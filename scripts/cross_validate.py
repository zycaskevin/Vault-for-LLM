#!/usr/bin/env python3
"""
Guardrails 跨模型不對稱驗證 — 用不同家族的模型交叉驗證知識品質。

策略：
  - 本地 Qwen3-8B（vLLM）作為提取模型（Recall-first）
  - Ollama Cloud GLM-5.1 作為驗證模型（Precision-first）
  - 不對稱設計：提取用便宜模型，驗證用強模型
  - 只驗證低 trust 或 convergence_status = 'partial' 的條目

評分結果：
  - 全部通過 → trust += 0.1
  - 部分通過 → convergence_status = 'partial'
  - 全部失敗 → trust -= 0.2（最低 0.1）

使用方式：
  python3 scripts/cross_validate.py              # 預覽模式（不修改 DB）
  python3 scripts/cross_validate.py --apply      # 實際更新 trust
  python3 scripts/cross_validate.py --limit 10    # 只驗證 10 條
  python3 scripts/cross_validate.py --min-trust 0.5  # 只驗證 trust < 0.5
  python3 scripts/cross_validate.py --local-only  # 只用本地模型（不用雲端）
  python3 scripts/cross_validate.py --cloud-model glm-5.1  # 指定雲端模型
  python3 scripts/cross_validate.py --local-model qwen3-8b  # 指定本地模型
"""

import os
import sys
import json
import argparse
import subprocess
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from vault.guardrails_db import GuardrailsDB
from vault.guardrails_compile import extract_claims

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "guardrails.db")

# ── LLM 介面 ──────────────────────────────────────────

def call_vllm_local(prompt: str, model: str = "qwen3-8b", max_tokens: int = 300) -> str:
    """呼叫本地 vLLM API。"""
    import requests
    try:
        resp = requests.post(
            "http://127.0.0.1:8000/v1/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": max_tokens,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"  ⚠️ vLLM 呼叫失敗：{e}")
        return ""


def call_ollama_cloud(prompt: str, model: str = "glm-5.1", max_tokens: int = 300) -> str:
    """呼叫 Ollama Cloud API。"""
    import requests

    # 從環境變數或 .env 取 API key
    api_key = os.environ.get("OLLAMA_API_KEY", "")
    if not api_key:
        # 嘗試從專案目錄或家目錄的 .env 載入
        try:
            from _utils import load_dotenv_cascade
            load_dotenv_cascade()
            api_key = os.environ.get("OLLAMA_API_KEY", "")
        except Exception:
            pass

    if not api_key:
        print("  ⚠️ OLLAMA_API_KEY 未設定")
        return ""

    try:
        resp = requests.post(
            "https://ollama.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": max_tokens,
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"  ⚠️ Ollama Cloud 呼叫失敗：{e}")
        return ""


# ── 驗證邏輯 ──────────────────────────────────────────

VALIDATION_PROMPT = """你是知識驗證專家。請驗證以下知識條目的原子主張是否正確、完整。

條目標題：{title}
條目內容：
{content}

原子主張（需要逐一驗證）：
{claims}

請對每條主張評估：
1. 是否正確（correct/incorrect/partial）
2. 信心分數（0.0-1.0）
3. 如果不正確，缺少什麼資訊

請用以下 JSON 格式回答（只輸出 JSON）：
{{
  "claims": [
    {{
      "id": "C1",
      "verdict": "correct/incorrect/partial",
      "confidence": 0.0-1.0,
      "missing": "缺少的資訊（如果不正確）"
    }}
  ],
  "overall_confidence": 0.0-1.0,
  "needs_expansion": true/false
}}"""


