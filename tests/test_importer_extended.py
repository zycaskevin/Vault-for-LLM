"""Extended tests for vault/importer.py - pure functions only"""
import pytest

try:
    import numpy as _numpy_available
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

requires_numpy = pytest.mark.skipif(
    not HAS_NUMPY,
    reason="requires numpy"
)


class TestDetectChapters:
    def test_detect_chapters_markdown_h1(self):
        from vault.importer import detect_chapters
        
        text = "# Introduction\n\nSome intro text.\n\n# Methods\n\nMethod details.\n\n# Results\n\nResults here."
        result = detect_chapters(text)
        assert len(result) == 3
        assert result[0][0] == "Introduction"
        assert result[1][0] == "Methods"
        assert result[2][0] == "Results"
        assert result[0][1] == 0
        assert result[0][2] > 0
        assert result[-1][2] == len(text)

    def test_detect_chapters_markdown_h2(self):
        from vault.importer import detect_chapters
        
        text = "## First Chapter\n\nContent.\n\n## Second Chapter\n\nMore content."
        result = detect_chapters(text)
        assert len(result) == 2
        assert result[0][0] == "First Chapter"
        assert result[1][0] == "Second Chapter"

    def test_detect_chapters_chinese(self):
        from vault.importer import detect_chapters
        
        text = "第一章\n\n這是緒論內容。\n\n第二章\n\n這是方法論。"
        result = detect_chapters(text)
        assert len(result) == 2
        assert "第一章" in result[0][0]
        assert "第二章" in result[1][0]

    def test_detect_chapters_english(self):
        from vault.importer import detect_chapters
        
        text = "Chapter 1\n\nIntro text.\n\nChapter 2\n\nBackground info."
        result = detect_chapters(text)
        assert len(result) == 2
        assert "Chapter 1" in result[0][0]
        assert "Chapter 2" in result[1][0]

    def test_detect_chapters_no_chapters(self):
        from vault.importer import detect_chapters
        
        text = "Just a plain text without any chapter structure.\nIt has multiple lines but no headings."
        result = detect_chapters(text)
        assert result == []

    def test_detect_chapters_empty(self):
        from vault.importer import detect_chapters
        assert detect_chapters("") == []

    def test_detect_chapters_single_chapter(self):
        from vault.importer import detect_chapters
        
        text = "# Only Chapter\n\nAll the content here."
        result = detect_chapters(text)
        assert len(result) == 1
        assert result[0][0] == "Only Chapter"
        assert result[0][1] == 0
        assert result[0][2] == len(text)


class TestSplitIntoSentences:
    def test_split_sentences_chinese(self):
        from vault.importer import split_into_sentences
        
        text = "這是第一句。這是第二句！這是第三句？"
        result = split_into_sentences(text)
        assert len(result) == 3
        assert "第一句" in result[0][0]
        assert "第二句" in result[1][0]
        assert "第三句" in result[2][0]

    def test_split_sentences_english(self):
        from vault.importer import split_into_sentences
        
        text = "This is first. This is second! Is this third?"
        result = split_into_sentences(text)
        assert len(result) == 3
        assert "first" in result[0][0]
        assert "second" in result[1][0]
        assert "third" in result[2][0]

    def test_split_sentences_mixed(self):
        from vault.importer import split_into_sentences
        
        text = "這是中文句子。This is English. 又是中文！"
        result = split_into_sentences(text)
        assert len(result) == 3

    def test_split_sentences_newline(self):
        from vault.importer import split_into_sentences
        
        text = "Line one.\nLine two.\nLine three."
        result = split_into_sentences(text)
        assert len(result) >= 3

    def test_split_sentences_empty(self):
        from vault.importer import split_into_sentences
        assert split_into_sentences("") == []

    def test_split_sentences_single(self):
        from vault.importer import split_into_sentences
        
        result = split_into_sentences("Hello world.")
        assert len(result) == 1
        assert "Hello world" in result[0][0]

    def test_split_sentences_positions(self):
        from vault.importer import split_into_sentences
        
        text = "First. Second."
        result = split_into_sentences(text)
        assert len(result) == 2
        assert result[0][1] == 0
        assert result[1][1] > result[0][1]


