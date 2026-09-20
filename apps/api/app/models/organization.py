from datetime import datetime
from enum import StrEnum

from pydantic import Field

from packages.contracts.common import Language, OrganizationOwned, utc_now


class ApplicationRole(StrEnum):
    EMPLOYEE = "employee"
    SOP_ADMIN = "sop_admin"
    SYSTEM_ADMIN = "system_admin"


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
