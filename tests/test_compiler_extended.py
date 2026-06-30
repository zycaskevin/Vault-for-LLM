"""
Extended tests for vault/compiler.py
Focus on pure functions that don't require DB or external services.
"""
import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import MagicMock, patch


class TestExtractFrontmatter:
    def test_extract_frontmatter_with_yaml(self):
        """Test extracting YAML frontmatter."""
        from vault.compiler import extract_frontmatter
        content = """---
title: Test Document
category: tech
tags: python, test
---

# Main Content
Some content here.
"""
        fm, body = extract_frontmatter(content)
        assert fm["title"] == "Test Document"
        assert fm["category"] == "tech"
        assert fm["tags"] == "python, test"
        assert "# Main Content" in body

    def test_extract_frontmatter_no_frontmatter(self):
        """Test content without frontmatter."""
        from vault.compiler import extract_frontmatter
        content = """# Just a document
No frontmatter here.
"""
        fm, body = extract_frontmatter(content)
        assert fm == {}
        assert "# Just a document" in body

    def test_extract_frontmatter_empty(self):
        """Test empty content."""
        from vault.compiler import extract_frontmatter
        fm, body = extract_frontmatter("")
        assert fm == {}
        assert body == ""

    def test_extract_frontmatter_with_empty_fm(self):
        """Test empty frontmatter section."""
        from vault.compiler import extract_frontmatter
        content = """---
---
Content
"""
        fm, body = extract_frontmatter(content)
        assert fm == {}
        assert "Content" in body

    def test_extract_frontmatter_only_fm(self):
        """Test content that's only frontmatter."""
        from vault.compiler import extract_frontmatter
        content = """---
key: value
---"""
        fm, body = extract_frontmatter(content)
        assert fm["key"] == "value"
        assert body.strip() == ""


class TestExtractClaims:
    def test_extract_claims_basic(self):
        """Test basic claim extraction."""
        from vault.compiler import extract_claims
        content = """## Key Points

Claim 1: Python is a programming language.
Claim 2: It supports multiple paradigms.
"""
        claims = extract_claims("Test", content)
        assert isinstance(claims, list)
        # Should find at least some claims

    def test_extract_claims_empty(self):
        """Test empty content."""
        from vault.compiler import extract_claims
        claims = extract_claims("Test", "")
        assert isinstance(claims, list)
        assert len(claims) == 0

    def test_extract_claims_no_claims(self):
        """Test content with no claim-like sentences."""
        from vault.compiler import extract_claims
        content = "Hello world. This is just a greeting."
        claims = extract_claims("Test", content)
        assert isinstance(claims, list)


class TestSimpleAAAKCompress:
    def test_simple_aaak_compress_basic(self):
        """Test basic AAAK compression."""
        from vault.compiler import simple_aaak_compress
        content = """# Introduction
This is the first paragraph with some content.

## Details
More detailed information here.
Another sentence in the same section.

### Sub Details
Even more details.
"""
        result = simple_aaak_compress("Test Title", content)
        assert isinstance(result, str)
        assert len(result) > 0
        assert "TITLE:" in result

    def test_simple_aaak_compress_empty(self):
        """Test empty content."""
        from vault.compiler import simple_aaak_compress
        result = simple_aaak_compress("Title", "")
        assert isinstance(result, str)

    def test_simple_aaak_compress_short(self):
        """Test very short content."""
        from vault.compiler import simple_aaak_compress
        result = simple_aaak_compress("Title", "Short content.")
        assert isinstance(result, str)
        assert len(result) > 0


