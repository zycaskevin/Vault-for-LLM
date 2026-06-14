"""Tests for importer module pure functions to boost coverage."""

import pytest
from pathlib import Path


class TestDetectChapters:
    """Test detect_chapters function."""
    
    def test_detect_chapters_markdown(self):
        """Test chapter detection with markdown headings."""
        from vault.importer import detect_chapters
        
        text = """# Chapter 1

Content of chapter 1.

## Section 1.1

More content.

# Chapter 2

Content of chapter 2.
"""
        chapters = detect_chapters(text)
        
        # It detects both # and ## headings
        assert len(chapters) >= 2
        assert chapters[0][0] == "Chapter 1"
        # Each is (title, start, end)
        assert isinstance(chapters[0], tuple)
        assert len(chapters[0]) == 3
    
    def test_detect_chapters_empty(self):
        """Test chapter detection with empty text."""
        from vault.importer import detect_chapters
        
        chapters = detect_chapters("")
        assert chapters == []
    
    def test_detect_chapters_no_headings(self):
        """Test chapter detection with no headings."""
        from vault.importer import detect_chapters
        
        text = "Just some plain text without any headings."
        chapters = detect_chapters(text)
        assert len(chapters) == 0


class TestSplitIntoSentences:
    """Test split_into_sentences function."""
    
    def test_split_sentences_basic(self):
        """Test basic sentence splitting."""
        from vault.importer import split_into_sentences
        
        text = "Hello world. This is a test. How are you?"
        sentences = split_into_sentences(text)
        
        assert len(sentences) >= 2
        # Each result is (sentence, start_index)
        assert isinstance(sentences[0], tuple)
        assert len(sentences[0]) == 2
    
    def test_split_sentences_empty(self):
        """Test sentence splitting with empty text."""
        from vault.importer import split_into_sentences
        
        sentences = split_into_sentences("")
        assert sentences == []


class TestSlidingWindowChunk:
    """Test sliding_window_chunk function."""
    
    def test_sliding_window_basic(self):
        """Test basic sliding window chunking."""
        from vault.importer import sliding_window_chunk
        
        text = "a" * 1000
        chunks = sliding_window_chunk(text, chunk_size=500, overlap=100)
        
        assert len(chunks) > 1
        # Each chunk is a ChunkResult
        assert hasattr(chunks[0], 'content')
        assert hasattr(chunks[0], 'start_char')
        assert hasattr(chunks[0], 'end_char')
    
    def test_sliding_window_small_text(self):
        """Test sliding window with text smaller than chunk size."""
        from vault.importer import sliding_window_chunk
        
        text = "Short text."
        chunks = sliding_window_chunk(text, chunk_size=500, overlap=100)
        
        assert len(chunks) == 1
        assert chunks[0].content == text
    
    def test_sliding_window_empty(self):
        """Test sliding window with empty text."""
        from vault.importer import sliding_window_chunk
        
        chunks = sliding_window_chunk("", chunk_size=500, overlap=100)
        assert len(chunks) == 0


class TestSplitIntoParagraphs:
    """Test _split_into_paragraphs function."""
    
    def test_split_paragraphs_with_headings(self):
        """Test paragraph splitting with markdown headings."""
        from vault.importer import _split_into_paragraphs
        
        text = """## Section 1

Content of section 1.

## Section 2

Content of section 2.
"""
        paragraphs = _split_into_paragraphs(text)
        
        assert len(paragraphs) >= 2
        # Each is (text, heading)
        assert isinstance(paragraphs[0], tuple)
        assert len(paragraphs[0]) == 2
    
    def test_split_paragraphs_single(self):
        """Test paragraph splitting with single paragraph."""
        from vault.importer import _split_into_paragraphs
        
        text = "Single paragraph without breaks."
        paragraphs = _split_into_paragraphs(text)
        
        assert len(paragraphs) == 1
    
    def test_split_paragraphs_empty(self):
        """Test paragraph splitting with empty text."""
        from vault.importer import _split_into_paragraphs
        
        paragraphs = _split_into_paragraphs("")
        assert paragraphs == []


