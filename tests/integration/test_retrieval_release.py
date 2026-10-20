"""Synthetic regressions for the final retrieval integration; no private SOP bodies."""

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from tokenizers import Tokenizer

from apps.api.app.auth.identity import FIXTURE_PROFILES
from apps.api.app.main import app
from packages.contracts.source import SourceDocument, SourceFormat
from services.ingestion.chunking.semantic_chunker import SemanticChunker
from services.ingestion.embeddings.pinecone_e5 import PineconeE5EmbeddingProvider
from services.ingestion.extractors.base import RawBlockKind
from services.ingestion.extractors.fixtures import FixtureDocumentParser
from services.ingestion.structure.canonical_document import Canonicalizer
from services.retrieval.lexical_search import FixtureLexicalRetriever
from services.retrieval.policy_references import policy_references
from services.retrieval.semantic_search import PineconeSemanticRetriever
from tests.unit.test_pinecone_e5 import FakePinecone


@pytest.mark.parametrize(
    "query,expected",
    [
        ("SOP # 89", "sop-89"),
        ("Sop# 2024/Gat/002", "sop-2024/gat/002"),
        ("SOP-014", "sop-014"),
        ("AJTM/STORE/SOP-1", "ajtm/store/sop-1"),
        ("SOP # 23.4-A", "sop-23.4-a"),
    ],
)
def test_complete_policy_references(query, expected):
    assert policy_references(query) == {expected}


def test_qualified_and_suffix_references_do_not_acquire_false_aliases():
    assert not policy_references("AJTM/STORE/SOP-1") & policy_references("AJTM/GATE/SOP-1")
    assert not policy_references("SOP # 2024/Gat/002") & policy_references("SOP # 2024/Gat/003")
    assert not policy_references("SOP # 89") & policy_references("SOP # 189")


@pytest.mark.asyncio
async def test_exact_reference_beats_many_unrelated_partial_terms():
    with TestClient(app) as client:
        profile = FIXTURE_PROFILES["fixture|employee"]
        prototype = client.app.state.retrieval_service.authorization.eligible_chunks(profile)[0]
        exact = prototype.model_copy(
            update={
                "id": "exact",
                "policy_number": None,
                "text": "Sop# 2024/Gat/002. Store signs the pass.",
            }
        )
        wrong = prototype.model_copy(
            update={
                "id": "partial",
                "policy_number": "SOP # 2024/Gat/003",
                "text": ("Who must sign the RGP according to SOP 2024 Gat 002? " * 50),
            }
        )
        results = await FixtureLexicalRetriever().search(
            "According to SOP # 2024/Gat/002, who must sign the RGP?", [wrong, exact], 2
        )
        assert results[0].chunk_id == "exact"


def test_bold_legacy_labels_are_conservative_and_hash_hierarchy_wins():
    parser = FixtureDocumentParser()
    legacy = parser._parse_markdown(
        b"# Manual\n\n**Document 1: SOP for Repairs**\n\n**RESPONSIBILITIES**\n\n**Employees must sign every repair note.**\n\n1. Inspect the item.\n  - Log the serial.\n\n**Important note**\n\nRetain the form.",  # noqa: E501
        "Manual",
    )
    headings = [b.text for b in legacy.blocks if b.kind == RawBlockKind.HEADING]
    assert headings == ["Manual", "Document 1: SOP for Repairs", "RESPONSIBILITIES"]
    assert any(b.text == "**Employees must sign every repair note.**" for b in legacy.blocks)
    assert any(b.text == "**Important note**" for b in legacy.blocks)
    assert legacy.warnings
    explicit = parser._parse_markdown(
        b"# Manual\n\n## Repairs\n\n**RESPONSIBILITIES**\n\nKeep the receipt.", "Manual"
    )
    assert [b.text for b in explicit.blocks if b.kind == RawBlockKind.HEADING] == [
        "Manual",
        "Repairs",
    ]
    assert not explicit.warnings