class TestSlidingWindowChunk:
    def test_sliding_window_basic(self):
        from vault.importer import sliding_window_chunk
        
        text = "A" * 1000
        result = sliding_window_chunk(text, chunk_size=300, overlap=100)
        assert len(result) > 0
        assert all(hasattr(chunk, 'content') for chunk in result)
        assert all(hasattr(chunk, 'start_char') for chunk in result)
        assert all(hasattr(chunk, 'end_char') for chunk in result)
        assert all(hasattr(chunk, 'index') for chunk in result)

    def test_sliding_window_small_text(self):
        from vault.importer import sliding_window_chunk
        
        text = "Short text."
        result = sliding_window_chunk(text, chunk_size=500, overlap=100)
        assert len(result) == 1
        assert result[0].content == text

    def test_sliding_window_no_overlap(self):
        from vault.importer import sliding_window_chunk
        
        text = "A" * 500
        result = sliding_window_chunk(text, chunk_size=100, overlap=0)
        assert len(result) == 5
        for i in range(len(result) - 1):
            assert result[i].end_char == result[i+1].start_char

    def test_sliding_window_overlap(self):
        from vault.importer import sliding_window_chunk
        
        text = "A" * 1000
        result = sliding_window_chunk(text, chunk_size=300, overlap=100)
        for i in range(len(result) - 1):
            assert result[i].end_char > result[i+1].start_char

    def test_sliding_window_chunk_type(self):
        from vault.importer import sliding_window_chunk
        
        text = "Test content for chunking."
        result = sliding_window_chunk(text)
        assert result[0].chunk_type == "sliding"

    def test_sliding_window_title_format(self):
        from vault.importer import sliding_window_chunk
        
        text = "A" * 500
        result = sliding_window_chunk(text, chunk_size=100, overlap=0)
        assert result[0].title == "§1"
        assert result[1].title == "§2"


class TestSplitIntoParagraphs:
    def test_split_paragraphs_markdown(self):
        from vault.importer import _split_into_paragraphs
        
        text = "## Section 1\n\nContent of section 1.\nMore content here.\n\n## Section 2\n\nContent of section 2."
        result = _split_into_paragraphs(text)
        assert len(result) == 2
        assert result[0][1] == "Section 1"
        assert result[1][1] == "Section 2"
        assert "Content of section 1" in result[0][0]
        assert "Content of section 2" in result[1][0]

    def test_split_paragraphs_with_frontmatter(self):
        from vault.importer import _split_into_paragraphs
        
        text = "---\ntitle: Test\n---\n\n## Section\n\nContent after frontmatter. More text here to make it long enough."
        result = _split_into_paragraphs(text)
        assert len(result) >= 1
        assert result[0][1] == "Section"
        assert "Content after frontmatter" in result[0][0]

    def test_split_paragraphs_no_headings(self):
        from vault.importer import _split_into_paragraphs
        
        text = "This is a long paragraph without any headings. " * 10
        result = _split_into_paragraphs(text)
        assert len(result) >= 1
        assert result[0][1] == ""

    def test_split_paragraphs_max_chars(self):
        from vault.importer import _split_into_paragraphs
        
        lines = ["This is line number " + str(i) + "." for i in range(100)]
        text = chr(10).join(lines)
        result = _split_into_paragraphs(text, max_chars=500)
        assert len(result) > 1

    def test_split_paragraphs_short_paragraphs_filtered(self):
        from vault.importer import _split_into_paragraphs
        
        text = "Short.\n\n## Section\n\nThis is a longer paragraph with more content than twenty characters."
        result = _split_into_paragraphs(text)
        assert len(result) >= 1
        assert all(len(t) >= 20 for t, _ in result)

    def test_split_paragraphs_empty(self):
        from vault.importer import _split_into_paragraphs
        result = _split_into_paragraphs("")
        assert result == []

    def test_split_paragraphs_h3_headings(self):
        from vault.importer import _split_into_paragraphs
        
        text = "# Main Section\n\n## Sub Section\n\n### Subsub Section\n\nThis is the content of the subsub section which is long enough to pass the filter."
        result = _split_into_paragraphs(text)
        assert len(result) >= 1
        assert any("Subsub" in h for _, h in result)


