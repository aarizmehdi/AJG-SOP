from fastapi import APIRouter

from apps.api.app.auth.dependencies import CurrentProfile
from packages.contracts.common import Language

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("/me")
async def get_profile(profile: CurrentProfile) -> dict[str, object]:
    return profile.model_dump(mode="json")


@router.put("/language")
async def update_language(language: Language, profile: CurrentProfile) -> dict[str, str]:
    # Fixture mode is ephemeral; live persistence is wired through the profile service.
    profile.preferred_language = language
    return {"preferred_language": language.value}
