"""
embedder.py — Embedding Service
Supports: local (sentence-transformers), OpenAI, Voyage AI
"""

import os
import numpy as np
from typing import List
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", ".env"))

PROVIDER = os.getenv("EMBEDDING_PROVIDER", "local")
LOCAL_MODEL = os.getenv("LOCAL_EMBEDDING_MODEL", "all-MiniLM-L6-v2")


class Embedder:
    """
    Unified embedding interface.
    Switch provider in .env without changing any other code.
    """

    def __init__(self):
        self.provider = PROVIDER
        self.model = None
        self._load_model()

    def _load_model(self):
        if self.provider == "local":
            from sentence_transformers import SentenceTransformer
            print(f"[Embedder] Loading local model: {LOCAL_MODEL}")
            self.model = SentenceTransformer(LOCAL_MODEL)
            self.dimension = self.model.get_embedding_dimension()
            print(f"[Embedder] Ready. Dimension: {self.dimension}")

        elif self.provider == "openai":
            import openai
            self.client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            self.dimension = 1536  # text-embedding-3-small
            print("[Embedder] Using OpenAI embeddings.")

        elif self.provider == "voyage":
            import voyageai
            self.client = voyageai.Client(api_key=os.getenv("VOYAGE_API_KEY"))
            self.dimension = 1024
            print("[Embedder] Using Voyage AI embeddings.")

        else:
            raise ValueError(f"Unknown embedding provider: {self.provider}")

    def embed(self, texts: List[str]) -> np.ndarray:
        """Embed a batch of texts. Returns numpy array shape (N, dim)."""
        if not texts:
            return np.array([])

        if self.provider == "local":
            embeddings = self.model.encode(
                texts,
                batch_size=32,
                show_progress_bar=len(texts) > 50,
                normalize_embeddings=True,
                convert_to_numpy=True,
            )
            return embeddings

        elif self.provider == "openai":
            response = self.client.embeddings.create(
                model="text-embedding-3-small",
                input=texts,
            )
            return np.array([e.embedding for e in response.data])

        elif self.provider == "voyage":
            result = self.client.embed(texts, model="voyage-3")
            return np.array(result.embeddings)

    def embed_query(self, query: str) -> np.ndarray:
        """Embed a single query string."""
        return self.embed([query])[0]


# Singleton
_embedder = None

def get_embedder() -> Embedder:
    global _embedder
    if _embedder is None:
        _embedder = Embedder()
    return _embedder