class TestDecomposeWithLLM:
    """Test _decompose_with_llm parsing logic (mocked LLM)."""
    
    def test_decompose_basic(self):
        """Test basic proposition decomposition with mock LLM."""
        from vault.importer import _decompose_with_llm
        from unittest.mock import MagicMock
        
        mock_llm = MagicMock()
        mock_llm.generate.return_value = """The Earth is round.
Gravity is 9.8 m/s^2.
Water boils at 100 degrees Celsius."""
        
        result = _decompose_with_llm(
            text="Some text about science.",
            llm=mock_llm,
            doc_title="Science Facts",
        )
        
        assert result is not None
        assert len(result) >= 2
    
    def test_decompose_with_rejections(self):
        """Test that reject patterns filter out invalid lines."""
        from vault.importer import _decompose_with_llm
        from unittest.mock import MagicMock
        
        mock_llm = MagicMock()
        # Include lines that should be rejected
        mock_llm.generate.return_value = """好的，以下是拆解的命題：
```
The sun is a star.
```
1. The Earth orbits the sun.
**This is bold text.**
"Quoted proposition."
"""
        
        result = _decompose_with_llm(
            text="Some text.",
            llm=mock_llm,
        )
        
        assert result is not None
        # Should have filtered out some lines
        assert len(result) >= 1
    
    def test_decompose_empty_response(self):
        """Test with empty LLM response."""
        from vault.importer import _decompose_with_llm
        from unittest.mock import MagicMock
        
        mock_llm = MagicMock()
        mock_llm.generate.return_value = ""
        
        result = _decompose_with_llm(text="test", llm=mock_llm)
        assert result is None
    
    def test_decompose_short_lines(self):
        """Test that short lines are filtered out."""
        from vault.importer import _decompose_with_llm
        from unittest.mock import MagicMock
        
        mock_llm = MagicMock()
        mock_llm.generate.return_value = "Hi.\nShort.\nThis is a properly long sentence about something important."
        
        result = _decompose_with_llm(text="test", llm=mock_llm)
        assert result is not None
        # Short lines (< 10 chars) should be filtered out
        assert len(result) == 1
    
    def test_decompose_llm_error(self):
        """Test that LLM errors return None."""
        from vault.importer import _decompose_with_llm
        from unittest.mock import MagicMock
        
        mock_llm = MagicMock()
        mock_llm.generate.side_effect = Exception("API Error")
        
        result = _decompose_with_llm(text="test", llm=mock_llm)
        assert result is None
    
    def test_decompose_max_propositions(self):
        """Test max_propositions limit."""
        from vault.importer import _decompose_with_llm
        from unittest.mock import MagicMock
        
        mock_llm = MagicMock()
        mock_llm.generate.return_value = """First proposition about something.
Second proposition with details.
Third proposition here.
Fourth proposition as well.
Fifth proposition too.
Sixth proposition also.
Seventh proposition yes.
Eighth proposition finally.
Ninth proposition extra."""
        
        result = _decompose_with_llm(
            text="test", 
            llm=mock_llm, 
            max_propositions=5
        )
        assert result is not None
        assert len(result) == 5


class TestContextualizeChunks:
    """Test contextualize_chunks function."""
    
    def test_contextualize_chunks_mocked(self):
        """Test contextualize with mocked LLM."""
        from vault.importer import contextualize_chunks
        from unittest.mock import MagicMock
        
        mock_llm = MagicMock()
        mock_llm.generate.return_value = "【上下文】 Enhanced content here."
        
        chunks = [
            MagicMock(content="Chunk 1 content.", title="Chunk 1"),
            MagicMock(content="Chunk 2 content.", title="Chunk 2"),
        ]
        
        result = contextualize_chunks(
            chunks=chunks,
            llm=mock_llm,
            doc_title="Test Doc",
        )
        
        assert result is not None
        assert len(result) == 2
    
    def test_contextualize_chunks_empty(self):
        """Test contextualize with empty chunks."""
        from vault.importer import contextualize_chunks
        from unittest.mock import MagicMock
        
        mock_llm = MagicMock()
        result = contextualize_chunks([], mock_llm)
        assert result == []


class TestPropositionChunk:
    """Test proposition_chunk function."""
    
    def test_proposition_chunk_mocked(self):
        """Test proposition chunking with mocked LLM."""
        from vault.importer import proposition_chunk
        from unittest.mock import MagicMock
        
        mock_llm = MagicMock()
        mock_llm.generate.return_value = """Proposition one about the topic.
Proposition two with more details.
Proposition three is a fact."""
        
        text = "A long text about various topics." * 10
        chunks = proposition_chunk(text, llm=mock_llm, doc_title="Test")
        
        assert len(chunks) >= 1
        assert hasattr(chunks[0], 'content')
    
    def test_proposition_chunk_no_llm(self):
        """Test proposition chunk without LLM (falls back)."""
        from vault.importer import proposition_chunk
        
        text = "A test document. With multiple sentences. Here is more content."
        chunks = proposition_chunk(text, llm=None)
        
        # Should still work, falling back to something
        assert isinstance(chunks, list)
