"""
Embeddings configuration for ChromaDB.
Provides an offline, fast, deterministic HashingVectorizer embedding function
that generates 384-dimensional normalized dense vectors locally without any
network calls or model downloads, with OpenAI embeddings when configured.
"""

import logging
from typing import Any, List, Dict
import numpy as np
from sklearn.feature_extraction.text import HashingVectorizer
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings
from app.config import settings

logger = logging.getLogger(__name__)


class FastOfflineEmbeddingFunction(EmbeddingFunction[Documents]):
    """
    Self-contained, ultra-fast embedding generator for ChromaDB.
    Produces 384-dimensional L2-normalized dense embeddings.
    Zero external dependencies, zero downloads, instant execution.
    """

    def __init__(self, n_features: int = 384):
        self.n_features = n_features
        self._vectorizer = HashingVectorizer(
            n_features=n_features,
            alternate_sign=False,
            norm="l2",
            lowercase=True
        )

    def name(self) -> str:
        return "default"

    def get_config(self) -> Dict[str, Any]:
        return {"n_features": self.n_features}

    def __call__(self, input: Documents) -> Embeddings:
        if not input:
            return []
        sparse_mat = self._vectorizer.transform(input)
        # Convert to list of float lists
        dense_mat = sparse_mat.toarray().astype(np.float32)
        return dense_mat.tolist()


def get_embedding_function() -> Any:
    """
    Returns an embedding function for ChromaDB.
    Uses OpenAI embeddings if configured, else uses FastOfflineEmbeddingFunction.
    """
    if settings.OPENAI_API_KEY and settings.OPENAI_API_KEY.startswith("sk-") and settings.OPENAI_API_KEY != "sk-placeholder":
        try:
            import chromadb.utils.embedding_functions as ef
            logger.info("Using OpenAI embedding function")
            return ef.OpenAIEmbeddingFunction(
                api_key=settings.OPENAI_API_KEY,
                model_name="text-embedding-3-small"
            )
        except Exception as err:
            logger.warning("Failed to initialize OpenAI embeddings: %s", err)

    return FastOfflineEmbeddingFunction(n_features=384)
