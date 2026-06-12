"""Markdown section parser for Vault Document Map."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import re
import sqlite3


_HEADING_RE = re.compile(r"^(#{1,3})[ \t]+(.+?)\s*$")
_CLAIM_RE = re.compile(
    r"^\s*-\s*\[(C\d+)\]\s+(.+?)\s*\(L(\d+)(?:-(?:L)?(\d+))?\)\s*$"
)


@dataclass
class SectionNode:
    """Parsed markdown section node matching knowledge_nodes fields."""

    node_uid: str
    heading: str
    level: int
    parent_uid: str
    path: str
    line_start: int
    line_end: int
    content_hash: str


@dataclass
class AtomicClaim:
    """Parsed AAAK atomic claim matching useful knowledge_claims fields."""

    claim_id: str
    claim: str
    line_start: int
    line_end: int
    source: str = "aaak"
    content_hash: str = ""

    def __post_init__(self) -> None:
        if not self.content_hash:
            self.content_hash = hashlib.sha256(self.claim.encode()).hexdigest()


def parse_markdown_sections(content: str) -> list[SectionNode]:
    """Parse H1/H2/H3 ATX markdown sections from raw content."""
    lines = content.splitlines()
    total_lines = max(1, len(lines))

    heading_nodes: list[SectionNode] = []
    current_h1: SectionNode | None = None
    current_h2: SectionNode | None = None

    for line_number, line in enumerate(lines, start=1):
        match = _HEADING_RE.match(line)
        if not match:
            continue

        level = len(match.group(1))
        heading = _clean_heading(match.group(2))
        node_uid = f"{_slugify(heading)}-{line_number}"

        parent_uid = ""
        parent_path = ""
        if level == 1:
            current_h2 = None
        elif level == 2:
            if current_h1 is not None:
                parent_uid = current_h1.node_uid
                parent_path = current_h1.path
        elif level == 3:
            if current_h2 is not None:
                parent_uid = current_h2.node_uid
                parent_path = current_h2.path
            elif current_h1 is not None:
                parent_uid = current_h1.node_uid
                parent_path = current_h1.path

        path = f"{parent_path}/{heading}" if parent_path else heading
        node = SectionNode(
            node_uid=node_uid,
            heading=heading,
            level=level,
            parent_uid=parent_uid,
            path=path,
            line_start=line_number,
            line_end=line_number,
            content_hash="",
        )
        heading_nodes.append(node)

        if level == 1:
            current_h1 = node
        elif level == 2:
            current_h2 = node

    if not heading_nodes:
        return [
            SectionNode(
                node_uid="root-1",
                heading="root",
                level=0,
                parent_uid="",
                path="root",
                line_start=1,
                line_end=total_lines,
                content_hash=_hash_lines(lines, 1, total_lines),
            )
        ]

    for index, node in enumerate(heading_nodes):
        line_end = total_lines
        for next_node in heading_nodes[index + 1 :]:
            if next_node.level <= node.level:
                line_end = next_node.line_start - 1
                break
        node.line_end = max(node.line_start, line_end)
        node.content_hash = _hash_lines(lines, node.line_start, node.line_end)

    return heading_nodes


def parse_aaak_claims(content_aaak: str) -> list[AtomicClaim]:
    """Parse the CLAIMS section of AAAK text into atomic claims.

    Malformed or truncated claim bullets are ignored so truncated content_aaak
    values can be backfilled safely.
    """
    if not content_aaak or "CLAIMS:" not in content_aaak:
        return []

    claims: list[AtomicClaim] = []
    in_claims = False
    for line in content_aaak.splitlines():
        stripped = line.strip()
        if stripped == "CLAIMS:":
            in_claims = True
            continue
        if not in_claims:
            continue

        match = _CLAIM_RE.match(line)
        if not match:
            continue

        claim_id = match.group(1)
        claim_text = match.group(2).strip()
        try:
            line_start = int(match.group(3))
            line_end = int(match.group(4)) if match.group(4) else line_start
        except (TypeError, ValueError):
            continue
        if line_end < line_start or not claim_text:
            continue

        claims.append(
            AtomicClaim(
                claim_id=claim_id,
                claim=claim_text,
                line_start=line_start,
                line_end=line_end,
            )
        )

    return claims


def assign_claim_node_uid(nodes: list[SectionNode], claim_line_start: int) -> str:
    """Return the deepest/narrowest section node covering claim_line_start."""
    matching_nodes = [
        node for node in nodes if node.line_start <= claim_line_start <= node.line_end
    ]
    if not matching_nodes:
        return ""

    best = max(
        matching_nodes,
        key=lambda node: (node.level, -(node.line_end - node.line_start), node.line_start),
    )
    return best.node_uid


def build_document_map_for_entry(conn: sqlite3.Connection, knowledge_id: int) -> dict[str, int]:
    """Backfill knowledge_nodes and knowledge_claims for one knowledge row.

    This library entry point is intentionally small so future CLI/MCP commands can
    call it without changing existing search behavior.
    """
    row = conn.execute(
        "SELECT content_raw, content_aaak FROM knowledge WHERE id=?", (knowledge_id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"Knowledge id not found: {knowledge_id}")

    content_raw = row["content_raw"] if isinstance(row, sqlite3.Row) else row[0]
    content_aaak = row["content_aaak"] if isinstance(row, sqlite3.Row) else row[1]
    lines = (content_raw or "").splitlines()
    nodes = parse_markdown_sections(content_raw or "")
    claims = parse_aaak_claims(content_aaak or "")
    now = datetime.now(timezone.utc).isoformat()

    conn.execute("DELETE FROM knowledge_claims WHERE knowledge_id=?", (knowledge_id,))
    conn.execute("DELETE FROM knowledge_nodes WHERE knowledge_id=?", (knowledge_id,))

    conn.executemany(
        """INSERT INTO knowledge_nodes
           (knowledge_id, node_uid, heading, level, parent_uid, path,
            summary, line_start, line_end, token_estimate,
            content_hash, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            (
                knowledge_id,
                node.node_uid,
                node.heading,
                node.level,
                node.parent_uid,
                node.path,
                _section_summary(lines, node.line_start, node.line_end),
                node.line_start,
                node.line_end,
                _token_estimate(node.line_start, node.line_end),
                node.content_hash,
                now,
                now,
            )
            for node in nodes
        ],
    )
    claim_rows = []
    seen_claims: set[tuple[str, str]] = set()
    for claim in claims:
        node_uid = assign_claim_node_uid(nodes, claim.line_start)
        claim_key = (node_uid, claim.claim)
        if claim_key in seen_claims:
            continue
        seen_claims.add(claim_key)
        claim_rows.append(
            (
                knowledge_id,
                node_uid,
                _claim_uid(claim.claim, claim.line_start, claim.line_end),
                claim.claim,
                "claim",
                claim.line_start,
                claim.line_end,
                0.7,
                claim.source,
                claim.content_hash,
                now,
                now,
            )
        )

    conn.executemany(
        """INSERT INTO knowledge_claims
           (knowledge_id, node_uid, claim_uid, claim, claim_type, line_start,
            line_end, confidence, source, content_hash, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        claim_rows,
    )
    conn.commit()

    return {"nodes": len(nodes), "claims": len(claim_rows)}


def _clean_heading(raw_heading: str) -> str:
    heading = raw_heading.strip()
    heading = re.sub(r"\s+#+\s*$", "", heading).strip()
    return heading


def _slugify(text: str) -> str:
    slug = re.sub(r"[^\w]+", "-", text.lower(), flags=re.UNICODE).strip("-")
    return slug or "section"


def _hash_lines(lines: list[str], line_start: int, line_end: int) -> str:
    section_text = "\n".join(lines[line_start - 1 : line_end])
    return hashlib.sha256(section_text.encode()).hexdigest()


def _section_summary(lines: list[str], line_start: int, line_end: int) -> str:
    """Return the first non-heading text line in the section as a local summary."""
    for line in lines[line_start - 1 : line_end]:
        stripped = line.strip()
        if stripped and not _HEADING_RE.match(stripped):
            return stripped
    return ""


def _token_estimate(line_start: int, line_end: int) -> int:
    """Cheap local token estimate for Sprint 1; uses covered line count."""
    return max(0, line_end - line_start + 1)


def _claim_uid(claim: str, line_start: int, line_end: int) -> str:
    digest = hashlib.sha256(f"{line_start}:{line_end}:{claim}".encode()).hexdigest()[:16]
    return f"c-{line_start}-{digest}"