class TestGenerateSummary:
    def test_generate_summary_basic(self):
        """Test basic summary generation."""
        from vault.compiler import generate_summary
        content = "Python is a high-level programming language. It was created by Guido van Rossum. It supports multiple programming paradigms."
        summary = generate_summary(content, "Python Guide")
        assert isinstance(summary, str)
        assert len(summary) > 0

    def test_generate_summary_max_chars(self):
        """Test summary respects max_chars."""
        from vault.compiler import generate_summary
        content = "A" * 500
        summary = generate_summary(content, "Test", max_chars=100)
        assert isinstance(summary, str)
        assert len(summary) <= 100 + 10  # some tolerance

    def test_generate_summary_empty(self):
        """Test empty content summary."""
        from vault.compiler import generate_summary
        summary = generate_summary("", "Empty")
        assert isinstance(summary, str)


class TestClassifyContent:
    def test_classify_content_tech(self):
        """Test classifying tech content."""
        from vault.compiler import classify_content
        content = "Python programming with machine learning and AI."
        category = classify_content(content, {})
        assert isinstance(category, str)

    def test_classify_content_with_metadata_source(self):
        """Test classification with source metadata."""
        from vault.compiler import classify_content
        # Source matching category gives bonus weight
        category = classify_content("Some error occurred", {"source": "error-log"})
        assert isinstance(category, str)
        # Should have higher chance of being 'error' due to source match

    def test_classify_content_personal(self):
        """Test classifying personal content."""
        from vault.compiler import classify_content
        content = "Today I felt happy and went for a walk."
        category = classify_content(content, {})
        assert isinstance(category, str)


class TestAssignLayer:
    def test_assign_layer_l0(self):
        """Test L0 layer assignment."""
        from vault.compiler import assign_layer
        result = assign_layer({"layer": "L0"})
        assert result == "L0"

    def test_assign_layer_l1(self):
        """Test L1 layer assignment."""
        from vault.compiler import assign_layer
        result = assign_layer({"layer": "L1"})
        assert result == "L1"

    def test_assign_layer_default(self):
        """Test default layer assignment."""
        from vault.compiler import assign_layer
        result = assign_layer({})
        assert isinstance(result, str)
        assert result.startswith("L")

    def test_assign_layer_from_tags(self):
        """Test layer assignment from tags."""
        from vault.compiler import assign_layer
        result = assign_layer({"tags": "core-fact"})
        assert isinstance(result, str)


class TestExtractFrontmatterExtended:
    def test_extract_frontmatter_invalid_yaml(self):
        """Test frontmatter with invalid YAML gracefully returns empty dict."""
        from vault.compiler import extract_frontmatter
        content = """---
key: [unclosed list
---
Body content
"""
        fm, body = extract_frontmatter(content)
        assert fm == {}
        assert "Body content" in body

    def test_extract_frontmatter_unclosed(self):
        """Test frontmatter without closing --- returns empty dict and full content."""
        from vault.compiler import extract_frontmatter
        content = """---
title: Test
No closing marker
Some more text
"""
        fm, body = extract_frontmatter(content)
        assert fm == {}
        assert "No closing marker" in body

    def test_extract_frontmatter_only_opening(self):
        """Test content with only opening ---."""
        from vault.compiler import extract_frontmatter
        content = "---\nJust this line"
        fm, body = extract_frontmatter(content)
        assert fm == {}

    def test_extract_frontmatter_first_line_not_dashes(self):
        """Test content where first line is not ---."""
        from vault.compiler import extract_frontmatter
        content = "Not frontmatter\n---\ntitle: test\n---\n"
        fm, body = extract_frontmatter(content)
        assert fm == {}
        assert "Not frontmatter" in body

    def test_extract_frontmatter_single_line(self):
        """Test single line content."""
        from vault.compiler import extract_frontmatter
        fm, body = extract_frontmatter("just one line")
        assert fm == {}
        assert body == "just one line"


