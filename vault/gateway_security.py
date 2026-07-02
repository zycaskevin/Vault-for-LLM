"""Small Gateway transport safety helpers."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
import hashlib
from ipaddress import ip_address, ip_network
import os
import time
from typing import Any


@dataclass(frozen=True)
class GatewaySecurityPolicy:
    rate_limit_per_minute: int = 60
    token_rate_limit_per_minute: int = 60
    auth_failure_limit: int = 10
    auth_lockout_seconds: int = 300
    ip_allowlist: str = ""
    ip_denylist: str = ""

    @classmethod
    def from_env(cls) -> "GatewaySecurityPolicy":
        return cls(
            rate_limit_per_minute=_env_int("VAULT_GATEWAY_RATE_LIMIT_PER_MINUTE", 60),
            token_rate_limit_per_minute=_env_int("VAULT_GATEWAY_TOKEN_RATE_LIMIT_PER_MINUTE", 60),
            auth_failure_limit=_env_int("VAULT_GATEWAY_AUTH_FAILURE_LIMIT", 10),
            auth_lockout_seconds=_env_int("VAULT_GATEWAY_AUTH_LOCKOUT_SECONDS", 300),
            ip_allowlist=os.environ.get("VAULT_GATEWAY_IP_ALLOWLIST", "").strip(),
            ip_denylist=os.environ.get("VAULT_GATEWAY_IP_DENYLIST", "").strip(),
        )


class GatewaySecurityState:
    """In-memory per-process request limiter and auth failure tracker."""

    def __init__(self, policy: GatewaySecurityPolicy | None = None):
        self.policy = policy or GatewaySecurityPolicy.from_env()
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._auth_failures: dict[str, deque[float]] = defaultdict(deque)
        self._lockouts: dict[str, float] = {}

    def check_ip_policy(self, client_ip: str) -> tuple[bool, str]:
        if _matches_any(client_ip, self.policy.ip_denylist):
            return False, "ip_denied"
        allowlist = self.policy.ip_allowlist.strip()
        if allowlist and not _matches_any(client_ip, allowlist):
            return False, "ip_not_allowed"
        return True, "ok"

    def check_rate_limit(self, *, client_ip: str, token_hint: str = "") -> tuple[bool, str]:
        ok, reason = self._check_bucket(
            f"ip:{client_ip}",
            self.policy.rate_limit_per_minute,
        )
        if not ok:
            return False, reason
        if token_hint:
            return self._check_bucket(
                f"token:{_token_fingerprint(token_hint)}",
                self.policy.token_rate_limit_per_minute,
            )
        return True, "ok"

    def check_auth_lockout(self, client_ip: str) -> tuple[bool, str]:
        until = self._lockouts.get(client_ip, 0.0)
        if until and until > time.monotonic():
            return False, "auth_locked"
        if until:
            self._lockouts.pop(client_ip, None)
        return True, "ok"

    def record_auth_failure(self, client_ip: str) -> tuple[bool, str]:
        limit = max(0, int(self.policy.auth_failure_limit or 0))
        if limit <= 0:
            return True, "auth_failed"
        now = time.monotonic()
        window_start = now - 60.0
        failures = self._auth_failures[client_ip]
        while failures and failures[0] < window_start:
            failures.popleft()
        failures.append(now)
        if len(failures) >= limit:
            self._lockouts[client_ip] = now + max(1, int(self.policy.auth_lockout_seconds or 1))
            failures.clear()
            return False, "auth_locked"
        return True, "auth_failed"

    def record_auth_success(self, client_ip: str) -> None:
        self._auth_failures.pop(client_ip, None)
        self._lockouts.pop(client_ip, None)

    def status(self) -> dict[str, Any]:
        return {
            "rate_limit_per_minute": self.policy.rate_limit_per_minute,
            "token_rate_limit_per_minute": self.policy.token_rate_limit_per_minute,
            "auth_failure_limit": self.policy.auth_failure_limit,
            "auth_lockout_seconds": self.policy.auth_lockout_seconds,
            "ip_allowlist_configured": bool(self.policy.ip_allowlist.strip()),
            "ip_denylist_configured": bool(self.policy.ip_denylist.strip()),
        }

    def _check_bucket(self, key: str, limit: int) -> tuple[bool, str]:
        limit_i = int(limit or 0)
        if limit_i <= 0:
            return True, "ok"
        now = time.monotonic()
        window_start = now - 60.0
        bucket = self._requests[key]
        while bucket and bucket[0] < window_start:
            bucket.popleft()
        if len(bucket) >= limit_i:
            return False, "rate_limited"
        bucket.append(now)
        return True, "ok"


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "").strip() or default)
    except ValueError:
        return int(default)


def _matches_any(client_ip: str, rules: str) -> bool:
    if not str(rules or "").strip():
        return False
    try:
        ip = ip_address(str(client_ip).strip())
    except ValueError:
        return False
    for raw in str(rules).split(","):
        item = raw.strip()
        if not item:
            continue
        try:
            if "/" in item:
                if ip in ip_network(item, strict=False):
                    return True
            elif ip == ip_address(item):
                return True
        except ValueError:
            continue
    return False


def _token_fingerprint(value: str) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:16]