@pytest.mark.asyncio
async def test_exact_tokenizer_long_row_and_long_heading_preserve_source():
    path = Path(os.environ.get("AJG_TEST_E5_TOKENIZER_PATH", ".data/e5-tokenizer.json"))
    if not path.exists():  # noqa: ASYNC240 - local test fixture, no network
        pytest.skip("Pinned public tokenizer is not installed (CI installs it explicitly)")
    tokenizer = Tokenizer.from_file(str(path))
    tokenizer.enable_truncation(max_length=32)  # Chunker must disable accidental truncation.
    chunker = SemanticChunker(tokenizer=tokenizer, require_tokenizer=True)
    blob = "x" * 1800 + "ENDVALUE"
    markdown = (
        "# "
        + "Long heading " * 160
        + "\n\n| Row key | Value |\n| --- | --- |\n| "
        + blob
        + " | Authorized final value |\n"
    )
    source = SourceDocument(
        id="synthetic-source",
        organization_id="ajt",
        policy_id="synthetic-policy",
        version_id="synthetic-version",
        source_format=SourceFormat.MARKDOWN,
        file_name="synthetic.md",
        media_type="text/markdown",
        sha256="0" * 64,
        original_artifact_uri="synthetic/private.md",
    )
    raw = await FixtureDocumentParser().parse(source, markdown.encode())
    canonical = Canonicalizer().canonicalize(source, raw)
    chunks = chunker.chunk(canonical, "published")
    assert len(chunks) > 1
    assert all(chunker.count_embedding_tokens(c.text) <= chunker.HARD_MAX_TOKENS for c in chunks)
    assert [c.model_dump() for c in chunks] == [
        c.model_dump() for c in chunker.chunk(canonical, "published")
    ]
    reconstructed = "".join(
        line.split("column 1 value: ", 1)[1]
        for c in chunks
        for line in c.text.splitlines()
        if "column 1 value: " in line
    )
    assert reconstructed == blob
    assert any("Authorized final value" in c.text for c in chunks)
    assert all(
        c.heading_path == canonical.sections[0].heading_path
        and c.source.source_document_id == source.id
        and c.organization_id == "ajt"
        for c in chunks
    )


@pytest.mark.asyncio
async def test_oversized_embedding_rejected_without_retry_or_truncation():
    client = FakePinecone()
    attempts = []

    def reject(model, inputs, parameters):
        attempts.append(parameters)
        error = ValueError("Input exceeds supported sequence length")
        error.status = 400
        raise error

    client.inference.embed = reject
    provider = PineconeE5EmbeddingProvider(
        "unused", "existing-index", "multilingual-e5-large", client=client
    )
    with pytest.raises(ValueError, match="sequence length"):
        await provider.embed_documents(["synthetic " * 2000])
    assert attempts == [{"input_type": "passage", "truncate": "NONE"}]


@pytest.mark.asyncio
async def test_large_semantic_filter_partitions_remain_exact_and_globally_ranked():
    with TestClient(app) as client:
        profile = FIXTURE_PROFILES["fixture|employee"]
        prototype = client.app.state.retrieval_service.authorization.eligible_chunks(profile)[0]
        chunks = [prototype.model_copy(update={"id": f"allowed-{i}"}) for i in range(601)]
        calls = []

        class Index:
            def query(self, **kwargs):
                calls.append(kwargs)
                ids = kwargs["filter"]["$and"][2]["chunk_id"]["$in"]
                return SimpleNamespace(
                    matches=[
                        SimpleNamespace(id=ids[-1], score=float(len(calls))),
                        SimpleNamespace(id="DENIED", score=999),
                        SimpleNamespace(id=ids[0], score=float("nan")),
                    ]
                )

        class Embeddings:
            async def embed_query(self, text):
                return [1.0]

        retriever = PineconeSemanticRetriever(
            "unused", "existing-index", "test", Embeddings(), index=Index()
        )
        result = await retriever.search("synthetic policy", chunks, 3)
        assert len(calls) == 2
        assert [r.chunk_id for r in result] == ["allowed-600", "allowed-499"]
        queried = [i for c in calls for i in c["filter"]["$and"][2]["chunk_id"]["$in"]]
        assert queried == [c.id for c in chunks]
        assert all(
            c["filter"]["$and"][0] == {"organization_id": {"$eq": profile.organization_id}}
            for c in calls
        )
        assert all(
            c["filter"]["$and"][3] == {"version_id": {"$in": [prototype.version_id]}} for c in calls
        )


@pytest.mark.asyncio
async def test_retrieval_telemetry_never_retains_chunk_bodies():
    with TestClient(app) as client:
        profile = FIXTURE_PROFILES["fixture|employee"]
        service = client.app.state.retrieval_service
        await service.retrieve(profile, "damaged stock", 5)
        traces = service.telemetry(profile.organization_id)
        assert traces
        assert all(
            "text" not in item
            for trace in traces
            for key in ("lexical_candidates", "semantic_candidates")
            for item in trace[key]
        )
        assert "excerpt" not in json.dumps(traces)


@pytest.mark.asyncio
async def test_e5_transient_server_error_retries_bounded_without_truncation():
    client = FakePinecone()
    original = client.inference.embed
    calls = []

    def flaky(model, inputs, parameters):
        calls.append(parameters)
        if len(calls) == 1:
            error = RuntimeError("Synthetic transient availability failure")
            error.status = 500
            raise error
        return original(model, inputs, parameters)

    client.inference.embed = flaky
    provider = PineconeE5EmbeddingProvider(
        "unused", "existing-index", "multilingual-e5-large", client=client
    )
    assert len(await provider.embed_documents(["synthetic short passage"])) == 1
    assert calls == [{"input_type": "passage", "truncate": "NONE"}] * 2


def test_live_chunker_cannot_silently_use_fixture_estimation(monkeypatch):
    monkeypatch.delenv("E5_TOKENIZER_PATH", raising=False)
    with pytest.raises(ValueError, match="pinned E5_TOKENIZER_PATH"):
        SemanticChunker(require_tokenizer=True)
