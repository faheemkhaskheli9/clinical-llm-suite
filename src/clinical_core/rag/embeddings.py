"""Embedding provider interface (swappable, chunking-and-embedding-ingestion
knowledge-base pattern). `HashingEmbedder` is the default: a deterministic,
offline, CPU-only embedder so ingestion and tests never need a paid API key.
`OpenAIEmbedder` is provided as the real-provider swap-in but is not
exercised in tests — it requires OPENAI_API_KEY and network access, both
explicitly out of scope for this portfolio's CI.
"""

from __future__ import annotations

import hashlib
import math
from abc import ABC, abstractmethod
from typing import List

import numpy as np


class EmbeddingProvider(ABC):
    @abstractmethod
    def embed(self, texts: List[str]) -> List[np.ndarray]:
        raise NotImplementedError

    @property
    @abstractmethod
    def dimensions(self) -> int:
        raise NotImplementedError


class HashingEmbedder(EmbeddingProvider):
    """A deterministic bag-of-words hashing embedder: each token is hashed
    into one of `dimensions` buckets and counted, then L2-normalized. Not a
    semantic embedding, but sufficient to demonstrate/test a working
    ingestion + retrieval pipeline without any model download or API call.
    """

    def __init__(self, dimensions: int = 256):
        self._dimensions = dimensions

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def _embed_one(self, text: str) -> np.ndarray:
        vector = np.zeros(self._dimensions, dtype=np.float64)
        for token in text.lower().split():
            bucket = int(hashlib.sha256(token.encode("utf-8")).hexdigest(), 16) % self._dimensions
            vector[bucket] += 1.0
        norm = math.sqrt(float(np.dot(vector, vector)))
        if norm > 0:
            vector /= norm
        return vector

    def embed(self, texts: List[str]) -> List[np.ndarray]:
        return [self._embed_one(t) for t in texts]


class OpenAIEmbedder(EmbeddingProvider):
    """Real embedding provider swap-in. Requires `openai` and an API key —
    not used by tests or the default config (mocked boundary, per project
    robustness rules: no paid APIs in CPU-only test runs)."""

    def __init__(self, model: str = "text-embedding-3-small", dimensions: int = 1536, client=None):
        self._model = model
        self._dimensions = dimensions
        self._client = client  # injected lazily; see get_client()

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def _get_client(self):
        if self._client is None:
            import openai  # imported lazily so this class can exist without the dep installed

            self._client = openai.OpenAI()
        return self._client

    def embed(self, texts: List[str]) -> List[np.ndarray]:
        client = self._get_client()
        response = client.embeddings.create(model=self._model, input=texts)
        return [np.array(item.embedding, dtype=np.float64) for item in response.data]
