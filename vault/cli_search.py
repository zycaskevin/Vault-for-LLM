"""CLI search option helpers."""

from __future__ import annotations

from typing import Any


def arg_value(args: Any, name: str, default: Any = None) -> Any:
    value = getattr(args, name, default)
    # Tests sometimes pass MagicMock instances that synthesize attributes. Treat
    # those as absent unless a real parser value was provided.
    if value.__class__.__module__.startswith("unittest.mock"):
        return default
    return value


def temporal_search_kwargs(args: Any) -> dict[str, Any]:
    return {
        "include_expired_temporal": not bool(arg_value(args, "exclude_expired", False)),
        "include_future_temporal": not bool(arg_value(args, "exclude_future", False)),
        "temporal_as_of": arg_value(args, "temporal_as_of", ""),
    }


def add_temporal_search_arguments(parser: Any) -> None:
    parser.add_argument(
        "--exclude-expired",
        action="store_true",
        help="排除 temporal_state=past 的過期事實；預設保留但標記",
    )
    parser.add_argument(
        "--exclude-future",
        action="store_true",
        help="排除 temporal_state=future 的尚未生效事實；預設保留但標記",
    )
    parser.add_argument("--temporal-as-of", default="", help="用指定 ISO 時間判斷 temporal_state；預設現在")
