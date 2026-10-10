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
            {"input_type": "passage", "truncate": "END"},
        ),
        (
            "multilingual-e5-large",
            ["question"],
            {"input_type": "query", "truncate": "END"},
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
