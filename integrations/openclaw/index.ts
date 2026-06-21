import { execFile } from "node:child_process";
import { promisify } from "node:util";

type OpenClawPluginApi = any;

const execFileAsync = promisify(execFile);

interface VaultConfig {
  wrapperPath: string;
  autoRecall: boolean;
  autoRecallResults: number;
}

function parseConfig(raw: unknown): VaultConfig {
  const cfg = (raw ?? {}) as Record<string, unknown>;
  return {
    wrapperPath: (cfg.wrapperPath as string) || "vault-openclaw",
    autoRecall: cfg.autoRecall === true,
    autoRecallResults: (cfg.autoRecallResults as number) || 3,
  };
}

async function runVault(wrapperPath: string, args: string[]) {
  const { stdout } = await execFileAsync(wrapperPath, args, {
    maxBuffer: 1024 * 1024 * 8,
  });
  const text = stdout.trim();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function toolText(payload: unknown) {
  return {
    content: [
      {
        type: "text",
        text: typeof payload === "string" ? payload : JSON.stringify(payload, null, 2),
      },
    ],
  };
}

function toolError(err: unknown) {
  return {
    content: [{ type: "text", text: `Vault-for-LLM error: ${String(err)}` }],
    isError: true,
  };
}

export default function register(api: OpenClawPluginApi) {
  const cfg = parseConfig(api.pluginConfig);

  api.logger.info(`vault-for-llm: registered (${cfg.wrapperPath})`);

  api.registerTool({
    name: "vault_search",
    description:
      "Search governed Vault-for-LLM project memory. Use before answering project-memory, decision, SOP, pitfall, or source-of-truth questions.",
    parameters: {
      type: "object",
      properties: {
        query: { type: "string", description: "Search query" },
        limit: { type: "number", description: "Max results, default 5" },
        mode: {
          type: "string",
          enum: ["auto", "keyword", "vector", "semantic", "hybrid"],
          description: "Search mode, default auto",
        },
      },
      required: ["query"],
    },
    async execute(_toolCallId: string, params: Record<string, unknown>) {
      try {
        const query = String(params.query || "");
        const limit = String(params.limit || 5);
        const mode = String(params.mode || "auto");
        const result = await runVault(cfg.wrapperPath, [
          "search",
          query,
          "--limit",
          limit,
          "--mode",
          mode,
        ]);
        return toolText(result);
      } catch (err) {
        return toolError(err);
      }
    },
  });

  api.registerTool({
    name: "vault_read_range",
    description:
      "Read a bounded source range from Vault-for-LLM after vault_search returns an id/node/line range. Use this before citing evidence.",
    parameters: {
      type: "object",
      properties: {
        knowledge_id: { type: "number", description: "Vault knowledge id" },
        node_uid: { type: "string", description: "Optional Document Map node uid" },
        line_start: { type: "number", description: "Optional start line" },
        line_end: { type: "number", description: "Optional end line" },
      },
      required: ["knowledge_id"],
    },
    async execute(_toolCallId: string, params: Record<string, unknown>) {
      try {
        const args = ["read-range", String(params.knowledge_id)];
        if (params.node_uid) args.push("--node-uid", String(params.node_uid));
        if (params.line_start) args.push("--line-start", String(params.line_start));
        if (params.line_end) args.push("--line-end", String(params.line_end));
        const result = await runVault(cfg.wrapperPath, args);
        return toolText(result);
      } catch (err) {
        return toolError(err);
      }
    },
  });

  api.registerTool({
    name: "vault_memory_propose",
    description:
      "Propose a new memory candidate. Candidate-first only: do not promote unless a human operator explicitly asks.",
    parameters: {
      type: "object",
      properties: {
        title: { type: "string" },
        content: { type: "string" },
        reason: { type: "string" },
        source_ref: { type: "string" },
        category: { type: "string" },
        tags: { type: "string" },
      },
      required: ["title", "content", "reason"],
    },
    async execute(_toolCallId: string, params: Record<string, unknown>) {
      try {
        const args = [
          "propose",
          "--title",
          String(params.title || ""),
          "--content",
          String(params.content || ""),
          "--reason",
          String(params.reason || ""),
          "--source",
          "openclaw",
        ];
        if (params.source_ref) args.push("--source-ref", String(params.source_ref));
        if (params.category) args.push("--category", String(params.category));
        if (params.tags) args.push("--tags", String(params.tags));
        const result = await runVault(cfg.wrapperPath, args);
        return toolText(result);
      } catch (err) {
        return toolError(err);
      }
    },
  });

  api.registerTool({
    name: "vault_stats",
    description: "Show Vault-for-LLM project memory status and counts.",
    parameters: { type: "object", properties: {} },
    async execute() {
      try {
        const result = await runVault(cfg.wrapperPath, ["status"]);
        return toolText(result);
      } catch (err) {
        return toolError(err);
      }
    },
  });

  if (cfg.autoRecall) {
    api.logger.warn(
      "vault-for-llm: autoRecall is enabled, but manual search -> bounded read is recommended for governed project memory.",
    );
  }

  api.registerService({
    id: "vault-for-llm",
    start: () => {
      api.logger.info(`vault-for-llm: service started (autoRecall: ${cfg.autoRecall})`);
    },
    stop: () => {
      api.logger.info("vault-for-llm: stopped");
    },
  });
}
