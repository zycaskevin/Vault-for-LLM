import json

import pytest

from vault.db import VaultDB
from vault.memory import promote_candidate
from vault.okf import export_okf_bundle, import_okf_bundle, parse_markdown_frontmatter, validate_okf_bundle
from vault.search_qa import evaluate_search_qa


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


def test_export_okf_bundle_excludes_private_and_restricted_by_default(tmp_path):
    project = tmp_path / "project"
    bundle = tmp_path / "okf-out"
    project.mkdir()
    with VaultDB(project / "vault.db") as db:
        public_id = db.add_knowledge(
            "Public SOP",
            "Agents should cite bounded source ranges because citations need a stable source.",
            category="workflow",
            tags="agent,citation",
            source="raw/public-sop.md",
            scope="shared",
            sensitivity="low",
            trust=0.8,
        )
        db.add_knowledge(
            "Private profile",
            "This private profile should not leave the local vault.",
            category="profile",
            scope="private",
            sensitivity="low",
            trust=0.9,
        )
        db.add_knowledge(
            "Restricted key handling",
            "Restricted knowledge should not be exported unless explicitly requested.",
            category="security",
            scope="shared",
            sensitivity="restricted",
            trust=0.9,
        )

    payload = export_okf_bundle(project_dir=project, bundle_dir=bundle)

    assert payload["status"] == "ok"
    assert payload["concept_count"] == 1
    assert payload["written"] == 3
    assert (bundle / "index.md").exists()
    assert (bundle / "log.md").exists()
    concept_path = bundle / payload["concepts"][0]["path"]
    assert concept_path.exists()
    assert f"vault_id: {public_id}" in concept_path.read_text(encoding="utf-8")
    assert "Private profile" not in (bundle / "index.md").read_text(encoding="utf-8")
    validation = validate_okf_bundle(bundle)
    assert validation["valid"] is True


def test_export_okf_bundle_dry_run_does_not_write_files(tmp_path):
    project = tmp_path / "project"
    bundle = tmp_path / "okf-out"
    project.mkdir()
    with VaultDB(project / "vault.db") as db:
        db.add_knowledge(
            "Dry Run Export",
            "Dry-run export should plan files without writing them.",
            category="workflow",
            tags="dry-run",
            trust=0.7,
        )

    payload = export_okf_bundle(project_dir=project, bundle_dir=bundle, dry_run=True)

    assert payload["status"] == "preview"
    assert payload["concept_count"] == 1
    assert payload["written"] == 0
    assert not bundle.exists()
    assert payload["paths"]


def test_export_okf_bundle_can_include_private_and_restricted(tmp_path):
    project = tmp_path / "project"
    bundle = tmp_path / "okf-out"
    project.mkdir()
    with VaultDB(project / "vault.db") as db:
        db.add_knowledge(
            "Restricted private item",
            "This only exports when both safety override flags are explicit.",
            category="security",
            scope="private",
            sensitivity="restricted",
            trust=0.8,
        )

    default_payload = export_okf_bundle(project_dir=project, bundle_dir=bundle / "default", dry_run=True)
    override_payload = export_okf_bundle(
        project_dir=project,
        bundle_dir=bundle / "override",
        include_private=True,
        include_restricted=True,
        dry_run=True,
    )

    assert default_payload["concept_count"] == 0
    assert override_payload["concept_count"] == 1


def test_okf_export_cli_json(tmp_path, capsys):
    from vault.cli import main

    project = tmp_path / "project"
    bundle = tmp_path / "okf-out"
    main(["init", "--project-dir", str(project)])
    capsys.readouterr()
    main([
        "add",
        "CLI OKF Export",
        "--content",
        "CLI export writes OKF concepts because portable exchange matters.",
        "--category",
        "workflow",
        "--tags",
        "okf,cli",
        "--project-dir",
        str(project),
    ])
    capsys.readouterr()

    main([
        "export",
        "okf",
        "--bundle",
        str(bundle),
        "--project-dir",
        str(project),
        "--json",
    ])

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["concept_count"] == 1
    assert (bundle / "index.md").exists()


def test_okf_exchange_roundtrip_promote_search_and_bounded_read(tmp_path):
    from vault.mcp_read import _vault_read_range_payload

    source_project = tmp_path / "source"
    target_project = tmp_path / "target"
    bundle = tmp_path / "okf-bundle"
    source_project.mkdir()
    target_project.mkdir()

    with VaultDB(source_project / "vault.db") as db:
        db.add_knowledge(
            "Checkout Rollback SOP",
            "\n".join(
                [
                    "# Checkout Rollback SOP",
                    "",
                    "## Rollback trigger",
                    "Rollback checkout experiments when payment authorization errors rise above two percent.",
                    "",
                    "## Owner",
                    "The release operator owns the rollback decision because customer payments are affected.",
                ]
            ),
            category="workflow",
            tags="checkout,rollback,release",
            source="raw/checkout-rollback.md",
            scope="shared",
            sensitivity="low",
            trust=0.9,
        )
        db.add_knowledge(
            "Private Checkout Notes",
            "Private checkout notes must not be exported by default.",
            category="profile",
            scope="private",
            sensitivity="low",
            trust=0.9,
        )

    exported = export_okf_bundle(project_dir=source_project, bundle_dir=bundle)
    assert exported["concept_count"] == 1
    assert validate_okf_bundle(bundle)["valid"] is True

    with VaultDB(target_project / "vault.db") as db:
        imported = import_okf_bundle(db, bundle, tags="roundtrip", scope="shared", trust=0.8)
        assert imported["created_count"] == 1
        candidates = db.list_memory_candidates(status="candidate")
        assert len(candidates) == 1
        promoted = promote_candidate(db, candidates[0]["id"], confirm=True, project_dir=target_project)
        promoted_id = promoted["knowledge_id"]
        assert db.get_knowledge(promoted_id)["title"] == "Checkout Rollback SOP"

    qa_file = tmp_path / "okf-roundtrip-qa.json"
    qa_file.write_text(
        json.dumps(
            {
                "name": "okf-roundtrip",
                "cases": [
                    {
                        "id": "checkout-rollback",
                        "query": "payment authorization errors rise above two percent",
                        "expected_ids": [promoted_id],
                        "expected_titles": ["Checkout Rollback SOP"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    snapshot = evaluate_search_qa(
        db_path=target_project / "vault.db",
        qa_file=qa_file,
        mode="keyword",
        limit=3,
    )

    assert snapshot["aggregate"]["topk_hits"] == 1
    assert snapshot["aggregate"]["read_range_guidance_rate"] == 1.0
    result = snapshot["cases"][0]["results"][0]
    assert result["id"] == promoted_id
    assert result["next_actions"][-1]["tool"] == "vault_read_range"
    with VaultDB(target_project / "vault.db") as db:
        promoted_content = db.get_knowledge(promoted_id)["content_raw"]
    evidence_line = next(
        idx
        for idx, line in enumerate(promoted_content.splitlines(), start=1)
        if "payment authorization errors" in line
    )
    read_payload = _vault_read_range_payload(
        promoted_id,
        line_start=evidence_line,
        line_end=evidence_line,
        db_path=str(target_project / "vault.db"),
    )
    assert read_payload["citation"] == f"#{promoted_id} Checkout Rollback SOP L{evidence_line}-L{evidence_line}"
    assert "payment authorization errors" in read_payload["content"]