class TestExtractClaimsExtended:
    def test_extract_claims_with_list_items(self):
        """Test claim extraction from bullet list items."""
        from vault.compiler import extract_claims
        content = """## Points
- Python supports object-oriented programming very well
- It has a rich standard library for many tasks
- Functional programming is also supported
"""
        claims = extract_claims("Test", content)
        assert len(claims) > 0
        assert all("id" in c and "claim" in c and "span" in c for c in claims)

    def test_extract_claims_with_numbered_list(self):
        """Test claim extraction from numbered list items."""
        from vault.compiler import extract_claims
        content = """## Steps
1. First you need to install the required dependencies
2. Then configure the environment variables properly
3. Finally run the main program with correct arguments
"""
        claims = extract_claims("Test", content)
        assert len(claims) > 0

    def test_extract_claims_short_items_skipped(self):
        """Test that short list items (< 10 chars) are skipped."""
        from vault.compiler import extract_claims
        content = """- hi
- ok
- yes
- This is a much longer item that should be captured as a valid claim
"""
        claims = extract_claims("Test", content)
        # Short items should be skipped, only the long one should count
        assert len(claims) <= 2

    def test_extract_claims_skip_headers_and_code(self):
        """Test that headers and code blocks are skipped."""
        from vault.compiler import extract_claims
        content = """# This is a header
```
some code here that should not be counted as a claim
```
## Another header
- This is a valid claim that is long enough
"""
        claims = extract_claims("Test", content)
        # Only the bullet point should be a claim
        assert len(claims) <= 2

    def test_extract_claims_max_10(self):
        """Test that at most 10 claims are returned."""
        from vault.compiler import extract_claims
        lines = [f"- This is claim number {i} with enough length to be counted" for i in range(20)]
        content = "\n".join(lines)
        claims = extract_claims("Test", content)
        assert len(claims) == 10

    def test_extract_claims_from_paragraphs(self):
        """Test claim extraction from regular paragraphs."""
        from vault.compiler import extract_claims
        content = """This is a very long paragraph that contains a meaningful sentence.
It should be extracted as a claim because it's longer than 20 characters.

Thinking: this thought process line should be skipped entirely.
// Comment line should also be skipped.
"""
        claims = extract_claims("Test", content)
        assert len(claims) > 0

    def test_extract_claims_short_paragraph_skipped(self):
        """Test that short paragraphs (<= 20 chars) are skipped."""
        from vault.compiler import extract_claims
        content = "Short.\nVery short line.\n"
        claims = extract_claims("Test", content)
        assert len(claims) == 0

    def test_extract_claims_colon_value_format(self):
        """Test extraction of KEY:VALUE format items."""
        from vault.compiler import extract_claims
        content = """- 架構：模組化設計，分為核心層與擴充層
- 效能：單次查詢回應時間小於 100ms
- 安全：支援 AES-256 加密與權限管控
"""
        claims = extract_claims("Test", content)
        assert len(claims) > 0

    def test_extract_claims_long_items_truncated(self):
        """Test that very long claim items are truncated to 120 chars."""
        from vault.compiler import extract_claims
        long_text = "x" * 200
        content = f"- {long_text}\n"
        claims = extract_claims("Test", content)
        if claims:
            assert len(claims[0]["claim"]) <= 120


