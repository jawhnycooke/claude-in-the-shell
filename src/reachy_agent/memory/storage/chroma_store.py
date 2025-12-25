"""ChromaDB storage for semantic memories.

Provides vector-based storage and retrieval using ChromaDB.
Memories are embedded and stored for semantic similarity search.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from reachy_agent.memory.embeddings import EmbeddingService, get_embedding_service
from reachy_agent.memory.types import Memory, MemoryType, SearchResult

if TYPE_CHECKING:
    import chromadb
    from chromadb.api.models.Collection import Collection

logger = logging.getLogger(__name__)

COLLECTION_NAME = "reachy_memories"


class ChromaMemoryStore:
    """ChromaDB-backed storage for semantic memories.

    Provides storage and retrieval of memories using vector embeddings
    for semantic similarity search.

    Args:
        path: Path to ChromaDB persistence directory.
        embedding_model: Name of sentence-transformers model to use.

    Example:
        >>> store = ChromaMemoryStore("~/.reachy/memory/chroma")
        >>> await store.initialize()
        >>> memory = await store.store("User prefers morning meetings", MemoryType.PREFERENCE)
        >>> results = await store.search("when does user like meetings", n_results=5)
    """

    def __init__(
        self,
        path: str | Path,
        embedding_model: str = "all-MiniLM-L6-v2",
    ) -> None:
        self.path = Path(path).expanduser()
        self.embedding_model = embedding_model
        self._client: chromadb.PersistentClient | None = None
        self._collection: Collection | None = None
        self._embedding_service: EmbeddingService | None = None

    @property
    def embedding_service(self) -> EmbeddingService:
        """Get or create the embedding service."""
        if self._embedding_service is None:
            self._embedding_service = get_embedding_service(self.embedding_model)
        return self._embedding_service

    async def initialize(self) -> None:
        """Initialize ChromaDB client and collection.

        Creates the persistence directory if it doesn't exist.
        """
        import chromadb
        from chromadb.config import Settings

        self.path.mkdir(parents=True, exist_ok=True)

        logger.info(f"Initializing ChromaDB at {self.path}")
        self._client = chromadb.PersistentClient(
            path=str(self.path),
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True,
            ),
        )

        self._collection = self._client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(f"ChromaDB collection '{COLLECTION_NAME}' ready")

    @property
    def collection(self) -> Collection:
        """Get the ChromaDB collection, raising if not initialized."""
        if self._collection is None:
            raise RuntimeError(
                "ChromaMemoryStore not initialized. Call initialize() first."
            )
        return self._collection

    async def store(
        self,
        content: str,
        memory_type: MemoryType,
        metadata: dict | None = None,
    ) -> Memory:
        """Store a new memory with its embedding.

        Args:
            content: The text content to store.
            memory_type: Category of this memory.
            metadata: Optional additional metadata.

        Returns:
            The created Memory object.
        """
        memory_id = str(uuid.uuid4())
        timestamp = datetime.now()

        # Generate embedding
        embedding = self.embedding_service.embed(content)

        # Prepare metadata for ChromaDB (must be flat key-value)
        chroma_metadata = {
            "memory_type": memory_type.value,
            "timestamp": timestamp.isoformat(),
            **(metadata or {}),
        }

        # Store in ChromaDB
        self.collection.add(
            ids=[memory_id],
            embeddings=[embedding],
            documents=[content],
            metadatas=[chroma_metadata],
        )

        memory = Memory(
            id=memory_id,
            content=content,
            memory_type=memory_type,
            timestamp=timestamp,
            metadata=metadata or {},
            embedding=embedding,
        )

        logger.debug(f"Stored memory {memory_id}: {content[:50]}...")
        return memory

    async def search(
        self,
        query: str,
        n_results: int = 5,
        memory_type: MemoryType | None = None,
    ) -> list[SearchResult]:
        """Search memories by semantic similarity.

        Args:
            query: The search query text.
            n_results: Maximum number of results to return.
            memory_type: Optional filter by memory type.

        Returns:
            List of SearchResult objects sorted by similarity.
        """
        # Generate query embedding
        query_embedding = self.embedding_service.embed(query)

        # Build where filter if memory_type specified
        where_filter = None
        if memory_type is not None:
            where_filter = {"memory_type": memory_type.value}

        # Search ChromaDB
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where_filter,
            include=["documents", "metadatas", "distances"],
        )

        # Convert to SearchResult objects
        search_results = []
        if results["ids"] and results["ids"][0]:
            for i, memory_id in enumerate(results["ids"][0]):
                content = results["documents"][0][i] if results["documents"] else ""
                metadata = results["metadatas"][0][i] if results["metadatas"] else {}
                distance = results["distances"][0][i] if results["distances"] else 1.0

                # Convert distance to similarity score (0.0 to 1.0)
                # ChromaDB cosine distance ranges from 0 (identical) to 2 (opposite)
                # Formula: similarity = 1 - (distance / 2), clamped to [0, 1]
                # This gives: distance=0 -> similarity=1.0, distance=2 -> similarity=0.0
                similarity = max(0.0, min(1.0, 1.0 - (distance / 2.0)))

                memory = Memory(
                    id=memory_id,
                    content=content,
                    memory_type=MemoryType.from_string(
                        metadata.get("memory_type", "fact")
                    ),
                    timestamp=datetime.fromisoformat(
                        metadata.get("timestamp", datetime.now().isoformat())
                    ),
                    metadata={
                        k: v for k, v in metadata.items() if k not in ("memory_type", "timestamp")
                    },
                )

                search_results.append(SearchResult(memory=memory, score=similarity))

        return search_results

    async def get(self, memory_id: str) -> Memory | None:
        """Retrieve a specific memory by ID.

        Args:
            memory_id: The unique identifier of the memory.

        Returns:
            The Memory object if found, None otherwise.
        """
        result = self.collection.get(
            ids=[memory_id],
            include=["documents", "metadatas"],
        )

        if not result["ids"]:
            return None

        content = result["documents"][0] if result["documents"] else ""
        metadata = result["metadatas"][0] if result["metadatas"] else {}

        return Memory(
            id=memory_id,
            content=content,
            memory_type=MemoryType.from_string(metadata.get("memory_type", "fact")),
            timestamp=datetime.fromisoformat(
                metadata.get("timestamp", datetime.now().isoformat())
            ),
            metadata={
                k: v for k, v in metadata.items() if k not in ("memory_type", "timestamp")
            },
        )

    async def delete(self, memory_id: str) -> bool:
        """Delete a memory by ID.

        Args:
            memory_id: The unique identifier of the memory to delete.

        Returns:
            True if deleted, False if not found.
        """
        try:
            self.collection.delete(ids=[memory_id])
            logger.debug(f"Deleted memory {memory_id}")
            return True
        except Exception as e:
            logger.warning(f"Failed to delete memory {memory_id}: {e}")
            return False

    async def cleanup(self, retention_days: int) -> int:
        """Remove memories older than retention period.

        Args:
            retention_days: Number of days to retain memories.

        Returns:
            Number of memories deleted.
        """
        cutoff = datetime.now() - timedelta(days=retention_days)
        cutoff_str = cutoff.isoformat()

        # Get all memories older than cutoff
        results = self.collection.get(
            where={"timestamp": {"$lt": cutoff_str}},
            include=["metadatas"],
        )

        if not results["ids"]:
            return 0

        # Delete old memories
        self.collection.delete(ids=results["ids"])
        count = len(results["ids"])
        logger.info(f"Cleaned up {count} memories older than {retention_days} days")
        return count

    async def count(self) -> int:
        """Get total number of memories stored."""
        return self.collection.count()

    async def close(self) -> None:
        """Close the ChromaDB client.

        ChromaDB PersistentClient handles cleanup automatically,
        so this method clears references for consistency.
        """
        if self._client is None and self._collection is None:
            logger.debug("ChromaDB store already closed")
            return

        self._client = None
        self._collection = None
        self._embedding_service = None
        logger.info("ChromaDB store closed")
