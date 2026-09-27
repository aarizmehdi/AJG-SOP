from datetime import datetime
from enum import StrEnum

from pydantic import Field, model_validator

from packages.contracts.common import Language, OrganizationOwned, utc_now


class ApplicationRole(StrEnum):
    EMPLOYEE = "employee"
    SOP_ADMIN = "sop_admin"
    SYSTEM_ADMIN = "system_admin"


class MembershipStatus(StrEnum):
    PENDING_ACTIVATION = "pending_activation"
    ACTIVE = "active"
    DISABLED = "disabled"


class CatalogKind(StrEnum):
    DEPARTMENT = "departments"
    LOCATION = "locations"
    ORGANIZATIONAL_ROLE = "organizational_roles"


class OrganizationCatalogItem(OrganizationOwned):
    id: str
    key: str = Field(pattern=r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$")
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    active: bool = True
    version: int = Field(default=1, ge=1)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class Organization(OrganizationOwned):
    name: str
    slug: str
    created_at: datetime = Field(default_factory=utc_now)


class EmployeeProfile(OrganizationOwned):
    id: str
    identity_subject: str
    display_name: str
    email: str
    application_roles: frozenset[ApplicationRole]
    departments: frozenset[str] = Field(default_factory=frozenset)
    locations: frozenset[str] = Field(default_factory=frozenset)
    organizational_roles: frozenset[str] = Field(default_factory=frozenset)
    management_departments: frozenset[str] = Field(default_factory=frozenset)
    management_locations: frozenset[str] = Field(default_factory=frozenset)
    management_roles: frozenset[str] = Field(default_factory=frozenset)
    preferred_language: Language | None = None
    active: bool = True
    status: MembershipStatus = MembershipStatus.ACTIVE
    version: int = Field(default=1, ge=1)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="before")
    @classmethod
    def infer_legacy_status(cls, value: object) -> object:
        if isinstance(value, dict) and "status" not in value:
            value = {
                **value,
                "status": (
                    MembershipStatus.ACTIVE
                    if value.get("active", True)
                    else MembershipStatus.DISABLED
                ),
            }
        return value
