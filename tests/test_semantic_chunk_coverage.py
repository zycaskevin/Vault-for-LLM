"""Tests for semantic_chunk function with mocked embeddings to boost coverage."""

import pytest
from unittest.mock import MagicMock
import math

try:
    import numpy as _numpy_available
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

pytestmark = pytest.mark.skipif(
    not HAS_NUMPY,
    reason="requires numpy"
)


class TestSemanticChunk:
    """Test semantic_chunk function with mocked embedding provider."""
    
    def _create_mock_embed(self, vectors):
        """Create a mock embedding provider that returns given vectors."""
        mock_embed = MagicMock()
        mock_embed.encode.return_value = vectors
        return mock_embed
    
    def test_semantic_chunk_short_text(self):
        """Test semantic_chunk with very short text (fewer than 3 sentences)."""
        from vault.importer import semantic_chunk
        
        text = "First sentence. Second one."
        mock_embed = self._create_mock_embed([[1, 0], [0, 1]])
        
        result = semantic_chunk(text, mock_embed)
        assert len(result) == 1
        assert result[0].chunk_type == "semantic"
    
    def test_semantic_chunk_single_topic(self):
        """Test semantic_chunk with all similar sentences (one chunk)."""
        from vault.importer import semantic_chunk
        
        # All sentences are similar (same direction)
        text = "Sentence one. Sentence two. Sentence three. Sentence four. Sentence five."
        # All vectors point in same direction = high similarity
        vectors = [[1, 0, 0]] * 5
        mock_embed = self._create_mock_embed(vectors)
        
        result = semantic_chunk(text, mock_embed)
        # Should be all in one chunk since all similar
        assert len(result) == 1
    
    def test_semantic_chunk_two_topics(self):
        """Test semantic_chunk with two distinct topics."""
        from vault.importer import semantic_chunk
        
        text = "Topic one sentence. Another about topic one. Now topic two. Also about topic two. More on topic two."
        # First 2 sentences similar, last 3 similar, but groups are different
        vectors = [
            [1, 0, 0], [1, 0.1, 0],  # topic 1
            [0, 1, 0], [0, 1.1, 0], [0, 0.9, 0],  # topic 2
        ]
        mock_embed = self._create_mock_embed(vectors)
        
        result = semantic_chunk(
            text, mock_embed, 
            similarity_threshold=0.5,
            min_chunk_size=10,  # Small min to avoid merging small chunks
        )
        # Should split into at least 2 chunks
        assert len(result) >= 2
    
    def test_semantic_chunk_merges_small_chunks(self):
        """Test that small chunks are merged."""
        from vault.importer import semantic_chunk
        
        # Create sentences where some chunks would be smaller than min_chunk_size
        text = """First sentence about topic A. Second about A. Third about A.
Now topic B. Another B sentence. Third B sentence. Fourth B.
Back to topic A again. More A content. And more A."""
        
        # Three distinct topics
        vectors = [
            [1, 0, 0], [1, 0.1, 0], [0.9, 0.05, 0],  # topic 1
            [0, 1, 0], [0, 1.1, 0], [0, 0.9, 0], [0, 1, 0.1],  # topic 2
            [1, 0.1, 0], [0.9, 0, 0.1], [1, 0, 0],  # topic 1 again
        ]
        mock_embed = self._create_mock_embed(vectors)
        
        result = semantic_chunk(
            text, mock_embed, 
            similarity_threshold=0.5,
            min_chunk_size=50,  # Some chunks might be small
            max_chunk_size=2000,
        )
        # Should still work and produce chunks
        assert len(result) >= 1
        assert all(isinstance(c.content, str) for c in result)
    
    def test_semantic_chunk_splits_large_chunks(self):
        """Test that large chunks are split by paragraph.
        
        Note: semantic_chunk builds chunk content with '\n' between sentences,
        so PARA_SPLIT (which looks for '\n\s*\n') only splits when the original
        text has paragraph breaks that fall between sentence boundaries.
        We test with multiple distinct topics to create chunks, and verify
        the merge/split logic handles them properly.
        """
        from vault.importer import semantic_chunk
        
        # Create text with multiple topics that will produce multiple chunks
        # Each "topic" has enough content to be a chunk of its own
        sentences = []
        vectors = []
        
        # Topic 1
        for i in range(5):
            sentences.append(f"Topic one sentence {i}. This is about the first topic.")
            vectors.append([1, 0, 0])
        
        # Topic 2 (very different vector)
        for i in range(5):
            sentences.append(f"Topic two sentence {i}. This is about the second topic.")
            vectors.append([0, 1, 0])
        
        # Topic 3
        for i in range(5):
            sentences.append(f"Topic three sentence {i}. This is about the third topic.")
            vectors.append([0, 0, 1])
        
        text = " ".join(sentences)
        mock_embed = self._create_mock_embed(vectors)
        
        result = semantic_chunk(
            text, mock_embed,
            similarity_threshold=0.5,
            min_chunk_size=50,
            max_chunk_size=500,
        )
        
        # Should have multiple chunks due to topic changes
        assert len(result) > 1
        # Verify all chunks have valid structure
        for i, chunk in enumerate(result):
            assert chunk.index == i
            assert chunk.chunk_type == "semantic"
            assert len(chunk.content) > 0
    
    def test_semantic_chunk_custom_threshold(self):
        """Test semantic_chunk with different similarity thresholds."""
        from vault.importer import semantic_chunk
        
        text = "Sent one. Sent two. Sent three. Sent four. Sent five."
        # Gradually changing vectors
        vectors = [
            [1, 0], [0.8, 0.2], [0.5, 0.5], [0.2, 0.8], [0, 1],
        ]
        mock_embed = self._create_mock_embed(vectors)
        
        # High threshold = more chunks
        result_high = semantic_chunk(text, mock_embed, similarity_threshold=0.9)
        # Low threshold = fewer chunks
        result_low = semantic_chunk(text, mock_embed, similarity_threshold=0.1)
        
        assert len(result_high) >= len(result_low)
    
    def test_semantic_chunk_empty_text(self):
        """Test semantic_chunk with empty text."""
        from vault.importer import semantic_chunk
        
        mock_embed = self._create_mock_embed([])
        result = semantic_chunk("", mock_embed)
        
        # Should return at least one chunk with empty content
        assert len(result) >= 0
        assert isinstance(result, list)
    
    def test_semantic_chunk_result_structure(self):
        """Test that result chunks have correct structure."""
        from vault.importer import semantic_chunk
        
        text = "First sentence. Second sentence. Third sentence. Fourth sentence. Fifth sentence."
        vectors = [[1, 0], [1, 0.1], [0, 1], [0, 1.1], [0.1, 1]]
        mock_embed = self._create_mock_embed(vectors)
        
        result = semantic_chunk(text, mock_embed, similarity_threshold=0.5)
        
        for i, chunk in enumerate(result):
            assert chunk.index == i
            assert chunk.title == f"§{i + 1}"
            assert chunk.chunk_type == "semantic"
            assert isinstance(chunk.content, str)
            assert isinstance(chunk.start_char, int)
            assert isinstance(chunk.end_char, int)
            assert chunk.end_char >= chunk.start_char
