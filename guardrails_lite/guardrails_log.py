"""
Guardrails Lite — 統一日誌模組。

所有模組用 logging.getLogger("guardrails-lite") 輸出，
不再直接 print()。CLI 可以控制 level，其他模組保持安靜。

使用方式：
  from .guardrails_log import log
  log.info("✅ 模型已載入")
  log.warning("⚠️ FTS5 搜尋失敗")
  log.debug("embedding dim=%d", dim)
"""

import logging

# 建立 logger（所有子模組共用）
log = logging.getLogger("guardrails-lite")

# 預設 handler：如果沒有人設定，至少讓 WARNING 以上可以輸出
if not log.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[guardrails-lite] %(message)s"))
    handler.setLevel(logging.WARNING)
    log.addHandler(handler)
    log.setLevel(logging.WARNING)


def setup_logging(level: str = "INFO"):
    """
    CLI 用：設定日誌等級和格式。

    level: "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"
    """
    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
    lvl = level_map.get(level.upper(), logging.INFO)

    # 清除舊 handler（避免重複輸出）
    log.handlers.clear()

    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[guardrails-lite] %(message)s"))
    handler.setLevel(lvl)
    log.addHandler(handler)
    log.setLevel(lvl)