class TestSimpleAAAKCompressExtended:
    def test_simple_aaak_compress_with_claims(self):
        """Test AAAK compression includes CLAIMS section."""
        from vault.compiler import simple_aaak_compress
        content = """# Test Doc
- This is the first important claim about the system architecture
- This is the second claim about performance optimization
- This is the third claim about security measures
"""
        result = simple_aaak_compress("Test", content)
        assert "TITLE:" in result
        # Should have claims section since we have list items
        assert "CLAIMS:" in result

    def test_simple_aaak_compress_thinking_lines_skipped(self):
        """Test that thinking lines are skipped in AAAK compression."""
        from vault.compiler import simple_aaak_compress
        content = """# Title
思考: This is a thought process that should not appear
思考：Another thought in Chinese format
- This is a real content item that should appear
"""
        result = simple_aaak_compress("Test", content)
        assert "思考" not in result
        assert "real content" in result

    def test_simple_aaak_compress_code_blocks_skipped(self):
        """Test that code blocks are skipped."""
        from vault.compiler import simple_aaak_compress
        content = """# Title
```
def hello():
    print("world")
```
- Important point about the code
"""
        result = simple_aaak_compress("Test", content)
        assert "def hello" not in result

    def test_simple_aaak_compress_max_8_items(self):
        """Test AAAK compression respects max 8 items."""
        from vault.compiler import simple_aaak_compress
        content = "# Test\n"
        for i in range(15):
            content += f"- Item number {i} with enough content to be included\n"
        result = simple_aaak_compress("Test", content)
        # Count items (lines starting with "- ")
        item_lines = [l for l in result.split("\n") if l.startswith("- ") and "[" not in l]
        assert len(item_lines) <= 8

    def test_simple_aaak_compress_aaak_mapping(self):
        """Test that AAAK keyword mapping works."""
        from vault.compiler import simple_aaak_compress
        content = """# 架構設計
- 架構：採用分層架構設計
- 效能：優化查詢效能
- 安全：加強安全防護
"""
        result = simple_aaak_compress("Test", content)
        # Chinese keywords should be replaced with AAAK abbreviations
        assert "ARCH" in result or "PERF" in result or "SEC" in result

    def test_simple_aaak_compress_length_limit(self):
        """Test AAAK output is limited to 800 characters."""
        from vault.compiler import simple_aaak_compress
        # Generate very long content
        sections = []
        for i in range(20):
            section = f"## Section {i}\n"
            for j in range(5):
                section += f"- Point {j} with some detailed explanation text here\n"
            sections.append(section)
        content = "\n".join(sections)
        result = simple_aaak_compress("Test Title", content)
        assert len(result) <= 810  # some tolerance

class TestGenerateSummaryExtended:
    def test_generate_summary_from_list(self):
        """Test summary generation from list content."""
        from vault.compiler import generate_summary
        content = """- First important point about the topic
- Second point that adds more context
- Third point with additional details
"""
        summary = generate_summary(content, "Test")
        assert isinstance(summary, str)
        assert len(summary) > 0

    def test_generate_summary_from_numbered_list(self):
        """Test summary generation from numbered list."""
        from vault.compiler import generate_summary
        content = """1. First step is to prepare the environment
2. Second step is to install dependencies
3. Third step is to run the program
"""
        summary = generate_summary(content, "Test")
        assert isinstance(summary, str)
        assert len(summary) > 0

    def test_generate_summary_very_short_fallback(self):
        """Test summary falls back to title when content is too short."""
        from vault.compiler import generate_summary
        content = "Hi."
        summary = generate_summary(content, "My Title")
        assert summary == "My Title。"

    def test_generate_summary_no_title_fallback(self):
        """Test summary with no title and short content."""
        from vault.compiler import generate_summary
        summary = generate_summary("", "")
        assert isinstance(summary, str)

    def test_generate_summary_ends_with_punctuation(self):
        """Test summary ends with proper punctuation."""
        from vault.compiler import generate_summary
        content = "This is a complete sentence with enough length"
        summary = generate_summary(content, "Test")
        assert summary.endswith("。") or summary.endswith("！") or summary.endswith("？")

    def test_generate_summary_respects_max_chars(self):
        """Test summary respects max_chars limit strictly."""
        from vault.compiler import generate_summary
        content = "這是第一句很長的話，包含了很多內容。這是第二句話，也有不少內容。這是第三句話，繼續補充。"
        summary = generate_summary(content, "Test", max_chars=30)
        assert len(summary) <= 30

    def test_generate_summary_with_title_prefix(self):
        """Test summary skips TITLE: and CLAIMS: prefix lines."""
        from vault.compiler import generate_summary
        content = """TITLE:Some Title
CLAIMS:
- Claim 1
- Claim 2

This is actual content that should be in the summary.
"""
        summary = generate_summary(content, "Test")
        assert "TITLE:" not in summary
        assert "CLAIMS:" not in summary
        assert "actual content" in summary

    def test_generate_summary_multiple_sentences(self):
        """Test summary combines multiple sentences up to max_chars."""
        from vault.compiler import generate_summary
        content = "第一句話。第二句話。第三句話。第四句話。第五句話。"
        summary = generate_summary(content, "Test", max_chars=50)
        # Should include more than one sentence
        assert "。" in summary
        assert len(summary) <= 50


