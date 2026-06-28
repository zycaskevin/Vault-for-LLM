import json

import pytest

from vault.db import VaultDB
from vault.okf import import_okf_bundle, parse_markdown_frontmatter, validate_okf_bundle


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


def test_import_okf_bundle_dry_run_does_not_write_candidates(tmp_path):
    _write(tmp_path / "index.md", "# Bundle index\n")
    _write(tmp_path / "log.md", "# Bundle log\n")
    _write(
        tmp_path / "metric.md",
        """---
type: metric
title: Conversion rate
description: Paid orders divided by checkout sessions
tags: [analytics, conversion]
resource: metric.conversion_rate
timestamp: 2026-06-28
---

Use this metric when reviewing checkout funnel experiments because it reflects real order completion.
""",
    )
    db_path = tmp_path / "vault.db"
    with VaultDB(db_path) as db:
        payload = import_okf_bundle(db, tmp_path, dry_run=True)
        rows = db.list_memory_candidates(status=None)

    assert payload["status"] == "preview"
    assert payload["candidate_count"] == 1
    assert payload["created_count"] == 0
    assert rows == []


def test_import_okf_bundle_writes_candidates_only(tmp_path):
    bundle = tmp_path / "bundle"
    _write(bundle / "index.md", "# Bundle index\n")
    _write(bundle / "log.md", "# Bundle log\n")
    _write(
        bundle / "tables" / "orders.md",
        """---
type: table
title: Orders table
description: Customer order records
tags: [warehouse, orders]
resource: db.public.orders
timestamp: 2026-06-28
valid_from: 2026-06-01T00:00:00Z
valid_until: 2026-12-31T00:00:00Z
---

Orders are joined by customer_id because each order belongs to exactly one customer account.
""",
    )
    with VaultDB(tmp_path / "vault.db") as db:
        payload = import_okf_bundle(
            db,
            bundle,
            scope="shared",
            owner_agent="work-agent",
            tags="imported",
            trust=0.7,
        )
        candidates = db.list_memory_candidates(status=None)
        active = db.list_knowledge()

    assert payload["status"] == "ok"
    assert payload["created_count"] == 1
    assert payload["rejected_count"] == 0
    assert active == []
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["title"] == "Orders table"
    assert candidate["source"] == "okf"
    assert candidate["source_ref"].startswith("okf:tables/orders.md")
    assert "resource=db.public.orders" in candidate["source_ref"]
    assert candidate["category"] == "table"
    assert candidate["memory_type"] == "okf_concept"
    assert candidate["scope"] == "shared"
    assert candidate["owner_agent"] == "work-agent"
    assert candidate["valid_from"] == "2026-06-01T00:00:00Z"
    assert candidate["valid_until"] == "2026-12-31T00:00:00Z"
    assert "imported" in candidate["tags"]
    assert "warehouse" in candidate["tags"]


def test_okf_import_cli_json_writes_candidate(tmp_path, capsys):
    from vault.cli import main

    project = tmp_path / "project"
    bundle = tmp_path / "bundle"
    main(["init", "--project-dir", str(project)])
    capsys.readouterr()
    _write(bundle / "index.md", "# Bundle index\n")
    _write(bundle / "log.md", "# Bundle log\n")
    _write(
        bundle / "concept.md",
        """---
type: decision
title: Use bounded reads
description: Agents should cite bounded source ranges
tags: [agent, citation]
---

Use bounded reads before answering because raw document dumps waste context and weaken citations.
""",
    )

    main([
        "import",
        "okf",
        "--bundle",
        str(bundle),
        "--project-dir",
        str(project),
        "--json",
    ])

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["created_count"] == 1
    with VaultDB(project / "vault.db") as db:
        candidates = db.list_memory_candidates(status=None)
        active = db.list_knowledge()
    assert len(candidates) == 1
    assert active == []
