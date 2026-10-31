"""TF-IDF vectorizer and retrieval engine for offline technical manual search.

Uses scikit-learn TfidfVectorizer and cosine similarity to index industrial
documentation chunks and perform grounded retrieval without internet access.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Optional
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from src.models.diagnosis import DocumentSourceReference

logger = logging.getLogger(__name__)


class TFIDFIndex:
    """Thread-safe in-memory TF-IDF index for knowledge manual chunks."""

    def __init__(self) -> None:
        self.vectorizer: Optional[TfidfVectorizer] = None
        self.doc_vectors: Optional[Any] = None
        self.chunks: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def build_index(self, chunks: list[dict[str, Any]]) -> int:
        """Fit TF-IDF matrix over document chunk contents."""
        with self._lock:
            if not chunks:
                self.chunks = []
                self.vectorizer = None
                self.doc_vectors = None
                return 0

            texts = [c.get("content", "") for c in chunks]
            valid_texts = [t for t in texts if t.strip()]
            if not valid_texts:
                self.chunks = []
                self.vectorizer = None
                self.doc_vectors = None
                return 0

            self.chunks = list(chunks)
            self.vectorizer = TfidfVectorizer(
                stop_words="english",
                ngram_range=(1, 2),
                max_features=5000,
                sublinear_tf=True
            )
            self.doc_vectors = self.vectorizer.fit_transform(texts)
            logger.info("TF-IDF index built over %d document chunks", len(chunks))
            return len(chunks)

    def delete_document(self, doc_name: str) -> int:
        """Remove chunks belonging to doc_name and re-index remaining chunks."""
        with self._lock:
            remaining = [c for c in self.chunks if c.get("doc_name") != doc_name]
            removed_count = len(self.chunks) - len(remaining)
        self.build_index(remaining)
        return removed_count

    def search(self, query: str, top_k: int = 3, min_score: float = 0.02) -> list[dict[str, Any]]:
        """Retrieve top-K most relevant chunks using cosine similarity."""
        with self._lock:
            if self.vectorizer is None or self.doc_vectors is None or not self.chunks:
                return []

            if not query or not query.strip():
                return []

            try:
                query_vec = self.vectorizer.transform([query])
                scores = cosine_similarity(query_vec, self.doc_vectors).flatten()

                # Get indices of top scores
                top_indices = np.argsort(scores)[::-1][:top_k]

                results: list[dict[str, Any]] = []
                for idx in top_indices:
                    score = float(scores[idx])
                    if score >= min_score:
                        chunk_copy = dict(self.chunks[idx])
                        chunk_copy["score"] = round(score, 4)
                        # Ensure page number is accessible at top-level
                        page = chunk_copy.get("page") or chunk_copy.get("page_number") or chunk_copy.get("metadata", {}).get("page", 1)
                        chunk_copy["page"] = int(page)
                        results.append(chunk_copy)

                return results
            except Exception as exc:
                logger.error("Error executing TF-IDF search for query '%s': %s", query, exc)
                return []

    def search_source_references(
        self,
        query: str,
        top_k: int = 3,
        min_score: float = 0.05
    ) -> list[DocumentSourceReference]:
        """Retrieve verified document source references strictly from indexed content."""
        chunks = self.search(query=query, top_k=top_k, min_score=min_score)
        references: list[DocumentSourceReference] = []

        for c in chunks:
            doc_name = c.get("doc_name", "Unknown Document")
            page = int(c.get("page", c.get("metadata", {}).get("page", 1)))
            chunk_id = int(c.get("chunk_id", c.get("chunk_index", 0)))
            raw_content = c.get("content", "").strip()

            # Create clean, concise excerpt
            excerpt = raw_content[:280] + "..." if len(raw_content) > 280 else raw_content

            references.append(DocumentSourceReference(
                doc_name=doc_name,
                page_number=page,
                chunk_id=chunk_id,
                excerpt=excerpt,
                similarity_score=float(c.get("score", 0.0))
            ))

        return references

    @property
    def total_chunks(self) -> int:
        return len(self.chunks)