class TestClassifyContentExtended:
    def test_classify_content_error(self):
        """Test error classification."""
        from vault.compiler import classify_content
        content = "程式崩潰了，出現了bug，導致系統timeout和crash。"
        cat = classify_content(content, {})
        assert cat == "error"

    def test_classify_content_architecture(self):
        """Test architecture classification."""
        from vault.compiler import classify_content
        content = "系統架構設計採用分層模式，部署在雲端伺服器上。"
        cat = classify_content(content, {})
        assert cat == "architecture"

    def test_classify_content_technique(self):
        """Test technique classification."""
        from vault.compiler import classify_content
        content = "最佳實踐方法：按照步驟一步步操作，就能完成設定。"
        cat = classify_content(content, {})
        assert cat == "technique"

    def test_classify_content_decision(self):
        """Test decision classification."""
        from vault.compiler import classify_content
        content = "比較兩種方案的權衡取捨，根據偏好做出最佳選擇。"
        cat = classify_content(content, {})
        assert cat == "decision"

    def test_classify_content_general(self):
        """Test general classification for uncategorized content."""
        from vault.compiler import classify_content
        content = "今天天氣很好，適合出去散步。"
        cat = classify_content(content, {"source": "personal"})
        assert cat == "general"

    def test_classify_content_general_with_empty_source_metadata(self):
        """Empty source metadata must not bonus-match every category."""
        from vault.compiler import classify_content
        content = "今天天氣很好，適合出去散步。"
        cat = classify_content(content, {})
        assert cat == "general"

    def test_classify_content_source_bonus(self):
        """Test that source metadata gives bonus weight."""
        from vault.compiler import classify_content
        # Content is ambiguous but source matches "error"
        content = "有一些問題需要處理"
        cat_with_source = classify_content(content, {"source": "error-log"})
        cat_without_source = classify_content(content, {})
        # With source bonus, it might be classified differently
        assert isinstance(cat_with_source, str)
        assert isinstance(cat_without_source, str)


class TestAssignLayerExtended:
    def test_assign_layer_explicit_l0(self):
        """Test explicit L0 layer assignment."""
        from vault.compiler import assign_layer
        assert assign_layer({"layer": "L0"}) == "L0"

    def test_assign_layer_explicit_l3(self):
        """Test explicit L3 layer assignment."""
        from vault.compiler import assign_layer
        assert assign_layer({"layer": "L3"}) == "L3"

    def test_assign_layer_invalid_explicit(self):
        """Test invalid explicit layer falls through to other rules."""
        from vault.compiler import assign_layer
        # "L5" is not a valid layer, should fall through
        result = assign_layer({"layer": "L5"})
        assert result == "L3"  # default

    def test_assign_layer_from_source_l0(self):
        """Test layer inference from source path L0-identity."""
        from vault.compiler import assign_layer
        assert assign_layer({"source": "L0-identity/about.md"}) == "L0"

    def test_assign_layer_from_source_l1(self):
        """Test layer inference from source path L1-core-facts."""
        from vault.compiler import assign_layer
        assert assign_layer({"source": "L1-core-facts/python.md"}) == "L1"

    def test_assign_layer_from_source_l2(self):
        """Test layer inference from source path L2-context."""
        from vault.compiler import assign_layer
        assert assign_layer({"source": "L2-context/architecture.md"}) == "L2"

    def test_assign_layer_from_source_l3(self):
        """Test layer inference from source path L3-knowledge."""
        from vault.compiler import assign_layer
        assert assign_layer({"source": "L3-knowledge/random.md"}) == "L3"

    def test_assign_layer_from_category_error(self):
        """Test error category maps to L2."""
        from vault.compiler import assign_layer
        assert assign_layer({"category": "error"}) == "L2"

    def test_assign_layer_from_category_architecture(self):
        """Test architecture category maps to L2."""
        from vault.compiler import assign_layer
        assert assign_layer({"category": "architecture"}) == "L2"

    def test_assign_layer_from_category_general(self):
        """Test general category defaults to L3."""
        from vault.compiler import assign_layer
        assert assign_layer({"category": "general"}) == "L3"

    def test_assign_layer_default(self):
        """Test default layer is L3."""
        from vault.compiler import assign_layer
        assert assign_layer({}) == "L3"


