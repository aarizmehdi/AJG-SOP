import secrets
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import anyio
import firebase_admin  # type: ignore[import-untyped]
from firebase_admin import auth

from apps.api.app.auth.identity import FixtureIdentityDirectory


class IdentityAdminError(ValueError):
    pass


class IdentityConflictError(IdentityAdminError):
    pass


@dataclass(frozen=True)
class ManagedIdentity:
    uid: str
    email: str
    display_name: str
    disabled: bool


class IdentityAdminService(ABC):
    @abstractmethod
    async def create_identity(self, email: str, display_name: str) -> ManagedIdentity: ...

    @abstractmethod
    async def disable_identity(self, uid: str) -> ManagedIdentity: ...

    @abstractmethod
    async def enable_identity(self, uid: str) -> ManagedIdentity: ...

    @abstractmethod
    async def delete_identity(self, uid: str) -> None: ...

    @abstractmethod
    async def generate_password_reset_link(self, email: str) -> str: ...

    @abstractmethod
    async def update_identity(
        self, uid: str, *, email: str | None = None, display_name: str | None = None
    ) -> ManagedIdentity: ...

    @abstractmethod
    async def get_identity(self, uid: str) -> ManagedIdentity | None: ...


class FirebaseAdminIdentityService(IdentityAdminService):
    """Firebase Admin operations kept behind a backend-only provider boundary."""

    def __init__(self, app: firebase_admin.App) -> None:
        self._app = app

    @staticmethod
    def _managed(user: auth.UserRecord) -> ManagedIdentity:
        return ManagedIdentity(
            uid=user.uid,
            email=user.email or "",
            display_name=user.display_name or "",
            disabled=user.disabled,
        )

    async def create_identity(self, email: str, display_name: str) -> ManagedIdentity:
        temporary_secret = secrets.token_urlsafe(36)
        try:
            user = await anyio.to_thread.run_sync(
                lambda: auth.create_user(
                    email=email,
                    display_name=display_name,
                    password=temporary_secret,
                    disabled=False,
                    app=self._app,
                )
            )
            return self._managed(user)
        except auth.EmailAlreadyExistsError as error:
            raise IdentityConflictError(
                "An account already exists for this email address"
            ) from error
        except Exception as error:
            raise IdentityAdminError("Firebase identity operation failed") from error

    async def _set_disabled(self, uid: str, disabled: bool) -> ManagedIdentity:
        try:
            user = await anyio.to_thread.run_sync(
                lambda: auth.update_user(uid, disabled=disabled, app=self._app)
            )
            if disabled:
                await anyio.to_thread.run_sync(
                    lambda: auth.revoke_refresh_tokens(uid, app=self._app)
                )
            return self._managed(user)
        except Exception as error:
            raise IdentityAdminError("Firebase identity operation failed") from error

    async def disable_identity(self, uid: str) -> ManagedIdentity:
        return await self._set_disabled(uid, True)

    async def enable_identity(self, uid: str) -> ManagedIdentity:
        return await self._set_disabled(uid, False)

    async def delete_identity(self, uid: str) -> None:
        try:
            await anyio.to_thread.run_sync(lambda: auth.delete_user(uid, app=self._app))
        except Exception as error:
            raise IdentityAdminError("Firebase identity compensation failed") from error

    async def generate_password_reset_link(self, email: str) -> str:
        try:
            return await anyio.to_thread.run_sync(
                lambda: auth.generate_password_reset_link(email, app=self._app)
            )
        except Exception as error:
            raise IdentityAdminError("Password reset could not be initiated") from error

    async def update_identity(
        self, uid: str, *, email: str | None = None, display_name: str | None = None
    ) -> ManagedIdentity:
        values: dict[str, Any] = {"app": self._app}
        if email is not None:
            values["email"] = email
        if display_name is not None:
            values["display_name"] = display_name
        try:
            user = await anyio.to_thread.run_sync(lambda: auth.update_user(uid, **values))
            return self._managed(user)
        except auth.EmailAlreadyExistsError as error:
            raise IdentityConflictError(
                "An account already exists for this email address"
            ) from error
        except Exception as error:
            raise IdentityAdminError("Firebase identity operation failed") from error

    async def get_identity(self, uid: str) -> ManagedIdentity | None:
        try:
            user = await anyio.to_thread.run_sync(lambda: auth.get_user(uid, app=self._app))
            return self._managed(user)
        except auth.UserNotFoundError:
            return None
        except Exception as error:
            raise IdentityAdminError("Firebase identity lookup failed") from error


class FixtureIdentityAdminService(IdentityAdminService):
    def __init__(self, directory: FixtureIdentityDirectory) -> None:
        self._directory = directory

    def _get(self, uid: str) -> dict[str, Any]:
        identity = self._directory.identities.get(uid)
        if not identity:
            raise IdentityAdminError("Identity was not found")
        return identity

    @staticmethod
    def _managed(identity: dict[str, Any]) -> ManagedIdentity:
        return ManagedIdentity(
            uid=str(identity["uid"]),
            email=str(identity["email"]),
            display_name=str(identity["display_name"]),
            disabled=bool(identity["disabled"]),
        )

    async def create_identity(self, email: str, display_name: str) -> ManagedIdentity:
        if any(
            str(item["email"]).casefold() == email.casefold()
            for item in self._directory.identities.values()
        ):
            raise IdentityConflictError("An account already exists for this email address")
        uid = f"fixture|managed-{uuid4().hex[:12]}"
        identity = {
            "uid": uid,
            "email": email,
            "display_name": display_name,
            "disabled": False,
        }
        self._directory.identities[uid] = identity
        return self._managed(identity)

    async def disable_identity(self, uid: str) -> ManagedIdentity:
        identity = self._get(uid)
        identity["disabled"] = True
        return self._managed(identity)

    async def enable_identity(self, uid: str) -> ManagedIdentity:
        identity = self._get(uid)
        identity["disabled"] = False
        return self._managed(identity)

    async def delete_identity(self, uid: str) -> None:
        self._directory.identities.pop(uid, None)

    async def generate_password_reset_link(self, email: str) -> str:
        if not any(
            str(item["email"]).casefold() == email.casefold()
            for item in self._directory.identities.values()
        ):
            raise IdentityAdminError("Identity was not found")
        return f"https://fixture.invalid/reset/{uuid4().hex}"

    async def update_identity(
        self, uid: str, *, email: str | None = None, display_name: str | None = None
    ) -> ManagedIdentity:
        identity = self._get(uid)
        if email is not None:
            identity["email"] = email
        if display_name is not None:
            identity["display_name"] = display_name
        return self._managed(identity)

    async def get_identity(self, uid: str) -> ManagedIdentity | None:
        identity = self._directory.identities.get(uid)
        return self._managed(identity) if identity else None
