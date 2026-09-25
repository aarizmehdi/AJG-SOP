from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    model_id: str
    dimension: int

    @abstractmethod
    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError

    @abstractmethod
    async def embed_query(self, text: str) -> list[float]:
        raise NotImplementedError


class FixtureEmbeddingProvider(EmbeddingProvider):
    """Deterministic test embedding. Model selection remains provisional."""

    model_id = "fixture-hash-v1-provisional"
    dimension = 32

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._vector(text)

    @staticmethod
    def _vector(text: str, dimensions: int = 32) -> list[float]:
        vector = [0.0] * dimensions
        for token in text.casefold().split():
            vector[hash(token) % dimensions] += 1.0
        magnitude = sum(value * value for value in vector) ** 0.5 or 1.0
        return [value / magnitude for value in vector]
