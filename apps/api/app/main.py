from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from apps.api.app.api.admin_policies import router as admin_policies_router
from apps.api.app.api.admin_sources import router as admin_sources_router
from apps.api.app.api.assistant import router as assistant_router
from apps.api.app.api.operations import router as operations_router
from apps.api.app.api.profile import router as profile_router
from apps.api.app.api.search import router as search_router
from apps.api.app.auth.identity import Auth0IdentityProvider, FixtureIdentityProvider
from apps.api.app.config import Settings, get_settings
from apps.api.app.repositories.database import InMemoryCanonicalDatabase, MongoCanonicalDatabase
from apps.api.app.repositories.foundation_persistence import (
    FixtureFoundationPersistence,
    FoundationPersistence,
    MongoFoundationPersistence,
)
from apps.api.app.services.assistant_service import AssistantService
from apps.api.app.services.audit_service import AuditService
from apps.api.app.services.fixture_seed import seed_fixture_data
from apps.api.app.services.foundation_store import FoundationStore
from apps.api.app.services.metrics import MetricsRegistry
from apps.api.app.services.policy_reader_service import PolicyReaderService
from apps.api.app.services.policy_service import PolicyService
from apps.api.app.services.storage_service import LocalArtifactStore, S3ArtifactStore
from services.assistant.answer_generator import (
    DeepSeekLLMProvider,
    FixtureLLMProvider,
    LLMProvider,
    UnavailableLLMProvider,
)
from services.assistant.answerability import FixtureAnswerabilityGate
from services.assistant.citations import CitationValidator
from services.assistant.grounding import GroundingVerifier
from services.ingestion.chunking.semantic_chunker import SectionAwareFixtureChunker
from services.ingestion.embeddings.base import FixtureEmbeddingProvider
from services.ingestion.extractors.azure_document_intelligence import (
    AzureDocumentIntelligenceParser,
)
from services.ingestion.extractors.base import DocumentParser
from services.ingestion.extractors.docling import DoclingDocumentParser
from services.ingestion.extractors.fixtures import FixtureDocumentParser
from services.ingestion.extractors.router import ParserRouter
from services.ingestion.indexing.pinecone_index import (
    FixtureRetrievalIndex,
    PineconeRetrievalIndex,
)
from services.ingestion.pipeline import IngestionPipeline
from services.ingestion.structure.canonical_document import Canonicalizer
from services.retrieval.authorization_filter import AuthorizationFilter
from services.retrieval.fusion import ReciprocalRankFusion
from services.retrieval.lexical_search import FixtureLexicalRetriever
from services.retrieval.reranker import FixtureReranker
from services.retrieval.retriever import RetrievalService
from services.retrieval.semantic_search import FixtureSemanticRetriever, PineconeSemanticRetriever