class TestVaultCompiler:
    """Tests for VaultCompiler class."""

    def test_compiler_init(self, tmp_path):
        from vault.compiler import VaultCompiler
        compiler = VaultCompiler(project_dir=str(tmp_path))
        assert compiler.project_dir == tmp_path
        assert compiler.raw_dir == tmp_path / "raw"
        assert compiler.compiled_dir == tmp_path / "compiled"
        assert compiler.db is None
        assert compiler.embed is None

    def test_compiler_init_with_db(self, tmp_path):
        from vault.compiler import VaultCompiler
        from vault.db import VaultDB

        db_path = tmp_path / "test.db"
        db = VaultDB(str(db_path))
        db.connect()

        compiler = VaultCompiler(project_dir=str(tmp_path), db=db)
        assert compiler.db is db

        db.close()

    def test_compile_no_raw_dir(self, tmp_path, capsys):
        from vault.compiler import VaultCompiler

        compiler = VaultCompiler(project_dir=str(tmp_path))
        stats = compiler.compile()

        captured = capsys.readouterr()
        assert stats["total_files"] == 0
        assert "raw/ 目錄不存在" in captured.out or "raw/" in captured.out

    def test_compile_empty_raw_dir(self, tmp_path, capsys):
        from vault.compiler import VaultCompiler
        from vault.db import VaultDB

        # Create raw dir
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()

        # Create db
        db = VaultDB(str(tmp_path / "vault.db"))
        db.connect()

        compiler = VaultCompiler(project_dir=str(tmp_path), db=db)
        stats = compiler.compile()

        db.close()

        assert stats["total_files"] == 0
        assert stats["new"] == 0
        assert stats["skipped"] == 0

    def test_compile_new_file_with_frontmatter(self, tmp_path, capsys):
        from vault.compiler import VaultCompiler
        from vault.db import VaultDB

        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()

        # Create a test file with frontmatter
        test_md = raw_dir / "test_note.md"
        test_md.write_text("""---
title: Test Note
category: tech
layer: L2
tags: python,test
trust: 0.8
---

# Test Note Content

This is the content of the test note.
It has multiple lines.
""")

        db = VaultDB(str(tmp_path / "vault.db"))
        db.connect()

        compiler = VaultCompiler(project_dir=str(tmp_path), db=db)
        stats = compiler.compile()

        db.close()

        assert stats["total_files"] == 1
        assert stats["new"] == 1
        assert stats["updated"] == 0
        assert stats["skipped"] == 0
        assert stats["errors"] == 0

    def test_compile_auto_frontmatter(self, tmp_path, capsys):
        from vault.compiler import VaultCompiler
        from vault.db import VaultDB

        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()

        test_md = raw_dir / "auto-frontmatter-test.md"
        test_md.write_text("# Auto Frontmatter Test\n\nThis file has no frontmatter.\nIt should be auto-generated.\n")

        db = VaultDB(str(tmp_path / "vault.db"))
        db.connect()

        compiler = VaultCompiler(project_dir=str(tmp_path), db=db)
        stats = compiler.compile()

        captured = capsys.readouterr()

        db.close()

        assert stats["total_files"] == 1
        assert stats["new"] == 1
        assert "缺 frontmatter" in captured.out or "auto" in captured.out.lower()

    def test_compile_empty_file(self, tmp_path):
        from vault.compiler import VaultCompiler
        from vault.db import VaultDB

        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()

        test_md = raw_dir / "empty.md"
        test_md.write_text("---\ntitle: Empty\n---\n\n   \n\n")

        db = VaultDB(str(tmp_path / "vault.db"))
        db.connect()

        compiler = VaultCompiler(project_dir=str(tmp_path), db=db)
        stats = compiler.compile()

        db.close()

        assert stats["total_files"] == 1
        assert stats["skipped"] == 1

    def test_compile_dry_run(self, tmp_path):
        from vault.compiler import VaultCompiler
        from vault.db import VaultDB

        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()

        test_md = raw_dir / "dryrun.md"
        test_md.write_text("# Dry Run Test\n\nContent for dry run.\n")

        db = VaultDB(str(tmp_path / "vault.db"))
        db.connect()

        compiler = VaultCompiler(project_dir=str(tmp_path), db=db)
        stats = compiler.compile(dry_run=True)

        # Check no entries were added
        count = db.conn.execute("SELECT COUNT(*) as cnt FROM knowledge").fetchone()
        db.close()

        assert stats["total_files"] == 1
        assert stats["new"] == 1  # dry_run still returns new/updated stats but doesn't write
        assert count["cnt"] == 0  # No actual entries in dry run

    def test_compile_update_existing(self, tmp_path):
        from vault.compiler import VaultCompiler
        from vault.db import VaultDB

        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()

        test_md = raw_dir / "update_test.md"
        test_md.write_text("# Update Test\n\nOriginal content.\n")

        db = VaultDB(str(tmp_path / "vault.db"))
        db.connect()

        compiler = VaultCompiler(project_dir=str(tmp_path), db=db)

        # First compile
        stats1 = compiler.compile()
        assert stats1["new"] == 1

        # Update content
        test_md.write_text("# Update Test\n\nUpdated content here.\n")

        # Second compile
        stats2 = compiler.compile()
        assert stats2["updated"] == 1
        assert stats2["new"] == 0

        db.close()

    def test_compile_skipped_unchanged(self, tmp_path):
        from vault.compiler import VaultCompiler
        from vault.db import VaultDB

        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()

        test_md = raw_dir / "skip_test.md"
        test_md.write_text("# Skip Test\n\nContent that stays the same.\n")

        db = VaultDB(str(tmp_path / "vault.db"))
        db.connect()

        compiler = VaultCompiler(project_dir=str(tmp_path), db=db)

        # First compile
        stats1 = compiler.compile()
        assert stats1["new"] == 1

        # Second compile (no changes)
        stats2 = compiler.compile()
        assert stats2["skipped"] == 1
        assert stats2["new"] == 0
        assert stats2["updated"] == 0

        db.close()

    def test_compile_multiple_files(self, tmp_path):
        from vault.compiler import VaultCompiler
        from vault.db import VaultDB

        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()

        # Create subdirectory
        sub_dir = raw_dir / "subfolder"
        sub_dir.mkdir()

        # Create multiple files
        (raw_dir / "file1.md").write_text("# File 1\n\nContent one.\n")
        (raw_dir / "file2.md").write_text("# File 2\n\nContent two.\n")
        (sub_dir / "file3.md").write_text("# File 3\n\nContent three.\n")

        db = VaultDB(str(tmp_path / "vault.db"))
        db.connect()

        compiler = VaultCompiler(project_dir=str(tmp_path), db=db)
        stats = compiler.compile()

        db.close()

        assert stats["total_files"] == 3
        assert stats["new"] == 3

    def test_compile_tags_list(self, tmp_path):
        """Test that list-style tags are handled correctly."""
        from vault.compiler import VaultCompiler
        from vault.db import VaultDB

        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()

        test_md = raw_dir / "tags_test.md"
        test_md.write_text("""---
title: Tags Test
tags:
  - tag1
  - tag2
  - tag3
---

# Tags Test

Content.
""")

        db = VaultDB(str(tmp_path / "vault.db"))
        db.connect()

        compiler = VaultCompiler(project_dir=str(tmp_path), db=db)
        stats = compiler.compile()

        # Check the entry has tags
        entry = db.conn.execute("SELECT tags FROM knowledge WHERE title = ?", ("Tags Test",)).fetchone()
        db.close()

        assert stats["new"] == 1
        assert "tag1" in entry["tags"]
        assert "tag2" in entry["tags"]
        assert "tag3" in entry["tags"]

    def test_compile_sanitizes_category_output_path(self, tmp_path):
        from vault.compiler import VaultCompiler
        from vault.db import VaultDB

        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()
        test_md = raw_dir / "escape.md"
        test_md.write_text("""---
title: Escape Test
category: ../../outside
---

Content should stay inside compiled.
""")

        db = VaultDB(str(tmp_path / "vault.db"))
        db.connect()

        compiler = VaultCompiler(project_dir=str(tmp_path), db=db)
        stats = compiler.compile()
        db.close()

        assert stats["new"] == 1
        assert not (tmp_path / "outside").exists()
        assert (tmp_path / "compiled" / "L3-outside" / "Escape_Test.md").exists()

    def test_compile_skips_raw_symlink(self, tmp_path):
        from vault.compiler import VaultCompiler
        from vault.db import VaultDB

        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()
        outside = tmp_path / "outside.md"
        outside.write_text("# Secret outside raw\n\nDo not compile me.")
        symlink = raw_dir / "linked.md"
        try:
            symlink.symlink_to(outside)
        except OSError:
            pytest.skip("symlink not supported on this filesystem")

        db = VaultDB(str(tmp_path / "vault.db"))
        db.connect()

        compiler = VaultCompiler(project_dir=str(tmp_path), db=db)
        stats = compiler.compile()
        rows = db.list_knowledge()
        db.close()

        assert stats["total_files"] == 0
        assert rows == []

    def test_compile_blocks_privacy_fail_raw_file(self, tmp_path):
        from vault.compiler import VaultCompiler
        from vault.db import VaultDB

        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()
        (raw_dir / "secret.md").write_text("""---
title: Secret Test
---

password = supersecret123
""")

        db = VaultDB(str(tmp_path / "vault.db"))
        db.connect()

        compiler = VaultCompiler(project_dir=str(tmp_path), db=db)
        stats = compiler.compile()
        rows = db.list_knowledge()
        db.close()

        assert stats["errors"] == 1
        assert rows == []

    def test_compile_allow_private_overrides_privacy_gate(self, tmp_path):
        from vault.compiler import VaultCompiler
        from vault.db import VaultDB

        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()
        (raw_dir / "secret.md").write_text("""---
title: Allowed Secret Test
---

password = supersecret123
""")

        db = VaultDB(str(tmp_path / "vault.db"))
        db.connect()

        compiler = VaultCompiler(project_dir=str(tmp_path), db=db, allow_private=True)
        stats = compiler.compile()
        rows = db.list_knowledge()
        db.close()

        assert stats["new"] == 1
        assert rows[0]["title"] == "Allowed Secret Test"

    def test_backfill_summaries(self, tmp_path, capsys):
        """Test _backfill_summaries method."""
        from vault.compiler import VaultCompiler
        from vault.db import VaultDB

        db = VaultDB(str(tmp_path / "vault.db"))
        db.connect()

        # Add an entry without a summary
        kid = db.add_knowledge(
            title="Summary Test",
            content_raw="This is a test content for summary generation. It has multiple sentences and should produce a reasonable summary.",
            layer="L3",
            category="test",
        )

        compiler = VaultCompiler(project_dir=str(tmp_path), db=db)
        compiler._backfill_summaries({})

        entry = db.conn.execute("SELECT summary FROM knowledge WHERE id = ?", (kid,)).fetchone()
        db.close()

        captured = capsys.readouterr()
        assert "補 1/1" in captured.out
        assert entry["summary"] is not None
        assert len(entry["summary"]) > 0
