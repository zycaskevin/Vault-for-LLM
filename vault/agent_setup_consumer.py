"""Consumer-mode setup guides for non-technical Agent users."""

from __future__ import annotations

import shlex
from pathlib import Path

from .agent_setup_roster import _safe_slug


def write_consumer_daily_report_guide(
    *,
    output_dir: str | Path,
    project_dir: str | Path,
    agent: str,
    language: str = "en",
) -> dict[str, str]:
    """Write a plain-language guide for non-technical users."""
    out = Path(output_dir).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    guide = out / "README-consumer-daily-report.md"
    if language == "zh-Hant":
        content = f"""# Vault 一般使用者模式

這個安裝包是給 `{agent}` 這類 Agent 使用的。你不需要學 CLI。

每天你只需要看：

```bash
vault daily-report --project-dir {shlex.quote(str(Path(project_dir).expanduser()))}
```

日報只會顯示：

- 今天記憶系統觀察到什麼
- 有幾筆候選記憶等待整理
- 哪幾筆真的需要你按「保留 / 私人 / 不要記 / 延後」
- 有沒有過期或需要冷存的記憶

安全邊界：

- 日報是 read-only。
- 不會自動 promote、archive、delete。
- 不會顯示 raw candidate content。
- 你可以讓 Agent 代跑自動化，但最後 5% 的重要決策仍然留給你。

安裝包也會產生：

- `README-local-safety.md`：本機 GUI / MCP 安全設定說明
- `local-safety.env.example`：給 Agent 套用 GUI token 與 MCP HMAC 的範例
- `memory-automation.cron`：每日產生日報與短版審核佇列的排程範本

建議給 Agent 的指令：

> 請幫我維護 Vault 記憶。平常你自己查詢、整理、提候選；每天只給我一份短版 daily report，需要我決定的項目不要超過 5 筆。
"""
    elif language == "zh-CN":
        content = f"""# Vault 一般用户模式

这个安装包是给 `{agent}` 这类 Agent 使用的。你不需要学习 CLI。

每天你只需要看：

```bash
vault daily-report --project-dir {shlex.quote(str(Path(project_dir).expanduser()))}
```

日报只会显示：

- 今天记忆系统观察到什么
- 有几条候选记忆等待整理
- 哪几条真的需要你按「保留 / 私人 / 不要记 / 延后」
- 有没有过期或需要冷存的记忆

安全边界：

- 日报是 read-only。
- 不会自动 promote、archive、delete。
- 不会显示 raw candidate content。
- 你可以让 Agent 代跑自动化，但最后 5% 的重要决策仍然留给你。

安装包也会产生：

- `README-local-safety.md`：本机 GUI / MCP 安全设置说明
- `local-safety.env.example`：给 Agent 套用 GUI token 与 MCP HMAC 的示例
- `memory-automation.cron`：每日生成日报与短版审核队列的排程模板

建议给 Agent 的指令：

> 请帮我维护 Vault 记忆。平常你自己查询、整理、提候选；每天只给我一份短版 daily report，需要我决定的项目不要超过 5 条。
"""
    else:
        content = f"""# Vault Consumer Mode

This install pack is for agents such as `{agent}`. You do not need to learn the CLI.

Each day, read:

```bash
vault daily-report --project-dir {shlex.quote(str(Path(project_dir).expanduser()))}
```

The report shows only:

- what the memory system observed today
- how many candidate memories are waiting
- which few items need your decision
- whether expired memory needs cleanup

Safety boundary:

- The daily report is read-only.
- It does not promote, archive, or delete memory.
- It does not show raw candidate content.
- Agents can run the loop; the important 5% stays reviewable by you.

The install pack also writes:

- `README-local-safety.md`: local GUI / MCP safety guidance
- `local-safety.env.example`: GUI token and MCP HMAC examples for agents
- `memory-automation.cron`: a daily report and short review queue schedule template

Suggested instruction for your agent:

> Maintain Vault memory for me. Search, organize, and propose candidates yourself. Give me only a short daily report, with at most 5 decisions that need me.
"""
    guide.write_text(content, encoding="utf-8")
    return {"guide": str(guide)}


def write_consumer_security_hardening_guide(
    *,
    output_dir: str | Path,
    agent: str,
    language: str = "en",
) -> dict[str, str]:
    """Write local GUI/MCP safety guidance without generating real secrets."""
    out = Path(output_dir).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    readme = out / "README-local-safety.md"
    env = out / "local-safety.env.example"
    safe_agent = _safe_slug(agent, default="agent").upper().replace("-", "_")
    env.write_text(
        "\n".join(
            [
                "# Copy this file to your agent/runtime environment and replace placeholders.",
                "# Do not commit real tokens or secrets.",
                "VAULT_GUI_TOKEN=replace-with-a-long-random-local-token",
                "VAULT_MCP_REQUIRE_AGENT_SIGNATURE=1",
                f"VAULT_MCP_AGENT_SECRET_{safe_agent}=replace-with-a-different-long-random-secret",
                "",
            ]
        ),
        encoding="utf-8",
    )
    if language == "zh-Hant":
        content = f"""# 本機安全預設

Vault 的一般使用者模式預設會保守運作：

- `vault gui` 預設需要 token。
- `--no-auth` 只建議本機測試使用，不要給共享電腦或遠端入口。
- 多 Agent 或不完全可信的 runtime 應該啟用 MCP HMAC。
- 每個 Agent 應該使用不同的 `VAULT_MCP_AGENT_SECRET_<AGENT>`。

建議讓 `{agent}` 做：

1. 讀 `local-safety.env.example`。
2. 產生真正的本機 token/secret，放進該 Agent 的環境變數。
3. 執行 `vault security doctor`。

這些設定不會改變你的記憶內容，只是讓 GUI 與 MCP 入口更難被誤用。
"""
    elif language == "zh-CN":
        content = f"""# 本机安全默认值

Vault 的一般用户模式默认会保守运行：

- `vault gui` 默认需要 token。
- `--no-auth` 只建议本机测试使用，不要给共享电脑或远端入口。
- 多 Agent 或不完全可信的 runtime 应该启用 MCP HMAC。
- 每个 Agent 应该使用不同的 `VAULT_MCP_AGENT_SECRET_<AGENT>`。

建议让 `{agent}` 做：

1. 读 `local-safety.env.example`。
2. 生成真正的本机 token/secret，放进该 Agent 的环境变量。
3. 执行 `vault security doctor`。

这些设置不会改变你的记忆内容，只是让 GUI 与 MCP 入口更难被误用。
"""
    else:
        content = f"""# Local Safety Defaults

Vault consumer mode is conservative by default:

- `vault gui` requires a token by default.
- Use `--no-auth` only for localhost testing, not shared computers or remote entrypoints.
- Multi-agent or less-trusted runtimes should enable MCP HMAC.
- Each agent should use a different `VAULT_MCP_AGENT_SECRET_<AGENT>`.

Ask `{agent}` to:

1. Read `local-safety.env.example`.
2. Generate real local token/secret values in that agent's environment.
3. Run `vault security doctor`.

These settings do not change memory content. They protect the GUI and MCP entrypoints from accidental misuse.
"""
    readme.write_text(content, encoding="utf-8")
    return {"readme": str(readme), "env": str(env)}