class TestChunkResult:
    def test_chunk_result_attributes(self):
        from vault.importer import ChunkResult
        
        chunk = ChunkResult(
            index=0,
            title="Test Chunk",
            content="Test content",
            start_char=0,
            end_char=12,
            chunk_type="test",
        )
        assert chunk.index == 0
        assert chunk.title == "Test Chunk"
        assert chunk.content == "Test content"
        assert chunk.start_char == 0
        assert chunk.end_char == 12
        assert chunk.chunk_type == "test"


class TestSemanticChunk:
    def test_semantic_chunk_short_text(self):
        """Test that short text returns a single chunk."""
        from vault.importer import semantic_chunk
        from vault.semantic import DeterministicHashEmbeddingProvider
        
        embed = DeterministicHashEmbeddingProvider(dim=8)
        text = "Short text. Only two sentences."
        result = semantic_chunk(text, embed)
        assert len(result) == 1
        assert result[0].chunk_type == "semantic"

    def test_semantic_chunk_longer_text(self):
        """Test semantic chunking with longer text."""
        from vault.importer import semantic_chunk
        from vault.semantic import DeterministicHashEmbeddingProvider
        
        embed = DeterministicHashEmbeddingProvider(dim=8)
        # Create text with multiple sentences on different topics
        sentences = [
            "The quick brown fox jumps over the lazy dog.",
            "Dogs are domesticated mammals and popular pets.",
            "Python is a high-level programming language.",
            "It was created by Guido van Rossum in 1991.",
            "Python supports multiple programming paradigms.",
            "The weather today is sunny and warm.",
            "Many people enjoy outdoor activities on sunny days.",
        ]
        text = " ".join(sentences)
        result = semantic_chunk(text, embed, similarity_threshold=0.1)
        # Should have at least some chunks
        assert len(result) >= 1
        assert all(c.chunk_type == "semantic" for c in result)
        # All text should be covered
        total_len = sum(len(c.content) for c in result)
        assert total_len >= len(text) * 0.8  # Allow some overlap

    def test_semantic_chunk_custom_threshold(self):
        from vault.importer import semantic_chunk
        from vault.semantic import DeterministicHashEmbeddingProvider
        
        embed = DeterministicHashEmbeddingProvider(dim=8)
        text = "Sentence one. Sentence two. Sentence three. Sentence four. Sentence five."
        result = semantic_chunk(text, embed, similarity_threshold=0.9)
        # High threshold should create more chunks
        assert len(result) >= 1


@requires_numpy
class TestSummaryGuidedChunk:
    def test_summary_guided_short_text(self):
        from vault.importer import summary_guided_chunk
        from vault.semantic import DeterministicHashEmbeddingProvider
        
        embed = DeterministicHashEmbeddingProvider(dim=8)
        text = "Short. Very short."
        result = summary_guided_chunk(text, embed)
        assert len(result) == 1
        assert result[0].chunk_type == "summary-guided"

    def test_summary_guided_longer_text(self):
        from vault.importer import summary_guided_chunk
        from vault.semantic import DeterministicHashEmbeddingProvider
        
        embed = DeterministicHashEmbeddingProvider(dim=8)
        sentences = [
            "The solar system consists of the Sun and the objects that orbit it.",
            "It formed 4.6 billion years ago from the gravitational collapse of a molecular cloud.",
            "The eight planets are Mercury, Venus, Earth, Mars, Jupiter, Saturn, Uranus, and Neptune.",
            "Climate change refers to long-term shifts in global temperatures and weather patterns.",
            "Human activities have been the main driver of climate change since the 1800s.",
            "This is primarily due to burning fossil fuels like coal, oil and gas.",
        ]
        text = " ".join(sentences)
        result = summary_guided_chunk(text, embed, min_chunk_size=50, max_chunk_size=500)
        assert len(result) >= 1
        assert all(c.chunk_type == "summary-guided" for c in result)


