import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import anyio
import firebase_admin  # type: ignore[import-untyped]
from firebase_admin import auth, credentials

from apps.api.app.config import Settings
from apps.api.app.models.organization import ApplicationRole, EmployeeProfile
from packages.contracts.common import Language


@dataclass(frozen=True)
class AuthenticatedIdentity:
    subject: str
    claims: dict[str, Any]


class IdentityProvider(ABC):
    @abstractmethod
    async def authenticate(self, credential: str) -> AuthenticatedIdentity:
        raise NotImplementedError


class FirebaseIdentityProvider(IdentityProvider):
    """Verify Firebase ID tokens and expose only the authenticated Firebase UID."""

    def __init__(self, settings: Settings) -> None:
        if not settings.firebase_project_id or not settings.firebase_service_account_json:
            raise ValueError("Firebase project ID and service account JSON are required")
        try:
            service_account = json.loads(settings.firebase_service_account_json.get_secret_value())
        except (TypeError, json.JSONDecodeError) as err:
            raise ValueError("FIREBASE_SERVICE_ACCOUNT_JSON must be valid JSON") from err
        if service_account.get("project_id") != settings.firebase_project_id:
            raise ValueError("Firebase service account project does not match FIREBASE_PROJECT_ID")
        try:
            self._app = firebase_admin.get_app("ajt-sop-api")
        except ValueError:
            self._app = firebase_admin.initialize_app(
                credentials.Certificate(service_account),
                {"projectId": settings.firebase_project_id},
                name="ajt-sop-api",
            )

    async def authenticate(self, credential: str) -> AuthenticatedIdentity:
        scheme, separator, token = credential.partition(" ")
        if not separator or scheme.lower() != "bearer" or not token.strip():
            raise ValueError("Bearer credential required")
        try:
            claims = await anyio.to_thread.run_sync(
                lambda: auth.verify_id_token(token.strip(), app=self._app, check_revoked=True)
            )
            uid = claims.get("uid") or claims.get("sub")
            if not uid:
                raise ValueError("Firebase token does not contain a UID")
            return AuthenticatedIdentity(subject=str(uid), claims=dict(claims))
        except Exception as err:
            raise ValueError("Invalid Firebase ID token") from err


class FixtureIdentityProvider(IdentityProvider):
    async def authenticate(self, credential: str) -> AuthenticatedIdentity:
        subject = credential.removeprefix("Fixture ").strip()
        if subject not in {"employee", "sop-admin", "system-admin"}:
            raise ValueError("Unknown fixture identity")
        return AuthenticatedIdentity(subject=f"fixture|{subject}", claims={"fixture": True})


FIXTURE_PROFILES = {
    "fixture|employee": EmployeeProfile(
        id="user-employee",
        organization_id="ajt",
        identity_subject="fixture|employee",
        display_name="Ayesha Khan",
        email="ayesha@example.test",
        application_roles=frozenset({ApplicationRole.EMPLOYEE}),
        departments=frozenset({"store"}),
        locations=frozenset({"peshawar-main"}),
        organizational_roles=frozenset({"store_keeper"}),
        preferred_language=Language.ENGLISH,
    ),
    "fixture|sop-admin": EmployeeProfile(
        id="user-sop-admin",
        organization_id="ajt",
        identity_subject="fixture|sop-admin",
        display_name="Hamza Shah",
        email="hamza@example.test",
        application_roles=frozenset({ApplicationRole.EMPLOYEE, ApplicationRole.SOP_ADMIN}),
        departments=frozenset({"operations"}),
        locations=frozenset({"head-office"}),
        organizational_roles=frozenset({"sop_owner"}),
        management_departments=frozenset({"store", "operations"}),
        management_locations=frozenset({"peshawar-main", "head-office"}),
        management_roles=frozenset({"store_keeper", "sop_owner"}),
        preferred_language=Language.ENGLISH,
    ),
    "fixture|system-admin": EmployeeProfile(
        id="user-system-admin",
        organization_id="ajt",
        identity_subject="fixture|system-admin",
        display_name="System Administrator",
        email="admin@example.test",
        application_roles=frozenset(
            {ApplicationRole.EMPLOYEE, ApplicationRole.SOP_ADMIN, ApplicationRole.SYSTEM_ADMIN}
        ),
        departments=frozenset({"technology"}),
        locations=frozenset({"head-office"}),
        organizational_roles=frozenset({"system_admin"}),
        management_departments=frozenset({"store", "operations", "technology"}),
        management_locations=frozenset({"peshawar-main", "head-office"}),
        management_roles=frozenset({"store_keeper", "sop_owner", "system_admin"}),
        preferred_language=Language.ENGLISH,
    ),
}
