import pytest
from firebase_admin import auth

from apps.api.app.auth.identity import FirebaseIdentityProvider


@pytest.mark.asyncio
async def test_firebase_identity_uses_verified_uid_and_revocation_check(monkeypatch) -> None:
    provider = FirebaseIdentityProvider.__new__(FirebaseIdentityProvider)
    provider._app = object()
    observed: dict[str, object] = {}

    def verify(token: str, *, app: object, check_revoked: bool) -> dict[str, str]:
        observed.update(token=token, app=app, check_revoked=check_revoked)
        return {"uid": "firebase-user-123", "email": "employee@example.test"}

    monkeypatch.setattr(auth, "verify_id_token", verify)

    identity = await provider.authenticate("Bearer signed-id-token")

    assert identity.subject == "firebase-user-123"
    assert identity.claims["email"] == "employee@example.test"
    assert observed == {
        "token": "signed-id-token",
        "app": provider._app,
        "check_revoked": True,
    }


@pytest.mark.asyncio
async def test_firebase_identity_rejects_non_bearer_credentials() -> None:
    provider = FirebaseIdentityProvider.__new__(FirebaseIdentityProvider)
    provider._app = object()

    with pytest.raises(ValueError, match="Bearer credential required"):
        await provider.authenticate("Basic anything")