def build_parser(settings: Settings) -> DocumentParser:
    fixture = FixtureDocumentParser()
    azure = AzureDocumentIntelligenceParser(
        settings.azure_document_intelligence_endpoint,
        settings.azure_document_intelligence_key.get_secret_value()
        if settings.azure_document_intelligence_key
        else None,
    )
    providers: dict[str, list[DocumentParser]] = {
        "fixture": [fixture],
        "azure": [azure, fixture],
        "docling": [DoclingDocumentParser(), fixture],
        "auto": [azure, DoclingDocumentParser(), fixture],
    }
    return ParserRouter(providers[settings.document_parser_provider])


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    app.state.settings = settings
    app.state.metrics = MetricsRegistry()
    if settings.app_mode == "fixture":
        app.state.identity_provider = FixtureIdentityProvider()
        app.state.database = InMemoryCanonicalDatabase()
        app.state.artifact_store = LocalArtifactStore(Path(".data"))
        app.state.foundation_persistence = FixtureFoundationPersistence()
    else:
        app.state.identity_provider = Auth0IdentityProvider(settings)
        app.state.database = MongoCanonicalDatabase(settings.mongodb_uri, settings.mongodb_database)
        if not settings.s3_access_key_id or not settings.s3_secret_access_key:
            raise ValueError("S3 credentials are required in live mode")
        app.state.artifact_store = S3ArtifactStore(
            settings.s3_bucket,
            settings.s3_region,
            settings.s3_endpoint_url,
            settings.s3_access_key_id.get_secret_value(),
            settings.s3_secret_access_key.get_secret_value(),
        )
        app.state.foundation_persistence = MongoFoundationPersistence(
            settings.mongodb_uri, settings.mongodb_database
        )
    app.state.foundation_store = FoundationStore()
    await app.state.foundation_persistence.load(app.state.foundation_store)
    app.state.ingestion_pipeline = IngestionPipeline(
        build_parser(settings),
        Canonicalizer(),
        app.state.artifact_store,
        app.state.foundation_store,
        app.state.metrics,
    )
    if settings.app_mode == "fixture":
        app.state.retrieval_index = FixtureRetrievalIndex()
    else:
        if not settings.pinecone_api_key:
            raise ValueError("Pinecone API key is required in live mode")
        app.state.retrieval_index = PineconeRetrievalIndex(
            settings.pinecone_api_key.get_secret_value(),
            settings.pinecone_index,
            settings.pinecone_namespace_prefix,
        )
    app.state.audit_service = AuditService(app.state.foundation_store)
    app.state.policy_service = PolicyService(
        app.state.foundation_store,
        SectionAwareFixtureChunker(),
        FixtureEmbeddingProvider(),
        app.state.retrieval_index,
        app.state.audit_service,
    )
    if settings.app_mode == "fixture":
        await seed_fixture_data(app)
    authorization = AuthorizationFilter(app.state.foundation_store)
    semantic = (
        FixtureSemanticRetriever(FixtureEmbeddingProvider())
        if settings.app_mode == "fixture"
        else PineconeSemanticRetriever(
            settings.pinecone_api_key.get_secret_value()
            if settings.pinecone_api_key
            else "",
            settings.pinecone_index,
            settings.pinecone_namespace_prefix,
            FixtureEmbeddingProvider(),
        )
    )
    app.state.retrieval_service = RetrievalService(
        app.state.foundation_store,
        authorization,
        FixtureLexicalRetriever(),
        semantic,
        ReciprocalRankFusion(),
        FixtureReranker(),
        app.state.metrics,
    )
    app.state.policy_reader_service = PolicyReaderService(
        app.state.foundation_store, authorization, app.state.artifact_store
    )
    llm_provider: LLMProvider
    if settings.llm_provider == "deepseek" and settings.deepseek_api_key:
        llm_provider = DeepSeekLLMProvider(
            settings.deepseek_api_key.get_secret_value(),
            settings.deepseek_base_url,
            settings.deepseek_model,
        )
    elif settings.llm_provider == "fixture":
        llm_provider = FixtureLLMProvider()
    else:
        llm_provider = UnavailableLLMProvider()
    app.state.assistant_service = AssistantService(
        app.state.foundation_store,
        app.state.retrieval_service,
        FixtureAnswerabilityGate(),
        llm_provider,
        CitationValidator(),
        GroundingVerifier(),
        app.state.metrics,
    )
    structlog.get_logger().info("application_started", mode=settings.app_mode)
    yield
    await app.state.foundation_persistence.flush(app.state.foundation_store)
    await app.state.foundation_persistence.close()


settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.web_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(profile_router, prefix=settings.api_prefix)
app.include_router(admin_sources_router, prefix=settings.api_prefix)
app.include_router(admin_policies_router, prefix=settings.api_prefix)
app.include_router(search_router, prefix=settings.api_prefix)
app.include_router(assistant_router, prefix=settings.api_prefix)
app.include_router(operations_router, prefix=settings.api_prefix)


@app.middleware("http")
async def persist_successful_mutations(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    response = await call_next(request)
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and response.status_code < 400:
        persistence: FoundationPersistence = request.app.state.foundation_persistence
        await persistence.flush(request.app.state.foundation_store)
    return response


@app.middleware("http")
async def observe_requests(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    request_id = request.headers.get("X-Request-ID") or uuid4().hex
    started = perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        request.app.state.metrics.observe(
            "http_request", (perf_counter() - started) * 1000, failed=True
        )
        structlog.get_logger().exception(
            "request_failed", request_id=request_id, method=request.method, path=request.url.path
        )
        raise
    duration_ms = (perf_counter() - started) * 1000
    request.app.state.metrics.observe(
        "http_request", duration_ms, failed=response.status_code >= 500
    )
    response.headers["X-Request-ID"] = request_id
    structlog.get_logger().info(
        "request_completed",
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=round(duration_ms, 2),
    )
    return response


@app.get("/health", tags=["operations"])
async def health() -> dict[str, str]:
    return {"status": "ok", "mode": settings.app_mode}
