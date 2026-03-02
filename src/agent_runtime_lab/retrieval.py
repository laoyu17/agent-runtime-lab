"""Lightweight local retrieval for v0.1 RAG support."""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

_TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9_\u4e00-\u9fff]+")


def chunk_text(text: str, chunk_size: int = 500) -> list[str]:
    """Split text into fixed-size chunks."""

    if chunk_size < 1:
        raise ValueError("chunk_size must be >= 1")
    if not text:
        return []
    return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]


def _tokenize(text: str) -> list[str]:
    return [token.lower() for token in _TOKEN_PATTERN.findall(text)]


class SimpleVectorizer:
    """Term-frequency vectorizer with sparse dict output."""

    def vectorize(self, text: str) -> dict[str, float]:
        vector: dict[str, float] = {}
        for token in _tokenize(text):
            vector[token] = vector.get(token, 0.0) + 1.0
        return vector


def _dot(left: dict[str, float], right: dict[str, float]) -> float:
    if len(left) > len(right):
        left, right = right, left
    return sum(value * right.get(key, 0.0) for key, value in left.items())


def _norm(vector: dict[str, float]) -> float:
    return math.sqrt(sum(value * value for value in vector.values()))


def cosine_similarity(left: dict[str, float], right: dict[str, float]) -> float:
    """Cosine similarity for sparse vectors."""

    denominator = _norm(left) * _norm(right)
    if denominator == 0:
        return 0.0
    return _dot(left, right) / denominator


@dataclass(slots=True)
class RetrievedChunk:
    """Single retrieval hit."""

    chunk_id: str
    text: str
    score: float
    source: str | None = None


@dataclass(slots=True)
class _StoredChunk:
    chunk_id: str
    text: str
    source: str | None
    vector: dict[str, float]


class Retriever:
    """In-memory retriever for local RAG experiments."""

    def __init__(
        self,
        chunk_size: int = 500,
        top_k: int = 4,
        vectorizer: SimpleVectorizer | None = None,
    ) -> None:
        if top_k < 1:
            raise ValueError("top_k must be >= 1")
        self.chunk_size = chunk_size
        self.top_k = top_k
        self._vectorizer = vectorizer or SimpleVectorizer()
        self._chunks: list[_StoredChunk] = []

    def clear(self) -> None:
        self._chunks.clear()

    def ingest(self, documents: Sequence[str], source_prefix: str = "doc") -> int:
        """Index all text chunks from input documents."""

        added = 0
        for doc_index, document in enumerate(documents):
            source = f"{source_prefix}:{doc_index}"
            for chunk_index, chunk in enumerate(chunk_text(document, self.chunk_size)):
                chunk_id = f"{source}:{chunk_index}"
                self._chunks.append(
                    _StoredChunk(
                        chunk_id=chunk_id,
                        text=chunk,
                        source=source,
                        vector=self._vectorizer.vectorize(chunk),
                    )
                )
                added += 1
        return added

    def search(self, query: str, top_k: int | None = None) -> list[RetrievedChunk]:
        """Search indexed chunks by cosine similarity."""

        if not query.strip():
            return []
        query_vec = self._vectorizer.vectorize(query)
        limit = top_k if top_k is not None else self.top_k
        scored: list[tuple[float, _StoredChunk]] = []
        for chunk in self._chunks:
            score = cosine_similarity(query_vec, chunk.vector)
            if score > 0:
                scored.append((score, chunk))
        scored.sort(key=lambda item: item[0], reverse=True)

        return [
            RetrievedChunk(
                chunk_id=item.chunk_id,
                text=item.text,
                score=score,
                source=item.source,
            )
            for score, item in scored[:limit]
        ]


def inject_context(base_prompt: str, chunks: Iterable[RetrievedChunk]) -> str:
    """Append retrieved context snippets to prompt."""

    lines = [base_prompt.strip(), "", "[Retrieved Context]"]
    for index, chunk in enumerate(chunks, start=1):
        source = chunk.source or "unknown"
        lines.append(f"{index}. ({source}, score={chunk.score:.3f}) {chunk.text}")
    return "\n".join(line for line in lines if line)


__all__ = [
    "RetrievedChunk",
    "Retriever",
    "SimpleVectorizer",
    "chunk_text",
    "cosine_similarity",
    "inject_context",
]
