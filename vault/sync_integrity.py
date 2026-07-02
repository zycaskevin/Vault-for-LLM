"""HMAC helpers for remote sync payload integrity."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from typing import Any


SYNC_HMAC_ALGORITHM = "hmac-sha256-v1"
SYNC_HMAC_ENV = "VAULT_SYNC_HMAC_SECRET"
SYNC_HMAC_FIELDS = [
    "title",
    "content",
    "from_agent",
    "reason",
    "category",
    "tags",
    "trust",
    "scope",
    "sensitivity",
    "owner_agent",
    "allowed_agents",
    "memory_type",
    "source_ref",
    "idempotency_key",
]


def sync_hmac_secret_from_env() -> str:
    """Return the optional shared secret used for sync payload signatures."""
    return os.environ.get(SYNC_HMAC_ENV, "").strip()


def sync_payload_hash(payload: dict[str, Any]) -> str:
    """Return a stable SHA256 digest for the signed sync payload subset."""
    return hashlib.sha256(_canonical_payload(payload)).hexdigest()


def sign_sync_payload(payload: dict[str, Any], secret: str) -> dict[str, str]:
    """Return signature metadata for a remote sync payload."""
    secret_text = str(secret or "").strip()
    if not secret_text:
        return {}
    canonical = _canonical_payload(payload)
    signature = hmac.new(secret_text.encode("utf-8"), canonical, hashlib.sha256).hexdigest()
    return {
        "hmac_algorithm": SYNC_HMAC_ALGORITHM,
        "payload_hash": hashlib.sha256(canonical).hexdigest(),
        "hmac_signature": signature,
    }


def verify_sync_payload(payload: dict[str, Any], secret: str, *, require_signature: bool = False) -> dict[str, Any]:
    """Verify optional HMAC metadata on a remote sync payload."""
    signature = str(payload.get("hmac_signature") or "").strip()
    algorithm = str(payload.get("hmac_algorithm") or "").strip()
    payload_hash = str(payload.get("payload_hash") or "").strip()
    secret_text = str(secret or "").strip()
    if not signature and not payload_hash and not algorithm:
        return {
            "ok": not require_signature,
            "status": "missing" if require_signature else "unsigned",
            "error": "missing_signature" if require_signature else "",
        }
    if not secret_text:
        return {"ok": False, "status": "unverified", "error": "hmac_secret_missing"}
    if algorithm != SYNC_HMAC_ALGORITHM:
        return {"ok": False, "status": "invalid", "error": "unsupported_hmac_algorithm"}
    expected = sign_sync_payload(payload, secret_text)
    if payload_hash and not hmac.compare_digest(payload_hash, expected["payload_hash"]):
        return {"ok": False, "status": "invalid", "error": "payload_hash_mismatch"}
    if not hmac.compare_digest(signature, expected["hmac_signature"]):
        return {"ok": False, "status": "invalid", "error": "hmac_signature_mismatch"}
    return {"ok": True, "status": "verified", "error": "", "payload_hash": expected["payload_hash"]}


def _canonical_payload(payload: dict[str, Any]) -> bytes:
    data = {field: _canonical_value(payload.get(field)) for field in SYNC_HMAC_FIELDS}
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _canonical_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, dict):
        return {str(key): _canonical_value(val) for key, val in sorted(value.items())}
    text = str(value).strip()
    if text.startswith("["):
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError:
            decoded = None
        if isinstance(decoded, list):
            return [str(item).strip() for item in decoded if str(item).strip()]
    return text
