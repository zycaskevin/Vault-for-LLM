"""Deterministic privacy gate for memory curator workflows."""

from __future__ import annotations

import re
from typing import Iterable


_SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("private_key", re.compile(r"-----BEGIN\s+(?:RSA\s+|EC\s+|OPENSSH\s+)?PRIVATE KEY-----[\s\S]*?-----END\s+(?:RSA\s+|EC\s+|OPENSSH\s+)?PRIVATE KEY-----")),
    ("github_token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{20,}\b")),
    ("api_key", re.compile(r"(?i)\b(?:api[\s_-]?key|apikey|access[\s_-]?key|secret[\s_-]?key)\b\s*(?::|=|\bis\b)\s*['\"]?([A-Za-z0-9_\-]{16,})['\"]?")),
    ("bearer_token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/\-]+=*")),
    ("password", re.compile(r"(?i)\b(?:password|passwd|pwd)\b\s*(?::|=|\bis\b)\s*['\"]?([^'\"\s]{8,})['\"]?")),
]

_WARN_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("email", re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)),
    ("phone", re.compile(r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)")),
    ("url_secret_query", re.compile(r"https?://[^\s'\"<>]+[?&][^\s'\"<>]*(?:token|key|password|secret)=[^\s'\"<>]+", re.I)),
]


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


def scan_privacy(text: str) -> dict:
    """Scan text and return {status, findings}; spans are redacted."""
    fail = _findings(text or "", _SECRET_PATTERNS, "fail")
    warn = _findings(text or "", _WARN_PATTERNS, "warn")
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
