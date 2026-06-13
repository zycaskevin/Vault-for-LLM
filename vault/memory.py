"""Deterministic memory curator proposal and promotion scaffolding."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from pathlib import Path
from typing import Any

from .compiler import VaultCompiler, simple_aaak_compress, generate_summary
from .db import VaultDB
from .privacy import redact_secrets, scan_privacy

_VALID_LAYERS = {"L0", "L1", "L2", "L3"}
_VALID_STATUSES = {"pass", "warn", "fail"}
_NEAR_DUPLICATE_THRESHOLD = 0.82
_NEAR_TITLE_THRESHOLD = 0.75
_GENERIC_TITLES = {"note", "notes", "memory", "misc", "update", "todo", "untitled", "雜記", "筆記", "記憶"}
_QUALITY_SIGNALS = {
    "because", "caused", "fix", "fixed", "decision", "decided", "prefer", "avoid",
    "step", "error", "bug", "reason", "limit", "constraint", "解法", "修復", "原因",
    "決策", "偏好", "避免", "步驟", "錯誤", "限制", "問題", "因此",
}


def normalize_title(title: str) -> str:
    return " ".join((title or "").strip().split())


def normalize_text(text: str) -> str:
    return " ".join((text or "").strip().split()).casefold()


def content_hash(content: str) -> str:
    return hashlib.sha256(normalize_text(content).encode("utf-8")).hexdigest()[:16]


def _similarity_tokens(text: str) -> set[str]:
    normalized = normalize_text(text)
    words = set(re.findall(r"[\w]+", normalized, flags=re.UNICODE))
    compact = re.sub(r"\s+", "", normalized)
    if len(compact) >= 3:
        words.update(compact[i:i + 3] for i in range(len(compact) - 2))
    return {token for token in words if token}


def text_similarity(left: str, right: str) -> float:
    """Deterministic token/character n-gram Jaccard similarity."""
    a = _similarity_tokens(left)
    b = _similarity_tokens(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def safe_slug(title: str) -> str:
    slug = re.sub(r"[^\w\-.]+", "-", normalize_title(title).lower(), flags=re.UNICODE).strip("-._")
    return slug or "memory"


def normalize_metadata(
    title: str,
    content: str,
    *,
    layer: str = "L3",
    category: str = "general",
    tags: str | list[str] = "",
    trust: float = 0.5,
    source: str = "memory",
    source_ref: str = "",
    reason: str = "",
) -> dict:
    if isinstance(tags, list):
        tags_s = ",".join(str(t).strip() for t in tags if str(t).strip())
    else:
        tags_s = ",".join(t.strip() for t in str(tags or "").split(",") if t.strip())
    norm_layer = str(layer or "L3").strip().upper()
    if norm_layer not in _VALID_LAYERS:
        norm_layer = "L3"
    try:
        trust_f = max(0.0, min(1.0, float(trust)))
    except (TypeError, ValueError):
        trust_f = 0.5
    return {
        "title": normalize_title(title),
        "content": (content or "").strip(),
        "layer": norm_layer,
        "category": (category or "general").strip() or "general",
        "tags": tags_s,
        "trust": trust_f,
        "source": (source or "memory").strip() or "memory",
        "source_ref": (source_ref or "").strip(),
        "reason": (reason or "").strip(),
    }


def metadata_gate(meta: dict) -> dict:
    findings = []
    if not meta.get("title"):
        findings.append({"type": "title", "severity": "fail", "span": "[EMPTY]"})
    if not meta.get("content"):
        findings.append({"type": "content", "severity": "fail", "span": "[EMPTY]"})
    if not meta.get("reason"):
        findings.append({"type": "reason", "severity": "warn", "span": "[EMPTY]"})
    status = "fail" if any(f["severity"] == "fail" for f in findings) else "warn" if findings else "pass"
    return {"status": status, "findings": findings}


def quality_gate(meta: dict) -> dict:
    """Warn on memories that are likely hard to retrieve or low-value noise."""
    findings: list[dict[str, Any]] = []
    title = normalize_title(meta.get("title", ""))
    content = str(meta.get("content", "") or "").strip()
    tags = str(meta.get("tags", "") or "").strip()
    reason = str(meta.get("reason", "") or "").strip()
    lower_blob = normalize_text(f"{title} {content} {reason} {tags}")

    if len(content) < 40:
        findings.append({"type": "content_too_short", "severity": "warn", "span": content[:40] or "[EMPTY]"})
    if normalize_text(title) in _GENERIC_TITLES:
        findings.append({"type": "generic_title", "severity": "warn", "span": title or "[EMPTY]"})
    if not tags:
        findings.append({"type": "missing_tags", "severity": "warn", "span": "[EMPTY]"})
    if not any(signal in lower_blob for signal in _QUALITY_SIGNALS):
        findings.append({"type": "low_context", "severity": "warn", "span": content[:80] or "[EMPTY]"})

    return {"status": "warn" if findings else "pass", "findings": findings}


def duplicate_gate(db: VaultDB, title: str, content: str, *, exclude_candidate_id: str | None = None) -> dict:
    nt = normalize_text(title)
    nc = normalize_text(content)
    ch = content_hash(content)
    findings: list[dict[str, Any]] = []

    for row in db.conn.execute("SELECT id, title, content_raw, content_hash FROM knowledge").fetchall():
        if normalize_text(row["title"]) == nt:
            findings.append({"type": "active_title", "severity": "warn", "span": f"knowledge:{row['id']}"})
        if normalize_text(row["content_raw"]) == nc or (row["content_hash"] and row["content_hash"] == ch):
            findings.append({"type": "active_content", "severity": "warn", "span": f"knowledge:{row['id']}"})
        elif text_similarity(content, row["content_raw"]) >= _NEAR_DUPLICATE_THRESHOLD:
            findings.append({"type": "active_near_duplicate", "severity": "warn", "span": f"knowledge:{row['id']}"})
        elif text_similarity(title, row["title"]) >= _NEAR_TITLE_THRESHOLD:
            findings.append({"type": "active_near_title", "severity": "warn", "span": f"knowledge:{row['id']}"})

    params: list[Any] = []
    query = "SELECT id, title, content FROM memory_candidates WHERE status IN ('candidate','approved')"
    if exclude_candidate_id:
        query += " AND id != ?"
        params.append(exclude_candidate_id)
    for row in db.conn.execute(query, params).fetchall():
        if normalize_text(row["title"]) == nt:
            findings.append({"type": "candidate_title", "severity": "warn", "span": f"candidate:{row['id']}"})
        if normalize_text(row["content"]) == nc or content_hash(row["content"]) == ch:
            findings.append({"type": "candidate_content", "severity": "warn", "span": f"candidate:{row['id']}"})
        elif text_similarity(content, row["content"]) >= _NEAR_DUPLICATE_THRESHOLD:
            findings.append({"type": "candidate_near_duplicate", "severity": "warn", "span": f"candidate:{row['id']}"})
        elif text_similarity(title, row["title"]) >= _NEAR_TITLE_THRESHOLD:
            findings.append({"type": "candidate_near_title", "severity": "warn", "span": f"candidate:{row['id']}"})

    return {"status": "warn" if findings else "pass", "findings": findings}


def _gate_payload(privacy: dict, duplicate: dict, metadata: dict, quality: dict) -> dict:
    return {"privacy": privacy, "duplicate": duplicate, "metadata": metadata, "quality": quality}


def create_candidate(db: VaultDB, **kwargs) -> dict:
    meta = normalize_metadata(**kwargs)
    privacy = scan_privacy(f"{meta['title']}\n{meta['content']}\n{meta['source_ref']}\n{meta['reason']}")
    duplicate = duplicate_gate(db, meta["title"], meta["content"])
    metadata = metadata_gate(meta)
    quality = quality_gate(meta)
    gates = _gate_payload(privacy, duplicate, metadata, quality)
    rejected = privacy["status"] == "fail" or metadata["status"] == "fail"
    stored_meta = dict(meta)
    if privacy["status"] == "fail":
        for field in ("title", "content", "source_ref", "reason"):
            stored_meta[field] = redact_secrets(stored_meta.get(field, ""))
    candidate_id = f"mem_{uuid.uuid4().hex[:12]}"
    candidate = {
        "id": candidate_id,
        **stored_meta,
        "status": "rejected" if rejected else "candidate",
        "privacy_status": privacy["status"],
        "duplicate_status": duplicate["status"],
        "quality_status": quality["status"],
        "gate_payload_json": json.dumps(gates, ensure_ascii=False, sort_keys=True),
    }
    db.add_memory_candidate(candidate)
    result = {
        "status": "rejected" if rejected else "candidate_created",
        "candidate_id": candidate_id,
        "knowledge_id": None,
        "gates": {"privacy": privacy["status"], "duplicate": duplicate["status"], "metadata": metadata["status"], "quality": quality["status"]},
        "gate_payload": gates,
    }
    if not rejected:
        result["next_action"] = {"tool": "vault_memory_promote", "arguments": {"candidate_id": candidate_id, "confirm": True}}
    return result


def propose_memory(db: VaultDB, mode: str = "candidate", **kwargs) -> dict:
    project_dir = kwargs.pop("project_dir", None)
    result = create_candidate(db, **kwargs)
    if mode == "promote_if_safe" and result["status"] == "candidate_created" and result["gates"]["privacy"] != "fail":
        promoted = promote_candidate(db, result["candidate_id"], confirm=True, project_dir=project_dir)
        result.update({"status": "promoted", "knowledge_id": promoted["knowledge_id"], "promotion": promoted})
    elif mode == "promote_if_safe" and result["status"] == "candidate_created":
        result["auto_promotion"] = {
            "status": "skipped",
            "reason": "promote_if_safe requires privacy, duplicate, metadata, and quality gates to pass",
        }
    return result


def _unique_raw_path(project_dir: Path, title: str) -> Path:
    raw_dir = project_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    base = safe_slug(title)
    path = raw_dir / f"{base}.md"
    idx = 2
    while path.exists():
        path = raw_dir / f"{base}-{idx}.md"
        idx += 1
    return path


def promote_candidate(db: VaultDB, candidate_id: str, *, confirm: bool = False, project_dir: str | Path | None = None, compile: bool = True, build_map: bool = True) -> dict:
    if not confirm:
        raise ValueError("promotion requires confirm=True")
    candidate = db.get_memory_candidate(candidate_id)
    if not candidate:
        raise KeyError(f"candidate not found: {candidate_id}")
    if candidate["status"] == "promoted" and candidate.get("promoted_knowledge_id"):
        return {"status": "already_promoted", "candidate_id": candidate_id, "knowledge_id": candidate["promoted_knowledge_id"], "candidate": candidate}
    if candidate["status"] == "rejected":
        return {"status": "blocked", "candidate_id": candidate_id, "knowledge_id": None, "candidate": candidate}

    privacy = scan_privacy(f"{candidate['title']}\n{candidate['content']}\n{candidate['source_ref']}\n{candidate['reason']}")
    duplicate = duplicate_gate(db, candidate["title"], candidate["content"], exclude_candidate_id=candidate_id)
    metadata = metadata_gate(candidate)
    quality = quality_gate(candidate)
    gates = _gate_payload(privacy, duplicate, metadata, quality)
    if privacy["status"] == "fail" or metadata["status"] == "fail":
        db.update_memory_candidate(candidate_id, status="rejected", privacy_status=privacy["status"], duplicate_status=duplicate["status"], quality_status=quality["status"], gate_payload_json=json.dumps(gates, ensure_ascii=False, sort_keys=True))
        return {"status": "blocked", "candidate_id": candidate_id, "knowledge_id": None, "gates": gates}

    root = Path(project_dir) if project_dir is not None else db.db_path.parent
    raw_path = _unique_raw_path(root, candidate["title"])
    source_file = str(raw_path.relative_to(root / "raw"))
    frontmatter = {
        "title": candidate["title"],
        "layer": candidate["layer"],
        "category": candidate["category"],
        "tags": candidate["tags"],
        "trust": candidate["trust"],
        "source": source_file,
        "memory_candidate_id": candidate_id,
    }
    raw_path.write_text(f"---\n{json.dumps(frontmatter, ensure_ascii=False, indent=2)}\n---\n\n{candidate['content']}\n", encoding="utf-8")

    knowledge_id: int | None = None
    if compile:
        compiler = VaultCompiler(root, db=db, embed_provider=None)
        compiler.compile(dry_run=False)
        row = db.conn.execute("SELECT id FROM knowledge WHERE source = ? ORDER BY id DESC LIMIT 1", (source_file,)).fetchone()
        knowledge_id = int(row["id"]) if row else None
    if knowledge_id is None:
        knowledge_id = db.add_knowledge(
            title=candidate["title"],
            content_raw=candidate["content"],
            content_aaak=simple_aaak_compress(candidate["title"], candidate["content"]),
            summary=generate_summary(candidate["content"], title=candidate["title"]),
            layer=candidate["layer"],
            category=candidate["category"],
            tags=candidate["tags"],
            trust=float(candidate["trust"]),
            source=source_file,
        )
        if build_map:
            VaultCompiler(root, db=db, embed_provider=None)._refresh_document_map(knowledge_id)

    db.update_memory_candidate(candidate_id, status="promoted", privacy_status=privacy["status"], duplicate_status=duplicate["status"], quality_status=quality["status"], gate_payload_json=json.dumps(gates, ensure_ascii=False, sort_keys=True), promoted_knowledge_id=knowledge_id)
    return {
        "status": "promoted",
        "candidate_id": candidate_id,
        "knowledge_id": knowledge_id,
        "raw_path": str(raw_path),
        "gates": {"privacy": privacy["status"], "duplicate": duplicate["status"], "metadata": metadata["status"], "quality": quality["status"]},
        "knowledge": db.get_knowledge(knowledge_id),
        "candidate": db.get_memory_candidate(candidate_id),
    }
