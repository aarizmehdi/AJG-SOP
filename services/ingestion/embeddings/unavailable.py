from services.ingestion.embeddings.base import EmbeddingProvider


class EmbeddingUnavailableError(RuntimeError):
    """Raised when an embedding operation is requested in live mode
    before a production embedding provider is configured."""

    pass


class UnavailableEmbeddingProvider(EmbeddingProvider):
    model_id = "unavailable-provisional"
    dimension = 0

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        raise EmbeddingUnavailableError(
            "Production embedding model provider has not been configured for live mode. "
            "Fixture fallback embeddings are explicitly prohibited in live mode."
        )

    async def embed_query(self, text: str) -> list[float]:
        raise EmbeddingUnavailableError(
            "Production embedding model provider has not been configured for live mode. "
            "Fixture fallback embeddings are explicitly prohibited in live mode."
        )
