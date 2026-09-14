from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(UTC)


class Language(StrEnum):
    ENGLISH = "english"
    URDU = "urdu"
    ROMAN_URDU = "roman_urdu"


class OrganizationOwned(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization_id: str = Field(min_length=1)
