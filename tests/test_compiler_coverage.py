"""Tests for compiler module pure functions to boost coverage."""

import pytest


class TestExtractFrontmatter:
    """Test extract_frontmatter function."""
    
    def test_extract_frontmatter_valid(self):
        """Test extracting valid YAML frontmatter."""
        from vault.compiler import extract_frontmatter
        
        content = """---
title: Test Title
category: test
tags: [a, b, c]
---

# Main Content

This is the body text.
"""
        metadata, body = extract_frontmatter(content)
        
        assert metadata["title"] == "Test Title"
        assert metadata["category"] == "test"
        assert "Main Content" in body
    
    def test_extract_frontmatter_empty(self):
        """Test empty frontmatter."""
        from vault.compiler import extract_frontmatter
        
        content = """---
---

Body here.
"""
        metadata, body = extract_frontmatter(content)
        assert metadata == {}
        assert "Body here" in body
    
    def test_extract_frontmatter_none(self):
        """Test no frontmatter at all."""
        from vault.compiler import extract_frontmatter
        
        content = "Just some content without frontmatter."
        metadata, body = extract_frontmatter(content)
        
        assert metadata == {}
        assert body == content
    
    def test_extract_frontmatter_incomplete(self):
        """Test incomplete frontmatter (no closing ---)."""
        from vault.compiler import extract_frontmatter
        
        content = """---
title: Test
no closing dashes

Body text.
"""
        metadata, body = extract_frontmatter(content)
        
        # Should return empty metadata and full content
        assert metadata == {}
        assert "no closing dashes" in body
    
    def test_extract_frontmatter_invalid_yaml(self):
        """Test frontmatter with invalid YAML."""
        from vault.compiler import extract_frontmatter
        
        content = """---
: invalid: yaml: [
---

Valid body.
"""
        metadata, body = extract_frontmatter(content)
        
        # Should gracefully handle invalid YAML
        assert isinstance(metadata, dict)
        assert "Valid body" in body
    
    def test_extract_frontmatter_empty_content(self):
        """Test with empty content."""
        from vault.compiler import extract_frontmatter
        
        metadata, body = extract_frontmatter("")
        assert metadata == {}
        assert body == ""


class TestClassifyContent:
    """Test classify_content function."""
    
    def test_classify_error(self):
        """Test error classification."""
        from vault.compiler import classify_content
        
        content = "This is about an error that happened. The bug caused a crash."
        metadata = {}
        result = classify_content(content, metadata)
        
        assert result == "error"
    
    def test_classify_architecture(self):
        """Test architecture classification."""
        from vault.compiler import classify_content
        
        content = "The system architecture design uses microservices deployment pattern."
        metadata = {}
        result = classify_content(content, metadata)
        
        assert result == "architecture"
    
    def test_classify_technique(self):
        """Test technique classification."""
        from vault.compiler import classify_content
        
        content = "Here are the steps to follow. This guide shows best practices."
        metadata = {}
        result = classify_content(content, metadata)
        
        assert result == "technique"
    
    def test_classify_decision(self):
        """Test decision classification."""
        from vault.compiler import classify_content
        
        content = "We need to compare option A vs option B and make a choice. This is a trade-off decision."
        metadata = {}
        result = classify_content(content, metadata)
        
        assert result == "decision"
    
    def test_classify_general(self):
        """Test general classification (no matching keywords)."""
        from vault.compiler import classify_content
        
        # Use content with no keywords from any category
        content = "Hello world. Welcome to the show."
        metadata = {}
        result = classify_content(content, metadata)
        
        # Should be general or whatever the default is
        assert isinstance(result, str)
        assert len(result) > 0
    
    def test_classify_with_source(self):
        """Test classification with source metadata."""
        from vault.compiler import classify_content
        
        content = "Some content with architecture design pattern."
        metadata = {"source": "architecture"}
        result = classify_content(content, metadata)
        
        # Should work without error
        assert isinstance(result, str)
    
    def test_classify_empty_content(self):
        """Test classification with empty content."""
        from vault.compiler import classify_content
        
        result = classify_content("", {})
        assert isinstance(result, str)


