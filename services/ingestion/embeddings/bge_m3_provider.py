from collections.abc import Sequence

from services.ingestion.embeddings.base import EmbeddingProvider


class BGEM3EmbeddingProvider(EmbeddingProvider):
    def __init__(self, use_fake_model: bool = False):
        self.use_fake_model = use_fake_model
        if self.use_fake_model:
            self._model = None
        else:
            try:
                # Lazy import flag embedding library (FlagEmbedding)
                from FlagEmbedding import BGEM3FlagModel  # type: ignore

                self._model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=True)
            except ImportError as err:
                raise ImportError(
                    "BGE-M3 library 'FlagEmbedding' is not installed. "
                    "Install with `pip install FlagEmbedding` to use bge_m3."
                ) from err

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if self.use_fake_model or self._model is None:
            return [[0.1] * 1024 for _ in texts]
        # In real usage we might batch it or use thread pool
        embeddings = self._model.encode(list(texts), batch_size=12, max_length=1024)["dense_vecs"]
        return [list(vec) for vec in embeddings]

    async def embed_query(self, query: str) -> list[float]:
        if self.use_fake_model or self._model is None:
            return [0.1] * 1024
        embedding = self._model.encode(query, max_length=1024)["dense_vecs"]
        return list(embedding)
