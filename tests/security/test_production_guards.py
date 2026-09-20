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

        asyncio.run(provider.embed(["test text"]))


@pytest.mark.asyncio
async def test_fixture_identity_prohibited_in_live_mode():
    """Verify that current_profile rejects fixture identity subjects in live mode."""

    class DummyRequest:
        def __init__(self):
            live_settings = Settings(
                app_mode="live",
                web_origin="https://app.example.com",
                mongodb_uri="mongodb://localhost:27017",
                firebase_project_id="ajg-sop-web",
                firebase_service_account_json="{}",
                pinecone_api_key="test-key",
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
            s3_access_key_id="test-access",
            s3_secret_access_key="test-secret",
        )


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
        mongodb_uri="mongodb://localhost:27017",
        firebase_project_id="ajg-sop-web",
        firebase_service_account_json="{}",
        pinecone_api_key="test-key",
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
