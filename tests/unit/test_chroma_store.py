"""Unit tests for ChromaDB memory store.

Tests semantic memory storage and retrieval, including
distance-to-similarity conversion.
"""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from reachy_agent.memory.storage.chroma_store import ChromaMemoryStore
from reachy_agent.memory.types import MemoryType


@pytest.fixture
def temp_chroma_dir():
    """Create a temporary directory for ChromaDB."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_collection():
    """Create a mock ChromaDB collection."""
    mock = MagicMock()
    mock.add = MagicMock()
    mock.query = MagicMock(return_value={
        "ids": [["id1", "id2"]],
        "documents": [["Content 1", "Content 2"]],
        "metadatas": [[
            {"memory_type": "fact", "timestamp": datetime.now().isoformat()},
            {"memory_type": "preference", "timestamp": datetime.now().isoformat()},
        ]],
        "distances": [[0.1, 0.5]],
    })
    mock.get = MagicMock(return_value={
        "ids": ["id1"],
        "documents": ["Content 1"],
        "metadatas": [{"memory_type": "fact", "timestamp": datetime.now().isoformat()}],
    })
    mock.delete = MagicMock()
    mock.count = MagicMock(return_value=10)
    return mock


class TestChromaMemoryStoreInit:
    """Tests for ChromaMemoryStore initialization."""

    def test_init_expands_path(self, temp_chroma_dir: Path) -> None:
        """Test that initialization expands user path."""
        store = ChromaMemoryStore("~/test/path")
        assert "~" not in str(store.path)

    def test_collection_property_raises_before_init(
        self, temp_chroma_dir: Path
    ) -> None:
        """Test that collection property raises if not initialized."""
        store = ChromaMemoryStore(temp_chroma_dir)
        with pytest.raises(RuntimeError, match="not initialized"):
            _ = store.collection


class TestDistanceToSimilarity:
    """Tests for distance-to-similarity conversion.

    ChromaDB cosine distance ranges from 0 (identical) to 2 (opposite).
    We convert this to a similarity score in [0, 1].
    """

    @pytest.mark.asyncio
    async def test_identical_vectors_high_similarity(
        self, temp_chroma_dir: Path, mock_collection: MagicMock
    ) -> None:
        """Test that distance=0 gives similarity=1.0."""
        store = ChromaMemoryStore(temp_chroma_dir)
        store._collection = mock_collection

        # Set up mock for distance=0 (identical vectors)
        mock_collection.query.return_value = {
            "ids": [["id1"]],
            "documents": [["Content"]],
            "metadatas": [[{"memory_type": "fact", "timestamp": datetime.now().isoformat()}]],
            "distances": [[0.0]],
        }

        # Mock embedding service via private attribute
        mock_embed = MagicMock()
        mock_embed.embed.return_value = [0.1] * 384
        store._embedding_service = mock_embed

        results = await store.search("query")

        assert len(results) == 1
        assert results[0].score == 1.0

    @pytest.mark.asyncio
    async def test_opposite_vectors_low_similarity(
        self, temp_chroma_dir: Path, mock_collection: MagicMock
    ) -> None:
        """Test that distance=2 gives similarity=0.0."""
        store = ChromaMemoryStore(temp_chroma_dir)
        store._collection = mock_collection

        # Set up mock for distance=2 (opposite vectors)
        mock_collection.query.return_value = {
            "ids": [["id1"]],
            "documents": [["Content"]],
            "metadatas": [[{"memory_type": "fact", "timestamp": datetime.now().isoformat()}]],
            "distances": [[2.0]],
        }

        # Mock embedding service via private attribute
        mock_embed = MagicMock()
        mock_embed.embed.return_value = [0.1] * 384
        store._embedding_service = mock_embed

        results = await store.search("query")

        assert len(results) == 1
        assert results[0].score == 0.0

    @pytest.mark.asyncio
    async def test_mid_range_distance(
        self, temp_chroma_dir: Path, mock_collection: MagicMock
    ) -> None:
        """Test that distance=1 gives similarity=0.5."""
        store = ChromaMemoryStore(temp_chroma_dir)
        store._collection = mock_collection

        mock_collection.query.return_value = {
            "ids": [["id1"]],
            "documents": [["Content"]],
            "metadatas": [[{"memory_type": "fact", "timestamp": datetime.now().isoformat()}]],
            "distances": [[1.0]],
        }

        # Mock embedding service via private attribute
        mock_embed = MagicMock()
        mock_embed.embed.return_value = [0.1] * 384
        store._embedding_service = mock_embed

        results = await store.search("query")

        assert len(results) == 1
        assert results[0].score == 0.5

    @pytest.mark.asyncio
    async def test_similarity_clamped_to_valid_range(
        self, temp_chroma_dir: Path, mock_collection: MagicMock
    ) -> None:
        """Test that similarity is clamped to [0, 1] even for extreme distances."""
        store = ChromaMemoryStore(temp_chroma_dir)
        store._collection = mock_collection

        # Test with distance > 2 (shouldn't happen, but edge case)
        mock_collection.query.return_value = {
            "ids": [["id1"]],
            "documents": [["Content"]],
            "metadatas": [[{"memory_type": "fact", "timestamp": datetime.now().isoformat()}]],
            "distances": [[2.5]],  # Beyond normal range
        }

        # Mock embedding service via private attribute
        mock_embed = MagicMock()
        mock_embed.embed.return_value = [0.1] * 384
        store._embedding_service = mock_embed

        results = await store.search("query")

        assert len(results) == 1
        assert results[0].score >= 0.0  # Should be clamped to 0


class TestChromaMemoryStoreOperations:
    """Tests for store operations."""

    @pytest.mark.asyncio
    async def test_store_memory(
        self, temp_chroma_dir: Path, mock_collection: MagicMock
    ) -> None:
        """Test storing a memory."""
        store = ChromaMemoryStore(temp_chroma_dir)
        store._collection = mock_collection

        # Mock embedding service via private attribute
        mock_embed = MagicMock()
        mock_embed.embed.return_value = [0.1] * 384
        store._embedding_service = mock_embed

        memory = await store.store("Test content", MemoryType.FACT)

        assert memory.content == "Test content"
        assert memory.memory_type == MemoryType.FACT
        assert memory.id is not None
        mock_collection.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_with_filter(
        self, temp_chroma_dir: Path, mock_collection: MagicMock
    ) -> None:
        """Test searching with memory type filter."""
        store = ChromaMemoryStore(temp_chroma_dir)
        store._collection = mock_collection

        # Mock embedding service via private attribute
        mock_embed = MagicMock()
        mock_embed.embed.return_value = [0.1] * 384
        store._embedding_service = mock_embed

        await store.search("query", memory_type=MemoryType.PREFERENCE)

        # Verify where filter was passed
        call_args = mock_collection.query.call_args
        assert call_args.kwargs.get("where") == {"memory_type": "preference"}

    @pytest.mark.asyncio
    async def test_search_empty_results(
        self, temp_chroma_dir: Path, mock_collection: MagicMock
    ) -> None:
        """Test searching with no results."""
        store = ChromaMemoryStore(temp_chroma_dir)
        store._collection = mock_collection

        mock_collection.query.return_value = {
            "ids": [[]],
            "documents": [[]],
            "metadatas": [[]],
            "distances": [[]],
        }

        # Mock embedding service via private attribute
        mock_embed = MagicMock()
        mock_embed.embed.return_value = [0.1] * 384
        store._embedding_service = mock_embed

        results = await store.search("nonexistent")

        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_get_memory(
        self, temp_chroma_dir: Path, mock_collection: MagicMock
    ) -> None:
        """Test getting a memory by ID."""
        store = ChromaMemoryStore(temp_chroma_dir)
        store._collection = mock_collection

        memory = await store.get("id1")

        assert memory is not None
        assert memory.id == "id1"
        assert memory.content == "Content 1"

    @pytest.mark.asyncio
    async def test_get_memory_not_found(
        self, temp_chroma_dir: Path, mock_collection: MagicMock
    ) -> None:
        """Test getting a nonexistent memory."""
        store = ChromaMemoryStore(temp_chroma_dir)
        store._collection = mock_collection

        mock_collection.get.return_value = {"ids": [], "documents": [], "metadatas": []}

        memory = await store.get("nonexistent")

        assert memory is None

    @pytest.mark.asyncio
    async def test_delete_memory(
        self, temp_chroma_dir: Path, mock_collection: MagicMock
    ) -> None:
        """Test deleting a memory."""
        store = ChromaMemoryStore(temp_chroma_dir)
        store._collection = mock_collection

        result = await store.delete("id1")

        assert result is True
        mock_collection.delete.assert_called_once_with(ids=["id1"])

    @pytest.mark.asyncio
    async def test_count(
        self, temp_chroma_dir: Path, mock_collection: MagicMock
    ) -> None:
        """Test counting memories."""
        store = ChromaMemoryStore(temp_chroma_dir)
        store._collection = mock_collection

        count = await store.count()

        assert count == 10


class TestChromaMemoryStoreClose:
    """Tests for close operation."""

    @pytest.mark.asyncio
    async def test_close_clears_references(
        self, temp_chroma_dir: Path, mock_collection: MagicMock
    ) -> None:
        """Test that close clears all references."""
        store = ChromaMemoryStore(temp_chroma_dir)
        store._client = MagicMock()
        store._collection = mock_collection
        store._embedding_service = MagicMock()

        await store.close()

        assert store._client is None
        assert store._collection is None
        assert store._embedding_service is None

    @pytest.mark.asyncio
    async def test_close_idempotent(self, temp_chroma_dir: Path) -> None:
        """Test that close can be called multiple times."""
        store = ChromaMemoryStore(temp_chroma_dir)
        store._client = None
        store._collection = None

        # Should not raise
        await store.close()
        await store.close()
