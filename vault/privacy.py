"""Deterministic privacy gate for memory curator workflows."""

from __future__ import annotations

import re
import base64
import binascii
import math
from typing import Iterable


_SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("private_key", re.compile(r"-----BEGIN\s+(?:RSA\s+|EC\s+|OPENSSH\s+)?PRIVATE KEY-----[\s\S]*?-----END\s+(?:RSA\s+|EC\s+|OPENSSH\s+)?PRIVATE KEY-----")),
    ("github_token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{20,}\b")),
    ("openai_api_key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_\-]{20,}\b")),
    ("api_key", re.compile(r"(?i)\b(?:api[\s_-]?key|apikey|access[\s_-]?key|secret[\s_-]?key)\b\s*(?::|=|\bis\b)\s*['\"]?([A-Za-z0-9_\-]{16,})['\"]?")),
    ("bearer_token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/\-]+=*")),
    ("password", re.compile(r"(?i)\b(?:password|passwd|pwd)\b\s*(?::|=|\bis\b)\s*['\"]?([^'\"\s]{8,})['\"]?")),
]

_WARN_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("email", re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)),
    ("phone", re.compile(r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)")),
    ("taiwan_mobile", re.compile(r"(?<!\d)(?:\+?886[-\s]?)?09\d{2}[-\s]?\d{3}[-\s]?\d{3}(?!\d)")),
    ("taiwan_id", re.compile(r"\b[A-Z][12]\d{8}\b", re.I)),
    ("url_secret_query", re.compile(r"https?://[^\s'\"<>]+[?&][^\s'\"<>]*(?:token|key|password|secret)=[^\s'\"<>]+", re.I)),
]

_INJECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("prompt_injection_ignore_instructions", re.compile(r"(?i)\bignore\s+(?:all\s+)?(?:previous|prior|system|developer)\s+instructions\b")),
    ("prompt_injection_reveal_secrets", re.compile(r"(?i)\b(?:reveal|print|dump|exfiltrate)\s+(?:the\s+)?(?:system\s+prompt|developer\s+message|api\s*key|token|secret)s?\b")),
    ("prompt_injection_tool_override", re.compile(r"(?i)\b(?:disable|bypass|override)\s+(?:safety|policy|guardrails?|access\s+control|privacy\s+gate)\b")),
    ("prompt_injection_zh_ignore", re.compile(r"(?:忽略|無視|无视|覆蓋|覆盖).{0,12}(?:之前|先前|系統|系统|開發者|开发者).{0,12}(?:指令|提示|規則|规则)")),
    ("prompt_injection_zh_secret", re.compile(r"(?:顯示|显示|輸出|输出|洩漏|泄漏).{0,12}(?:系統提示|系统提示|api\s*key|token|密鑰|密钥|秘密)")),
]

_BASE64_RE = re.compile(r"\b[A-Za-z0-9+/]{24,}={0,2}\b")
_HIGH_ENTROPY_RE = re.compile(r"\b[A-Za-z0-9._~+/\-]{32,}={0,2}\b")


def _redacted_span(text: str, start: int, end: int) -> str:
    snippet = text[start:end]
    if len(snippet) <= 8:
        return "[REDACTED]"
    return f"{snippet[:3]}…{snippet[-3:]}"


def _findings(text: str, patterns: Iterable[tuple[str, re.Pattern[str]]], severity: str) -> list[dict]:
    out: list[dict] = []
    for typ, pattern in patterns:
        for match in pattern.finditer(text):
            start, end = match.span(1) if match.lastindex else match.span()
            out.append({
                "type": typ,
                "severity": severity,
                "span": _redacted_span(text, start, end),
            })
    return out


def _entropy(value: str) -> float:
    if not value:
        return 0.0
    counts: dict[str, int] = {}
    for char in value:
        counts[char] = counts.get(char, 0) + 1
    total = len(value)
    return -sum((count / total) * math.log2(count / total) for count in counts.values())


def _derived_findings(text: str) -> list[dict]:
    out: list[dict] = []
    seen_spans: set[str] = set()
    for match in _HIGH_ENTROPY_RE.finditer(text or ""):
        token = match.group(0)
        if _entropy(token) >= 4.25:
            span = _redacted_span(text, match.start(), match.end())
            if span not in seen_spans:
                seen_spans.add(span)
                out.append({"type": "high_entropy_token", "severity": "warn", "span": span})
    for match in _BASE64_RE.finditer(text or ""):
        token = match.group(0)
        try:
            padded = token + "=" * (-len(token) % 4)
            decoded = base64.b64decode(padded, validate=True).decode("utf-8", "ignore")
        except (binascii.Error, UnicodeDecodeError, ValueError):
            continue
        if not decoded:
            continue
        decoded_privacy = _findings(decoded, _SECRET_PATTERNS, "fail")
        decoded_privacy.extend(_findings(decoded, _WARN_PATTERNS, "warn"))
        if decoded_privacy:
            decoded_has_fail = any(item.get("severity") == "fail" for item in decoded_privacy)
            out.append({
                "type": "encoded_sensitive_content",
                "severity": "fail" if decoded_has_fail else "warn",
                "span": _redacted_span(text, match.start(), match.end()),
                "decoded_severity": "fail" if decoded_has_fail else "warn",
            })
    return out


def scan_privacy(text: str) -> dict:
    """Scan text and return {status, findings}; spans are redacted."""
    fail = _findings(text or "", _SECRET_PATTERNS, "fail")
    warn = _findings(text or "", _WARN_PATTERNS, "warn")
    warn += _findings(text or "", _INJECTION_PATTERNS, "warn")
    derived = _derived_findings(text or "")
    fail += [item for item in derived if item.get("severity") == "fail"]
    warn += [item for item in derived if item.get("severity") != "fail"]
    findings = fail + warn
    status = "fail" if fail else "warn" if warn else "pass"
    return {"status": status, "findings": findings}


def redact_secrets(text: str) -> str:
    """Redact fail-severity secret values before storing blocked audit rows."""
    redacted = text or ""
    for _typ, pattern in _SECRET_PATTERNS:
        def repl(match: re.Match[str]) -> str:
            if match.lastindex:
                start, end = match.span(1)
                rel_start = start - match.start()
                rel_end = end - match.start()
                return f"{match.group(0)[:rel_start]}[REDACTED]{match.group(0)[rel_end:]}"
            return "[REDACTED]"

        redacted = pattern.sub(repl, redacted)
    return redacted

# Friendly alias for callers/tests.
privacy_gate = scan_privacy
