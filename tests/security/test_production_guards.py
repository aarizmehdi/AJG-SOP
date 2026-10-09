import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from apps.api.app.auth.dependencies import current_profile
from apps.api.app.auth.identity import AuthenticatedIdentity
from apps.api.app.config import Settings
from apps.api.app.repositories.database import InMemoryCanonicalDatabase
from services.ingestion.embeddings.unavailable import (
    EmbeddingUnavailableError,
    UnavailableEmbeddingProvider,
)


def test_unavailable_embedding_provider_raises_error():
    """Verify that UnavailableEmbeddingProvider raises EmbeddingUnavailableError in live mode."""
    provider = UnavailableEmbeddingProvider()
    with pytest.raises(EmbeddingUnavailableError, match="Production embedding model provider"):
        import asyncio

        asyncio.run(provider.embed_documents(["test text"]))


@pytest.mark.asyncio
async def test_fixture_identity_prohibited_in_live_mode():
    """Verify that current_profile rejects fixture identity subjects in live mode."""

    class DummyRequest:
        def __init__(self):
            live_settings = Settings(
                app_mode="live",
                web_origin="https://app.example.com",
                mongodb_uri="mongodb://remote:27017",
                firebase_project_id="ajg-sop-web",
                firebase_service_account_json="{}",
                pinecone_api_key="test-key",
                deepseek_api_key="test-key",
                embedding_provider="e5",
                s3_access_key_id="test-access",
                s3_secret_access_key="test-secret",
            )
            self.app = type(
                "App", (), {"state": type("State", (), {"settings": live_settings})()}
            )()
            self.state = type("RequestState", (), {})()

    request = DummyRequest()
    identity = AuthenticatedIdentity(subject="fixture|employee", claims={"fixture": True})

    with pytest.raises(HTTPException) as exc_info:
        await current_profile(request, identity)

    assert exc_info.value.status_code == 403
    assert "Fixture identity prohibited in live mode" in exc_info.value.detail


def test_live_mode_requires_mongodb_uri():
    """Verify Settings raises validation error if APP_MODE=live but MONGODB_URI is absent."""
    with pytest.raises((ValueError, ValidationError)):
        Settings(
            app_mode="live",
            web_origin="https://app.example.com",
            mongodb_uri=None,
            firebase_project_id="ajg-sop-web",
            firebase_service_account_json="{}",
            pinecone_api_key="test-key",
            deepseek_api_key="test-key",
            embedding_provider="e5",
            s3_access_key_id="test-access",
            s3_secret_access_key="test-secret",
        )


def test_live_mode_prohibits_fixture_embeddings() -> None:
    with pytest.raises((ValueError, ValidationError), match="e5"):
        Settings(
            app_mode="live",
            web_origin="https://app.example.com",
            mongodb_uri="mongodb://remote:27017",
            firebase_project_id="ajg-sop-web",
            firebase_service_account_json="{}",
            pinecone_api_key="test-key",
            deepseek_api_key="test-key",
            s3_access_key_id="test-access",
            s3_secret_access_key="test-secret",
            embedding_provider="fixture",
        )


def test_current_deepseek_model_is_the_supported_flash_identifier() -> None:
    assert Settings.model_fields["deepseek_model"].default == "deepseek-flash"


@pytest.mark.asyncio
async def test_unknown_firebase_user_is_not_auto_provisioned_or_email_linked() -> None:
    database = InMemoryCanonicalDatabase()
    existing_admin = {
        "id": "existing-admin",
        "organization_id": "ajt",
        "identity_subject": "legacy-provider|existing-subject",
        "display_name": "Existing Admin",
        "email": "owner@example.test",
        "application_roles": ["employee", "sop_admin", "system_admin"],
        "departments": ["management"],
        "locations": ["head-office"],
        "organizational_roles": ["admin"],
        "preferred_language": "english",
        "active": True,
    }
    database.collections["employee_profiles"] = [existing_admin]

    live_settings = Settings(
        app_mode="live",
        web_origin="https://app.example.com",
        mongodb_uri="mongodb://remote:27017",
        firebase_project_id="ajg-sop-web",
        firebase_service_account_json="{}",
        pinecone_api_key="test-key",
        deepseek_api_key="test-key",
        embedding_provider="e5",
        s3_access_key_id="test-access",
        s3_secret_access_key="test-secret",
    )
    state = type("State", (), {"settings": live_settings, "database": database})()
    request = type(
        "Request",
        (),
        {"app": type("App", (), {"state": state})(), "state": type("RequestState", (), {})()},
    )()
    unknown = AuthenticatedIdentity(
        subject="firebase-unknown-uid",
        claims={"email": "owner@example.test", "name": "Same Email"},
    )

    with pytest.raises(HTTPException) as exc_info:
        await current_profile(request, unknown)

    assert exc_info.value.status_code == 403
    assert database.collections["employee_profiles"] == [existing_admin]
    assert existing_admin["identity_subject"] == "legacy-provider|existing-subject"


def test_llm_provider_defaults_to_deepseek() -> None:
    settings = Settings()
    assert settings.llm_provider == "deepseek"


def test_invalid_llm_provider_raises_validation_error() -> None:
    with pytest.raises(ValidationError):
        Settings(llm_provider="unauthorized_ai")


def test_live_mode_fails_fast_missing_keys() -> None:
    with pytest.raises(
        ValueError,
        match="Missing required live configuration:.*DEEPSEEK_API_KEY",
    ):
        Settings(
            app_mode="live",
            web_origin="https://app.example.com",
            mongodb_uri="mongodb://remote:27017",
        )


def test_embedding_provider_e5_and_pinecone_e5_aliases() -> None:
    # Assert both embedding_provider="e5" and embedding_provider="pinecone_e5" initialize Settings without validation errors.
    valid_e5 = Settings(
        app_mode="live",
        web_origin="https://app.example.com",
        mongodb_uri="mongodb://remote:27017",
        firebase_project_id="ajg-sop-web",
        firebase_service_account_json="{}",
        pinecone_api_key="test-key",
        deepseek_api_key="test-key",
        s3_access_key_id="test-access",
        s3_secret_access_key="test-secret",
        embedding_provider="e5",
    )
    valid_pinecone_e5 = Settings(
        app_mode="live",
        web_origin="https://app.example.com",
        mongodb_uri="mongodb://remote:27017",
        firebase_project_id="ajg-sop-web",
        firebase_service_account_json="{}",
        pinecone_api_key="test-key",
        deepseek_api_key="test-key",
        s3_access_key_id="test-access",
        s3_secret_access_key="test-secret",
        embedding_provider="pinecone_e5",
    )
    assert valid_e5.embedding_provider == "e5"
    assert valid_pinecone_e5.embedding_provider == "pinecone_e5"


def test_live_mode_prohibits_fixture_llm_and_retriever() -> None:
    # Assert that when app_mode="live", attempting to set llm_provider="fixture" raises a fail-fast ValueError.
    with pytest.raises((ValueError, ValidationError)):
        Settings(
            app_mode="live",
            web_origin="https://app.example.com",
            mongodb_uri="mongodb://remote:27017",
            firebase_project_id="ajg-sop-web",
            firebase_service_account_json="{}",
            pinecone_api_key="test-key",
            deepseek_api_key="test-key",
            s3_access_key_id="test-access",
            s3_secret_access_key="test-secret",
            llm_provider="fixture",
        )
