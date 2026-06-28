"""CLI helpers for OKF bundle workflows."""

from __future__ import annotations

import argparse
import json
import sys


def add_okf_parser(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser("okf", help="OKF bundle validation and exchange helpers")
    okf_sub = parser.add_subparsers(dest="okf_action")

    p = okf_sub.add_parser("validate", help="Validate an OKF-style Markdown bundle")
    p.add_argument("bundle_dir", help="OKF bundle directory")
    p.add_argument("--max-file-bytes", type=int, default=2_000_000, help="maximum bytes per Markdown file")
    p.add_argument("--json", action="store_true", help="output JSON")
    p.add_argument("--pretty", action="store_true", help="pretty JSON output")


def cmd_okf(args: argparse.Namespace) -> None:
    if getattr(args, "okf_action", "") != "validate":
        print("error: okf requires action: validate", file=sys.stderr)
        raise SystemExit(2)

    from .okf import validate_okf_bundle

    payload = validate_okf_bundle(args.bundle_dir, max_file_bytes=args.max_file_bytes)
    if args.json or args.pretty:
        print(json.dumps(payload, ensure_ascii=False, indent=2 if args.pretty else None, default=str))
    else:
        _print_validate_summary(payload)
    if not payload.get("valid", False):
        raise SystemExit(1)


def _print_validate_summary(payload: dict) -> None:
    print(f"OKF bundle: {payload.get('bundle_dir')}")
    print(
        f"status={payload.get('status')} concepts={payload.get('concept_count')} "
        f"warnings={payload.get('warning_count')} errors={payload.get('error_count')}"
    )
    for issue in payload.get("errors", [])[:10]:
        print(f"ERROR {issue.get('path')}: {issue.get('code')} - {issue.get('message')}")
    for issue in payload.get("warnings", [])[:10]:
        print(f"WARN {issue.get('path')}: {issue.get('code')} - {issue.get('message')}")
