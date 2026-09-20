from services.ingestion.embeddings.base import EmbeddingProvider


class EmbeddingUnavailableError(RuntimeError):
    """Raised when an embedding operation is requested in live mode
    before a production embedding provider is configured."""

    pass


class UnavailableEmbeddingProvider(EmbeddingProvider):
    model_id = "unavailable-provisional"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise EmbeddingUnavailableError(
            "Production embedding model provider has not been configured for live mode. "
            "Fixture fallback embeddings are explicitly prohibited in live mode."
        )
