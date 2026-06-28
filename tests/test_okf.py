import json

import pytest

from vault.okf import parse_markdown_frontmatter, validate_okf_bundle


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_parse_markdown_frontmatter_reports_non_mapping():
    parsed = parse_markdown_frontmatter("---\n- not\n- mapping\n---\nbody")

    assert parsed.has_frontmatter is True
    assert parsed.error == "frontmatter must be a mapping"


def test_validate_okf_bundle_accepts_valid_concepts(tmp_path):
    _write(tmp_path / "index.md", "# Bundle index\n")
    _write(tmp_path / "log.md", "# Bundle log\n")
    _write(
        tmp_path / "tables" / "orders.md",
        """---
type: table
title: Orders table
description: Customer order records
tags: [warehouse, orders]
timestamp: 2026-06-28
resource: db.public.orders
---

Orders are joined by customer_id.
""",
    )
    _write(
        tmp_path / "metrics" / "return-rate.md",
        """---
type: metric
title: Return rate
description: Returned orders divided by shipped orders
tags: [warehouse, returns]
timestamp: 2026-06-28
resource: metric.return_rate
---

Uses [orders](../tables/orders.md) as the source table.
""",
    )

    payload = validate_okf_bundle(tmp_path)

    assert payload["valid"] is True
    assert payload["status"] == "ok"
    assert payload["concept_count"] == 2
    assert payload["reserved_count"] == 2
    assert payload["errors"] == []
    assert payload["warnings"] == []
    assert {item["concept_id"] for item in payload["concepts"]} == {"metrics/return-rate", "tables/orders"}


def test_validate_okf_bundle_rejects_missing_type(tmp_path):
    _write(
        tmp_path / "concept.md",
        """---
title: Missing type
description: This concept has no type
---

Body
""",
    )

    payload = validate_okf_bundle(tmp_path)

    assert payload["valid"] is False
    assert any(issue["code"] == "missing_type" for issue in payload["errors"])


def test_validate_okf_bundle_reports_invalid_frontmatter(tmp_path):
    _write(
        tmp_path / "broken.md",
        """---
type: [
---

Body
""",
    )

    payload = validate_okf_bundle(tmp_path)

    assert payload["valid"] is False
    assert any(issue["code"] == "invalid_frontmatter" for issue in payload["errors"])


def test_validate_okf_bundle_warns_on_broken_markdown_link(tmp_path):
    _write(tmp_path / "index.md", "# Bundle index\n")
    _write(tmp_path / "log.md", "# Bundle log\n")
    _write(
        tmp_path / "concept.md",
        """---
type: concept
title: Link example
description: Demonstrates local link validation
---

See [missing](missing.md) for details.
""",
    )

    payload = validate_okf_bundle(tmp_path)

    assert payload["valid"] is True
    assert payload["status"] == "warn"
    assert any(issue["code"] == "broken_link" for issue in payload["warnings"])


def test_okf_validate_cli_json_output(tmp_path, capsys):
    from vault.cli import main

    _write(tmp_path / "index.md", "# Bundle index\n")
    _write(tmp_path / "log.md", "# Bundle log\n")
    _write(
        tmp_path / "concept.md",
        """---
type: concept
title: CLI concept
description: Validates JSON output
---

Body
""",
    )

    main(["okf", "validate", str(tmp_path), "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert payload["valid"] is True
    assert payload["concept_count"] == 1


def test_okf_validate_cli_exits_nonzero_when_invalid(tmp_path):
    from vault.cli import main

    _write(tmp_path / "concept.md", "No frontmatter\n")

    with pytest.raises(SystemExit) as exc:
        main(["okf", "validate", str(tmp_path), "--json"])

    assert exc.value.code == 1