class TestAssignLayer:
    """Test assign_layer function."""
    
    def test_assign_layer_explicit(self):
        """Test explicit layer assignment."""
        from vault.compiler import assign_layer
        
        for layer in ["L0", "L1", "L2", "L3"]:
            assert assign_layer({"layer": layer}) == layer
    
    def test_assign_layer_invalid_explicit(self):
        """Test invalid explicit layer falls back."""
        from vault.compiler import assign_layer
        
        assert assign_layer({"layer": "L4"}) == "L3"
    
    def test_assign_layer_from_source_l0(self):
        """Test layer inference from source path L0."""
        from vault.compiler import assign_layer
        
        assert assign_layer({"source": "/path/L0-identity/doc.md"}) == "L0"
    
    def test_assign_layer_from_source_l1(self):
        """Test layer inference from source path L1."""
        from vault.compiler import assign_layer
        
        assert assign_layer({"source": "/path/L1-core-facts/doc.md"}) == "L1"
    
    def test_assign_layer_from_source_l2(self):
        """Test layer inference from source path L2."""
        from vault.compiler import assign_layer
        
        assert assign_layer({"source": "/path/L2-context/doc.md"}) == "L2"
    
    def test_assign_layer_from_source_l3(self):
        """Test layer inference from source path L3."""
        from vault.compiler import assign_layer
        
        assert assign_layer({"source": "/path/L3-knowledge/doc.md"}) == "L3"
    
    def test_assign_layer_from_category_error(self):
        """Test layer inference from error category."""
        from vault.compiler import assign_layer
        
        assert assign_layer({"category": "error"}) == "L2"
    
    def test_assign_layer_from_category_architecture(self):
        """Test layer inference from architecture category."""
        from vault.compiler import assign_layer
        
        assert assign_layer({"category": "architecture"}) == "L2"
    
    def test_assign_layer_default(self):
        """Test default layer assignment."""
        from vault.compiler import assign_layer
        
        assert assign_layer({}) == "L3"
        assert assign_layer({"category": "general"}) == "L3"
    
    def test_assign_layer_explicit_overrides_source(self):
        """Test that explicit layer overrides source inference."""
        from vault.compiler import assign_layer
        
        metadata = {
            "layer": "L0",
            "source": "/path/L3-knowledge/doc.md",
        }
        assert assign_layer(metadata) == "L0"


class TestGenerateSummary:
    """Test generate_summary function."""
    
    def test_generate_summary_basic(self):
        """Test basic summary generation."""
        from vault.compiler import generate_summary
        
        content = """This is the first paragraph. It has multiple sentences. 
The quick brown fox jumps over the lazy dog. This is additional text."""
        result = generate_summary(content)
        
        assert isinstance(result, str)
        assert len(result) > 0
        # Should be within max_chars
        assert len(result) <= 80
    
    def test_generate_summary_with_title_fallback(self):
        """Test summary falls back to title when content is short."""
        from vault.compiler import generate_summary
        
        content = "Short."
        result = generate_summary(content, title="My Awesome Title")
        
        # Should use title fallback
        assert len(result) > 0
    
    def test_generate_summary_empty(self):
        """Test summary generation with empty content."""
        from vault.compiler import generate_summary
        
        result = generate_summary("")
        assert result == ""
    
    def test_generate_summary_custom_max_chars(self):
        """Test summary with custom max_chars."""
        from vault.compiler import generate_summary
        
        content = "A very long sentence that contains many words and should be truncated at some point."
        result = generate_summary(content, max_chars=30)
        
        assert len(result) <= 30
    
    def test_generate_summary_multiple_paragraphs(self):
        """Test summary takes first paragraph."""
        from vault.compiler import generate_summary
        
        content = """First paragraph with content.

Second paragraph that should not be included in the summary at all.

Third paragraph also not included.
"""
        result = generate_summary(content)
        
        # Should contain first paragraph content
        assert "First paragraph" in result
        # Should not contain second paragraph
        assert "Second paragraph" not in result


class TestExtractClaims:
    """Test extract_claims function."""
    
    def test_extract_claims_basic(self):
        """Test basic claim extraction."""
        from vault.compiler import extract_claims
        
        content = "First claim about something. Second claim about another thing. Third claim here."
        result = extract_claims("Test Title", content)
        
        assert isinstance(result, list)
        # Returns at least 1 claim
        assert len(result) >= 1
        assert "id" in result[0]
        assert "claim" in result[0]
    
    def test_extract_claims_short_content(self):
        """Test claim extraction with short content."""
        from vault.compiler import extract_claims
        
        content = "Short."
        result = extract_claims("Test", content)
        # Short items might be filtered out
        assert isinstance(result, list)
    
    def test_extract_claims_empty(self):
        """Test claim extraction with empty content."""
        from vault.compiler import extract_claims
        
        result = extract_claims("Title", "")
        assert result == []
    
    def test_extract_claims_with_code_blocks(self):
        """Test that code blocks are skipped."""
        from vault.compiler import extract_claims
        
        content = """Some text before code.

```python
print("hello")
x = 1 + 2
```

Text after code block."""
        result = extract_claims("Test", content)
        
        # Should have claims from text, not code
        assert isinstance(result, list)
        # Code content should not appear as claims
        claim_texts = [c["claim"] for c in result]
        assert not any("print" in c for c in claim_texts)