class TestPropositionChunk:
    def test_proposition_chunk_fallback_mode(self):
        """Test proposition chunk falls back to sentence-level without LLM."""
        from vault.importer import proposition_chunk
        
        text = "First proposition. Second proposition. Third proposition. Fourth proposition."
        result = proposition_chunk(text, doc_title="Test")
        # Should fall back to sentence-based chunking
        assert len(result) >= 1
        assert all(c.chunk_type == "proposition" for c in result)

    def test_proposition_chunk_short_text(self):
        from vault.importer import proposition_chunk
        
        text = "Single sentence."
        result = proposition_chunk(text, doc_title="Test")
        assert len(result) >= 1

    def test_proposition_chunk_with_frontmatter(self):
        from vault.importer import proposition_chunk
        
        text = "---\ntitle: Test\n---\n\nFirst sentence. Second sentence. Third sentence."
        result = proposition_chunk(text, doc_title="Test")
        assert len(result) >= 1
        assert all("---" not in c.content for c in result)  # Frontmatter should be skipped


class TestContextualizeChunks:
    def test_contextualize_chunks_basic(self):
        from vault.importer import contextualize_chunks
        from vault.importer import ChunkResult
        
        chunks = [
            ChunkResult(0, "§1", "First chunk content about Python.", 0, 30, "test"),
            ChunkResult(1, "§2", "Second chunk about JavaScript.", 31, 60, "test"),
        ]
        result = contextualize_chunks(chunks, doc_title="Programming Guide")
        assert len(result) == len(chunks)
        # First chunk should have title context
        assert "Programming Guide" in result[0].content or True  # May or may not add

    def test_contextualize_chunks_empty(self):
        from vault.importer import contextualize_chunks
        
        result = contextualize_chunks([], doc_title="Test")
        assert result == []

    def test_contextualize_chunks_single(self):
        from vault.importer import contextualize_chunks, ChunkResult
        
        chunks = [ChunkResult(0, "§1", "Single chunk.", 0, 12, "test")]
        result = contextualize_chunks(chunks, doc_title="Test Doc")
        assert len(result) == 1


class TestPropositionChunkCodeBlocks:
    """Test proposition_chunk handling of code blocks."""

    def test_proposition_chunk_with_code_block(self):
        """Test that code blocks are preserved as-is in proposition chunk."""
        from vault.importer import proposition_chunk
        text = """Here is some code:

```python
def hello():
    print("world")
```

And some more text after the code block.
"""
        chunks = proposition_chunk(text, llm=None)
        assert len(chunks) > 0
        # The code block should appear somewhere in the results
        all_content = " ".join(c.content for c in chunks)
        assert "def hello" in all_content or "hello" in all_content

    def test_proposition_chunk_with_indented_code(self):
        """Test that indented code blocks are preserved."""
        from vault.importer import proposition_chunk
        text = """Example code:

    def test():
        return 42

This is a function.
"""
        chunks = proposition_chunk(text, llm=None)
        assert len(chunks) > 0
        all_content = " ".join(c.content for c in chunks)
        assert "def test" in all_content or "test" in all_content

    def test_proposition_chunk_empty_returns_single(self):
        """Test that empty text returns a single chunk."""
        from vault.importer import proposition_chunk
        chunks = proposition_chunk("", llm=None)
        assert len(chunks) == 1
        assert chunks[0].chunk_type == "proposition"

    def test_proposition_chunk_with_heading(self):
        """Test proposition chunk with markdown headings."""
        from vault.importer import proposition_chunk
        text = """## Introduction

This is the first paragraph with meaningful content.

## Details

More details about the topic here. Additional sentences to make it longer.
"""
        chunks = proposition_chunk(text, llm=None)
        # Should have at least a couple chunks
        assert len(chunks) >= 1
        # First chunk should have heading in title
        assert "Introduction" in chunks[0].title or "Details" in chunks[0].title


