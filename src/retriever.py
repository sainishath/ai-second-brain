"""
retriever.py — Hybrid Search Engine
Combines dense vector search (ChromaDB) + BM25 keyword search.
Optional reranking for maximum precision.
"""

import os
from typing import List, Dict, Any
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", ".env"))

_ROOT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


class HybridRetriever:
    """
    Two-stage retrieval:
      1. Dense search (semantic similarity via embeddings)
      2. BM25 keyword search
      3. Reciprocal Rank Fusion to merge results
    Optional: Cross-encoder reranking for final precision boost.
    """

    def __init__(self):
        import chromadb
        from embedder import get_embedder

        _chroma_path = os.getenv("CHROMA_PERSIST_DIR", os.path.join(_ROOT_DIR, "data", "chroma_db"))
        if not os.path.isabs(_chroma_path):
            _chroma_path = os.path.join(_ROOT_DIR, _chroma_path)
        self.chroma = chromadb.PersistentClient(path=_chroma_path)
        self.collection = self.chroma.get_or_create_collection(
            name=os.getenv("CHROMA_COLLECTION_NAME", "second_brain"),
            metadata={"hnsw:space": "cosine"},
        )
        self.embedder = get_embedder()
        self.n_results = int(os.getenv("MAX_RESULTS", 8))

    def dense_search(self, query: str, n: int = None) -> List[Dict]:
        """Semantic search using embeddings."""
        n = n or self.n_results * 2
        query_embedding = self.embedder.embed_query(query)

        results = self.collection.query(
            query_embeddings=[query_embedding.tolist()],
            n_results=min(n, self.collection.count() or 1),
            include=["documents", "metadatas", "distances"],
        )

        hits = []
        for i, doc in enumerate(results["documents"][0]):
            hits.append({
                "content": doc,
                "metadata": results["metadatas"][0][i],
                "score": 1 - results["distances"][0][i],  # cosine sim
                "source": "dense",
            })
        return hits

    def bm25_search(self, query: str, n: int = None) -> List[Dict]:
        """BM25 keyword-based search over all stored documents."""
        from rank_bm25 import BM25Okapi

        n = n or self.n_results * 2

        # Get all documents (for personal knowledge base, this is fine)
        all_docs = self.collection.get(include=["documents", "metadatas"])
        if not all_docs["documents"]:
            return []

        docs = all_docs["documents"]
        metas = all_docs["metadatas"]

        # Tokenize
        tokenized = [d.lower().split() for d in docs]
        bm25 = BM25Okapi(tokenized)

        query_tokens = query.lower().split()
        scores = bm25.get_scores(query_tokens)

        # Get top-n indices
        import numpy as np
        top_indices = np.argsort(scores)[::-1][:n]

        hits = []
        for idx in top_indices:
            if scores[idx] > 0:
                hits.append({
                    "content": docs[idx],
                    "metadata": metas[idx],
                    "score": float(scores[idx]),
                    "source": "bm25",
                })
        return hits

    def reciprocal_rank_fusion(
        self,
        dense_hits: List[Dict],
        bm25_hits: List[Dict],
        k: int = 60,
    ) -> List[Dict]:
        """
        Merge dense + BM25 results using Reciprocal Rank Fusion.
        RRF score = Σ 1/(k + rank_i)
        """
        scores: Dict[str, float] = {}
        docs_map: Dict[str, Dict] = {}

        for rank, hit in enumerate(dense_hits):
            key = hit["content"][:100]  # use content snippet as key
            scores[key] = scores.get(key, 0) + 1 / (k + rank + 1)
            docs_map[key] = hit

        for rank, hit in enumerate(bm25_hits):
            key = hit["content"][:100]
            scores[key] = scores.get(key, 0) + 1 / (k + rank + 1)
            if key not in docs_map:
                docs_map[key] = hit

        # Sort by fused score
        sorted_keys = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
        results = []
        for key in sorted_keys:
            hit = docs_map[key].copy()
            hit["rrf_score"] = scores[key]
            results.append(hit)

        return results

    def retrieve(self, query: str, n: int = None) -> List[Dict]:
        """
        Main retrieval method.
        Returns top-n most relevant chunks for the query.
        """
        n = n or self.n_results

        dense = self.dense_search(query, n=n * 2)
        bm25 = self.bm25_search(query, n=n * 2)
        merged = self.reciprocal_rank_fusion(dense, bm25)

        return merged[:n]

    def format_context(self, hits: List[Dict]) -> str:
        """Format retrieved chunks into a context block for the LLM."""
        parts = []
        for i, hit in enumerate(hits, 1):
            meta = hit["metadata"]
            title = meta.get("title", "Unknown")
            source = meta.get("source", "")
            source_type = meta.get("source_type", "")
            parts.append(
                f"[{i}] Source: {title} ({source_type}: {source})\n{hit['content']}"
            )
        return "\n\n---\n\n".join(parts)

    def stats(self) -> Dict[str, Any]:
        """Return knowledge base statistics."""
        count = self.collection.count()
        return {
            "total_chunks": count,
            "estimated_documents": max(1, count // 10),
            "vector_store": "ChromaDB",
            "embedding_provider": os.getenv("EMBEDDING_PROVIDER", "local"),
        }