def validate_entry(
    db: GuardrailsDB,
    kid: int,
    title: str,
    content_raw: str,
    content_aaak: str,
    use_local: bool = True,
    use_cloud: bool = True,
    local_model: str = "qwen3-8b",
    cloud_model: str = "glm-5.1",
) -> dict:
    """驗證單條知識條目。"""

    # 提取原子主張
    claims = extract_claims(title, content_raw)

    if not claims:
        # 沒有主張可驗證，用整段內容
        claims_text = f"(整體評估) {content_raw[:500]}"
    else:
        claims_text = "\n".join(
            f"- [{c['id']}] {c['claim']} ({c['span']})"
            for c in claims[:5]  # 最多驗證 5 條主張
        )

    prompt = VALIDATION_PROMPT.format(
        title=title,
        content=content_raw[:1500],
        claims=claims_text,
    )

    results = {
        "kid": kid,
        "title": title,
        "claims_count": len(claims),
        "local_result": None,
        "cloud_result": None,
        "final_verdict": None,
        "trust_delta": 0.0,
    }

    # 本地模型驗證（Qwen3-8B）
    if use_local:
        local_response = call_vllm_local(prompt, model=local_model)
        if local_response:
            local_parsed = parse_validation_response(local_response)
            results["local_result"] = local_parsed

    # 雲端模型驗證（GLM-5.1）
    if use_cloud:
        cloud_response = call_ollama_cloud(prompt, model=cloud_model)
        if cloud_response:
            cloud_parsed = parse_validation_response(cloud_response)
            results["cloud_result"] = cloud_parsed

    # 綜合判斷
    results["final_verdict"] = synthesize_results(results["local_result"], results["cloud_result"])
    results["trust_delta"] = calculate_trust_delta(results["final_verdict"])

    return results


def parse_validation_response(response: str) -> dict:
    """解析 LLM 驗證回應。"""
    import re
    try:
        # 嘗試找 JSON
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            return {
                "overall_confidence": float(data.get("overall_confidence", 0.5)),
                "needs_expansion": data.get("needs_expansion", False),
                "claims": data.get("claims", []),
            }
    except (json.JSONDecodeError, ValueError):
        pass

    # Fallback：從文字中提取信心分數
    confidence_match = re.search(r'(?:confidence|信心)[：:]\s*([\d.]+)', response, re.IGNORECASE)
    confidence = float(confidence_match.group(1)) if confidence_match else 0.5

    return {
        "overall_confidence": confidence,
        "needs_expansion": False,
        "claims": [],
    }


def synthesize_results(local: dict = None, cloud: dict = None) -> dict:
    """綜合本地和雲端驗證結果。"""
    if local and cloud:
        # 兩邊都有結果：取平均，雲端權重更高
        confidence = local.get("overall_confidence", 0.5) * 0.3 + cloud.get("overall_confidence", 0.5) * 0.7
        needs_expansion = local.get("needs_expansion", False) or cloud.get("needs_expansion", False)
    elif local:
        confidence = local.get("overall_confidence", 0.5)
        needs_expansion = local.get("needs_expansion", False)
    elif cloud:
        confidence = cloud.get("overall_confidence", 0.5)
        needs_expansion = cloud.get("needs_expansion", False)
    else:
        confidence = 0.3  # 兩邊都失敗，低信心
        needs_expansion = True

    # 判定 verdict
    if confidence >= 0.8:
        verdict = "complete"
    elif confidence >= 0.5:
        verdict = "partial"
    else:
        verdict = "needs_expansion"

    return {
        "confidence": round(confidence, 3),
        "verdict": verdict,
        "needs_expansion": needs_expansion,
    }


def calculate_trust_delta(verdict: dict) -> float:
    """根據驗證結果計算 trust 調整量。"""
    verdict_str = verdict.get("verdict", "partial")
    if verdict_str == "complete":
        return 0.1
    elif verdict_str == "partial":
        return 0.0  # 維持不變
    else:  # needs_expansion
        return -0.2


# ── 主流程 ──────────────────────────────────────────

