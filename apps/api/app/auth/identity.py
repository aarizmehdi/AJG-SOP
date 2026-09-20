from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import jwt
from jwt import PyJWKClient

from apps.api.app.config import Settings
from apps.api.app.models.organization import ApplicationRole, EmployeeProfile
from packages.contracts.common import Language


@dataclass(frozen=True)
class AuthenticatedIdentity:
    subject: str
    claims: dict[str, Any]

    @property
    def external_organization_id(self) -> str | None:
        value = self.claims.get("org_id")
        return str(value) if value else None


class IdentityProvider(ABC):
    @abstractmethod
    async def authenticate(self, credential: str) -> AuthenticatedIdentity:
        raise NotImplementedError


class Auth0IdentityProvider(IdentityProvider):
    """Validates Auth0 access tokens; browser OAuth is handled by Auth0's supported React SDK."""

    def __init__(self, settings: Settings) -> None:
        if not settings.auth0_domain or not settings.auth0_audience:
            raise ValueError("Auth0 domain and audience are required")
        domain = settings.auth0_domain.strip().rstrip("/")
        self._issuer = f"https://{domain}/"
        self._audience = settings.auth0_audience
        self._jwks = PyJWKClient(
            f"{self._issuer}.well-known/jwks.json",
            cache_keys=True,
            cache_jwk_set=True,
            lifespan=3600,
        )

    async def authenticate(self, credential: str) -> AuthenticatedIdentity:
        token = credential.removeprefix("Bearer ").strip()
        try:
            key = self._jwks.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                key.key,
                algorithms=["RS256"],
                audience=self._audience,
                issuer=self._issuer,
                options={"verify_exp": True, "verify_iss": True, "verify_aud": True},
            )
            return AuthenticatedIdentity(subject=str(claims["sub"]), claims=claims)
        except Exception as err:
            raise ValueError(f"Invalid JWT credential: {err}") from err


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
