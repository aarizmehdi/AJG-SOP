from types import SimpleNamespace

import pytest

from services.ingestion.embeddings.pinecone_e5 import (
    EmbeddingConfigurationError,
    EmbeddingDimensionError,
    PineconeE5EmbeddingProvider,
)


class FakeInference:
    def __init__(self, dimension: int = 4) -> None:
        self.dimension = dimension
        self.calls: list[tuple[str, list[str], dict[str, str]]] = []

    def get_model(self, *, model: str) -> SimpleNamespace:
        return SimpleNamespace(model=model, default_dimension=self.dimension)

    def embed(
        self, model: str, inputs: list[str], parameters: dict[str, str]
    ) -> SimpleNamespace:
        self.calls.append((model, inputs, parameters))
        return SimpleNamespace(
            data=[
                SimpleNamespace(values=[float(index + 1)] * self.dimension)
                for index, _ in enumerate(inputs)
            ]
        )


class FakePinecone:
    def __init__(
        self,
        *,
        index_model: str = "multilingual-e5-large",
        model_dimension: int = 4,
        index_dimension: int = 4,
    ) -> None:
        self.inference = FakeInference(model_dimension)
        self.index_model = index_model
        self.index_dimension = index_dimension

    def describe_index(self, index_name: str) -> SimpleNamespace:
        return SimpleNamespace(name=index_name, embed=SimpleNamespace(model=self.index_model))

    def Index(self, index_name: str) -> SimpleNamespace:  # noqa: N802
        return SimpleNamespace(
            describe_index_stats=lambda: SimpleNamespace(dimension=self.index_dimension)
        )


@pytest.mark.asyncio
async def test_e5_uses_passage_for_documents_and_query_for_questions() -> None:
    client = FakePinecone()
    provider = PineconeE5EmbeddingProvider(
        "secret-not-used",
        "aziz-jan-sop",
        "multilingual-e5-large",
        client=client,
    )

    documents = await provider.embed_documents(["first", "second"])
    query = await provider.embed_query("question")

    assert provider.dimension == 4
    assert len(documents) == 2
    assert len(query) == 4
    assert client.inference.calls == [
        (
            "multilingual-e5-large",
            ["first", "second"],
            {"input_type": "passage", "truncate": "NONE"},
        ),
        (
            "multilingual-e5-large",
            ["question"],
            {"input_type": "query", "truncate": "NONE"},
        ),
    ]


def test_e5_rejects_model_mismatch() -> None:
    with pytest.raises(EmbeddingConfigurationError, match="index model"):
        PineconeE5EmbeddingProvider(
            "secret-not-used",
            "aziz-jan-sop",
            "multilingual-e5-large",
            client=FakePinecone(index_model="different-model"),
        )


def test_e5_rejects_dimension_mismatch() -> None:
    with pytest.raises(EmbeddingDimensionError, match="does not match"):
        PineconeE5EmbeddingProvider(
            "secret-not-used",
            "aziz-jan-sop",
            "multilingual-e5-large",
            client=FakePinecone(model_dimension=1024, index_dimension=384),
        )


@pytest.mark.asyncio
async def test_production_e5_batches_inputs_at_most_64_and_preserves_order() -> None:
    class UniqueVectorFakeInference(FakeInference):
        def embed(
            self, model: str, inputs: list[str], parameters: dict[str, str]
        ) -> SimpleNamespace:
            self.calls.append((model, inputs, parameters))
            data = [
                SimpleNamespace(values=[float(item.split("_")[1])] * self.dimension)
                for item in inputs
            ]
            return SimpleNamespace(data=data)

    client = FakePinecone()
    client.inference = UniqueVectorFakeInference(dimension=4)

    provider = PineconeE5EmbeddingProvider(
        "secret-not-used",
        "aziz-jan-sop",
        "multilingual-e5-large",
        client=client,
    )

    input_count = 219
    inputs = [f"input_{i}" for i in range(input_count)]
    vectors = await provider.embed_documents(inputs)

    assert len(client.inference.calls) == 4
    for model, batch_inputs, params in client.inference.calls:
        assert len(batch_inputs) <= PineconeE5EmbeddingProvider.BATCH_SIZE
        assert len(batch_inputs) <= 64
        assert model == "multilingual-e5-large"
        assert params == {"input_type": "passage", "truncate": "NONE"}

    assert len(vectors) == input_count
    for i, vec in enumerate(vectors):
        assert vec == [float(i)] * 4


@pytest.mark.asyncio
async def test_production_e5_empty_inputs_returns_empty() -> None:
    client = FakePinecone()
    provider = PineconeE5EmbeddingProvider(
        "secret-not-used",
        "aziz-jan-sop",
        "multilingual-e5-large",
        client=client,
    )
    assert await provider.embed_documents([]) == []
    assert len(client.inference.calls) == 0


@pytest.mark.asyncio
async def test_production_e5_retries_on_http_429() -> None:
    class RateLimitedFakeInference(FakeInference):
        def __init__(self, dimension: int = 4) -> None:
            super().__init__(dimension)
            self.attempts = 0

        def embed(
            self, model: str, inputs: list[str], parameters: dict[str, str]
        ) -> SimpleNamespace:
            self.attempts += 1
            if self.attempts == 1:
                class HTTP429Error(RuntimeError):
                    status = 429
                raise HTTP429Error("Rate limit exceeded 429")
            return super().embed(model, inputs, parameters)

    client = FakePinecone()
    client.inference = RateLimitedFakeInference(dimension=4)

    provider = PineconeE5EmbeddingProvider(
        "secret-not-used",
        "aziz-jan-sop",
        "multilingual-e5-large",
        client=client,
    )

    vectors = await provider.embed_documents(["doc1", "doc2"])
    assert len(vectors) == 2
    assert client.inference.attempts == 2


@pytest.mark.asyncio
async def test_production_e5_dimension_mismatch_during_embed() -> None:
    class WrongDimensionInference(FakeInference):
        def embed(
            self, model: str, inputs: list[str], parameters: dict[str, str]
        ) -> SimpleNamespace:
            return SimpleNamespace(
                data=[SimpleNamespace(values=[1.0, 2.0]) for _ in inputs]
            )

    client = FakePinecone(model_dimension=4, index_dimension=4)
    client.inference = WrongDimensionInference(dimension=4)

    provider = PineconeE5EmbeddingProvider(
        "secret-not-used",
        "aziz-jan-sop",
        "multilingual-e5-large",
        client=client,
    )

    with pytest.raises(EmbeddingDimensionError, match="does not match expected 4"):
        await provider.embed_documents(["doc1"])