def cross_validate(
    db_path: str = DB_PATH,
    apply: bool = False,
    limit: int = 0,
    min_trust: float = 0.8,
    local_only: bool = False,
    local_model: str = "qwen3-8b",
    cloud_model: str = "glm-5.1",
):
    """執行跨模型不對稱驗證。"""

    db = GuardrailsDB(db_path)
    db.connect()

    # 篩選待驗證條目
    conditions = ["(trust < ? OR convergence_status IN ('unknown', 'partial'))"]
    params: list = [min_trust]

    where_clause = conditions[0]
    query = f"SELECT id, title, content_raw, content_aaak, trust, convergence_status FROM knowledge WHERE {where_clause} ORDER BY trust ASC"

    if limit > 0:
        query += " LIMIT ?"
        params.append(limit)

    rows = db.conn.execute(query, params).fetchall()

    if not rows:
        print("✅ 沒有待驗證的條目（所有高 trust 條目已驗證）")
        db.close()
        return

    print(f"📊 找到 {len(rows)} 條待驗證條目")
    print(f"   模型：本地={local_model}，雲端={'跳過' if local_only else cloud_model}")
    print("=" * 70)

    use_cloud = not local_only
    results = []
    passed = 0
    partial = 0
    failed = 0

    for i, row in enumerate(rows, 1):
        kid = row[0]
        title = row[1]
        content_raw = row[2] or ""
        content_aaak = row[3] or ""
        trust = row[4]
        conv_status = row[5]

        print(f"\n🔍 [{i}/{len(rows)}] {title} (trust={trust}, conv={conv_status})")

        result = validate_entry(
            db, kid, title, content_raw, content_aaak,
            use_local=True,
            use_cloud=use_cloud,
            local_model=local_model,
            cloud_model=cloud_model,
        )

        verdict = result["final_verdict"]
        trust_delta = result["trust_delta"]

        # 更新 trust
        new_trust = max(0.1, min(1.0, trust + trust_delta))
        if verdict["verdict"] == "complete":
            passed += 1
            emoji = "✅"
        elif verdict["verdict"] == "partial":
            partial += 1
            emoji = "⚠️"
        else:
            failed += 1
            emoji = "❌"

        print(f"  {emoji} verdict={verdict['verdict']}, confidence={verdict['confidence']}, trust_delta={trust_delta:+.1f}")

        if apply:
            db.update_knowledge(kid, trust=new_trust)
            if verdict["verdict"] == "complete":
                db.update_convergence(kid, "complete", verdict["confidence"])
            elif verdict["verdict"] == "partial":
                db.update_convergence(kid, "partial", verdict["confidence"])
            else:
                db.update_convergence(kid, "partial", verdict["confidence"])
            print(f"  → trust: {trust:.2f} → {new_trust:.2f}")

        result["final_trust"] = new_trust
        results.append(result)

    # 總結
    print("\n" + "=" * 70)
    print(f"📈 跨模型驗證結果：")
    print(f"  ✅ Complete:  {passed}")
    print(f"  ⚠️  Partial:    {partial}")
    print(f"  ❌ Expand:     {failed}")
    print(f"  📊 總計:       {len(rows)}")

    if not apply:
        print("\n💡 這是預覽模式。使用 --apply 實際更新資料庫。")

    # 儲存報告
    report_path = os.path.join(os.path.dirname(db_path), "cross_validation_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "models": {"local": local_model, "cloud": cloud_model if use_cloud else "skipped"},
            "total": len(rows),
            "complete": passed,
            "partial": partial,
            "needs_expansion": failed,
            "results": [{
                "kid": r["kid"],
                "title": r["title"],
                "verdict": r["final_verdict"]["verdict"] if r.get("final_verdict") else "unknown",
                "confidence": r["final_verdict"]["confidence"] if r.get("final_verdict") else 0,
                "trust_delta": r["trust_delta"],
            } for r in results],
        }, f, ensure_ascii=False, indent=2)
    print(f"📄 報告已儲存：{report_path}")

    db.close()
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Guardrails 跨模型不對稱驗證")
    parser.add_argument("--apply", action="store_true", help="實際更新 DB（預設為預覽模式）")
    parser.add_argument("--limit", type=int, default=0, help="最多驗證幾條（0=全部）")
    parser.add_argument("--min-trust", type=float, default=0.8, help="只驗證 trust 低於此值的條目")
    parser.add_argument("--local-only", action="store_true", help="只用本地模型（不用雲端）")
    parser.add_argument("--local-model", type=str, default="qwen3-8b", help="本地模型名稱")
    parser.add_argument("--cloud-model", type=str, default="glm-5.1", help="雲端模型名稱")
    args = parser.parse_args()

    cross_validate(
        apply=args.apply,
        limit=args.limit,
        min_trust=args.min_trust,
        local_only=args.local_only,
        local_model=args.local_model,
        cloud_model=args.cloud_model,
    )