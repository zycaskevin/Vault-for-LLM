"""Read-side governance filters for multi-agent Vault access."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

SENSITIVITY_RANK = {
    "low": 0,
    "medium": 1,
    "high": 2,
    "restricted": 3,
}


def _normalize_agent(value: Any) -> str:
    return str(value or "").strip().lower()


def _parse_allowed_agents(value: Any) -> set[str]:
    if value is None or value == "":
        return set()
    if isinstance(value, (list, tuple, set)):
        return {_normalize_agent(item) for item in value if _normalize_agent(item)}
    text = str(value).strip()
    if not text:
        return set()
    if text.startswith("["):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            return {_normalize_agent(item) for item in parsed if _normalize_agent(item)}
    return {_normalize_agent(part) for part in text.split(",") if _normalize_agent(part)}


@dataclass(frozen=True)
class ReadPolicy:
    agent_id: str = ""
    include_private: bool = False
    max_sensitivity: str = ""

    @property
    def active(self) -> bool:
        return bool(self.agent_id or self.max_sensitivity)


def normalize_read_policy(
    *,
    agent_id: Any = "",
    include_private: Any = False,
    max_sensitivity: Any = "",
) -> ReadPolicy:
    sensitivity = str(max_sensitivity or "").strip().lower()
    if sensitivity and sensitivity not in SENSITIVITY_RANK:
        sensitivity = ""
    return ReadPolicy(
        agent_id=_normalize_agent(agent_id),
        include_private=bool(include_private),
        max_sensitivity=sensitivity,
    )


def can_read_memory(row: dict[str, Any], policy: ReadPolicy) -> bool:
    """Return whether a knowledge row is visible under a local read policy.

    The policy is opt-in. Without `agent_id` or `max_sensitivity`, legacy local
    behavior is preserved and all rows remain visible.
    """
    if not policy.active:
        return True

    sensitivity = str(row.get("sensitivity") or "low").strip().lower()
    sensitivity_rank = SENSITIVITY_RANK.get(sensitivity, 0)
    if policy.max_sensitivity:
        max_rank = SENSITIVITY_RANK[policy.max_sensitivity]
        if sensitivity_rank > max_rank:
            return False

    scope = str(row.get("scope") or "project").strip().lower()
    owner_agent = _normalize_agent(row.get("owner_agent"))
    allowed_agents = _parse_allowed_agents(row.get("allowed_agents"))
    agent = policy.agent_id

    if sensitivity == "restricted":
        return bool(agent and (agent == owner_agent or agent in allowed_agents))

    if scope == "private":
        return bool(
            policy.include_private
            and agent
            and (agent == owner_agent or agent in allowed_agents)
        )

    return True


def filter_readable_memories(rows: list[dict[str, Any]], policy: ReadPolicy) -> list[dict[str, Any]]:
    if not policy.active:
        return rows
    return [row for row in rows if can_read_memory(row, policy)]