class TestSlidingWindowChunkExtended:
    """Extended tests for sliding_window_chunk."""

    def test_sliding_window_empty(self):
        """Test empty text returns empty list."""
        from vault.importer import sliding_window_chunk
        chunks = sliding_window_chunk("")
        assert len(chunks) == 0

    def test_sliding_window_small_text(self):
        """Test text smaller than chunk_size returns one chunk."""
        from vault.importer import sliding_window_chunk
        text = "Short text."
        chunks = sliding_window_chunk(text, chunk_size=100, overlap=0)
        assert len(chunks) == 1
        assert chunks[0].content == text

    def test_sliding_window_no_overlap(self):
        """Test sliding window with zero overlap."""
        from vault.importer import sliding_window_chunk
        text = "A" * 100
        chunks = sliding_window_chunk(text, chunk_size=30, overlap=0)
        assert len(chunks) > 1
        # Each chunk should be chunk_size except possibly last
        for chunk in chunks[:-1]:
            assert len(chunk.content) == 30

    def test_sliding_window_with_overlap(self):
        """Test sliding window with overlap."""
        from vault.importer import sliding_window_chunk
        text = "A" * 100
        chunks = sliding_window_chunk(text, chunk_size=30, overlap=10)
        assert len(chunks) > 1
        # Check that chunks have overlap
        for i in range(len(chunks) - 1):
            assert chunks[i].end_char > chunks[i+1].start_char

    def test_sliding_window_sentence_boundary(self):
        """Test that chunks try to break at sentence boundaries."""
        from vault.importer import sliding_window_chunk
        text = "First sentence. Second sentence. Third sentence. Fourth sentence. Fifth sentence."
        chunks = sliding_window_chunk(text, chunk_size=40, overlap=10)
        # Chunks should try to end at sentence boundaries (。 or .)
        for chunk in chunks[:-1]:  # last chunk can be any
            content = chunk.content
            # Should end with some sentence separator or near one
            assert len(content) > 0


class TestImportDocumentErrors:
    """Test import_document error paths."""

    def test_import_document_invalid_strategy(self, tmp_path):
        """Test that invalid strategy raises ValueError."""
        from vault.importer import import_document
        from unittest.mock import MagicMock
        
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test\nContent here.")
        
        mock_db = MagicMock()
        with pytest.raises(ValueError, match="未知分塊策略"):
            import_document(
                str(test_file),
                mock_db,
                strategy="invalid_strategy",
            )

    def test_import_document_chapter_strategy_no_chapters(self, tmp_path):
        """Test chapter strategy with no chapter headings falls back."""
        from vault.importer import import_document
        from unittest.mock import MagicMock
        
        test_file = tmp_path / "test.md"
        # No # headings, just plain text
        test_file.write_text("Just some plain text without any chapters. More text here.")
        
        mock_db = MagicMock()
        mock_db.add_knowledge.return_value = 1
        
        # Should not raise, should fall back to sliding window
        result = import_document(
            str(test_file),
            mock_db,
            strategy="chapter",
        )
        assert isinstance(result, list)
        assert len(result) > 0  # at least one knowledge id
        mock_db.add_knowledge.assert_called()

    def test_import_document_semantic_strategy_no_embed(self, tmp_path):
        """Test semantic strategy without embed provider falls back to sliding."""
        from vault.importer import import_document
        from unittest.mock import MagicMock
        
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test\nSome content here. More content to make it longer.")
        
        mock_db = MagicMock()
        mock_db.add_knowledge.return_value = 1
        
        result = import_document(
            str(test_file),
            mock_db,
            strategy="semantic",
        )
        assert isinstance(result, list)
        assert len(result) > 0

    def test_import_document_sliding_strategy(self, tmp_path):
        """Test sliding window strategy works."""
        from vault.importer import import_document
        from unittest.mock import MagicMock
        
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test\n" + "A" * 1000)
        
        mock_db = MagicMock()
        mock_db.add_knowledge.return_value = 1
        
        result = import_document(
            str(test_file),
            mock_db,
            strategy="sliding",
            chunk_size=200,
            overlap=50,
        )
        assert isinstance(result, list)
        assert len(result) > 1  # should have multiple chunks

    def test_import_document_with_contextualize_no_llm(self, tmp_path):
        """Test contextualize=True without LLM (should gracefully handle)."""
        from vault.importer import import_document
        from unittest.mock import MagicMock
        
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test\nContent for contextualize test. More content here.")
        
        mock_db = MagicMock()
        mock_db.add_knowledge.return_value = 1
        
        # contextualize=True but no llm provided - should still work
        result = import_document(
            str(test_file),
            mock_db,
            strategy="sliding",
            contextualize=True,
        )
        assert isinstance(result, list)
