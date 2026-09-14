from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from packages.contracts.common import OrganizationOwned


class AccessMode(StrEnum):
    ALL = "all"
    SELECTED = "selected"


class AccessDimension(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: AccessMode
    values: frozenset[str] = Field(default_factory=frozenset)

    @model_validator(mode="after")
    def validate_explicit_scope(self) -> "AccessDimension":
        if self.mode is AccessMode.SELECTED and not self.values:
            raise ValueError("Selected access requires at least one value")
        if self.mode is AccessMode.ALL and self.values:
            raise ValueError("All access must not carry selected values")
        return self

    def allows(self, employee_values: frozenset[str]) -> bool:
        return self.mode is AccessMode.ALL or bool(self.values & employee_values)


class AccessScope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    departments: AccessDimension
    locations: AccessDimension
    roles: AccessDimension

    def allows(self, employee: "EmployeeScope") -> bool:
        return (
            self.departments.allows(employee.departments)
            and self.locations.allows(employee.locations)
            and self.roles.allows(employee.organizational_roles)
        )


class EmployeeScope(OrganizationOwned):
    departments: frozenset[str] = Field(default_factory=frozenset)
    locations: frozenset[str] = Field(default_factory=frozenset)
    organizational_roles: frozenset[str] = Field(default_factory=frozenset)


UNRESTRICTED_SCOPE = AccessScope(
    departments=AccessDimension(mode=AccessMode.ALL),
    locations=AccessDimension(mode=AccessMode.ALL),
    roles=AccessDimension(mode=AccessMode.ALL),
)
