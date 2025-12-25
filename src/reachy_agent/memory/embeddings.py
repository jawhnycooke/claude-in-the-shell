"""Embedding service for semantic memory search.

Provides text-to-vector embeddings using sentence-transformers.
Uses lazy loading to avoid importing the heavy ML libraries until needed.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# Default model produces 384-dimensional embeddings
DEFAULT_MODEL = "all-MiniLM-L6-v2"


class EmbeddingService:
    """Service for generating text embeddings.

    Lazily loads the sentence-transformers model on first use to avoid
    slow startup times when embeddings aren't immediately needed.

    Args:
        model_name: Name of the sentence-transformers model to use.
            Defaults to all-MiniLM-L6-v2 (384 dimensions, fast).

    Example:
        >>> service = EmbeddingService()
        >>> embedding = service.embed("Hello world")
        >>> len(embedding)
        384
    """

    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        self.model_name = model_name
        self._model: SentenceTransformer | None = None
        self._dimension: int | None = None

    @property
    def model(self) -> SentenceTransformer:
        """Lazily load the sentence-transformers model."""
        if self._model is None:
            logger.info(f"Loading embedding model: {self.model_name}")
            try:
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer(self.model_name)
                self._dimension = self._model.get_sentence_embedding_dimension()
                logger.info(
                    f"Loaded {self.model_name} with {self._dimension} dimensions"
                )
            except ImportError as e:
                raise ImportError(
                    "sentence-transformers is required for embeddings. "
                    "Install with: pip install sentence-transformers"
                ) from e
        return self._model

    @property
    def dimension(self) -> int:
        """Get the embedding dimension (loads model if needed)."""
        if self._dimension is None:
            # Access model property to trigger loading
            _ = self.model
        return self._dimension or 384  # Default for MiniLM

    def embed(self, text: str) -> list[float]:
        """Generate embedding for a single text string.

        Args:
            text: The text to embed.

        Returns:
            List of floats representing the embedding vector.
        """
        embedding = self.model.encode(text, convert_to_numpy=True)
        return embedding.tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts efficiently.

        Args:
            texts: List of texts to embed.

        Returns:
            List of embedding vectors, one per input text.
        """
        if not texts:
            return []

        embeddings = self.model.encode(
            texts,
            convert_to_numpy=True,
            show_progress_bar=len(texts) > 10,
        )
        return [emb.tolist() for emb in embeddings]

    def similarity(self, embedding1: list[float], embedding2: list[float]) -> float:
        """Calculate cosine similarity between two embeddings.

        Args:
            embedding1: First embedding vector.
            embedding2: Second embedding vector.

        Returns:
            Similarity score between 0 and 1 (higher is more similar).
        """
        import numpy as np

        e1 = np.array(embedding1)
        e2 = np.array(embedding2)

        # Cosine similarity
        dot_product = np.dot(e1, e2)
        norm1 = np.linalg.norm(e1)
        norm2 = np.linalg.norm(e2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return float(dot_product / (norm1 * norm2))


@lru_cache(maxsize=1)
def get_embedding_service(model_name: str = DEFAULT_MODEL) -> EmbeddingService:
    """Get a cached embedding service instance.

    Use this function to avoid creating multiple instances of the
    embedding service, which would load the model multiple times.

    Args:
        model_name: Name of the sentence-transformers model.

    Returns:
        Cached EmbeddingService instance.
    """
    return EmbeddingService(model_name)
