from fastapi import APIRouter, HTTPException, Request

from apps.api.app.auth.dependencies import CurrentProfile
from packages.contracts.common import Language, utc_now

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("/me")
async def get_profile(profile: CurrentProfile) -> dict[str, object]:
    return profile.model_dump(mode="json")


@router.put("/language")
async def update_language(
    request: Request, language: Language, profile: CurrentProfile
) -> dict[str, str]:
    changed = await request.app.state.database.update_one(
        "employee_profiles",
        profile.organization_id,
        {
            "id": profile.id,
            # The first save initializes legacy profiles without weakening later CAS checks.
            "version": {"$in": [1, None]} if profile.version == 1 else profile.version,
        },
        {
            "preferred_language": language.value,
            "version": profile.version + 1,
            "updated_at": utc_now().isoformat(),
        },
    )
    if not changed:
        raise HTTPException(
            status_code=409,
            detail="Your profile changed. Reload before saving the language preference",
        )
    profile.preferred_language = language
    profile.version += 1
    return {"preferred_language": language.value}
