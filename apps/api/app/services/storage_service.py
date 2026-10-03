import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import partial
from pathlib import Path

import anyio
import boto3


@dataclass(frozen=True)
class SourceObject:
    key: str
    size: int


def source_prefix(organization_id: str, source_id: str) -> str:
    if not all(re.fullmatch(r"[A-Za-z0-9_-]+", value) for value in (organization_id, source_id)):
        raise ValueError("Invalid organization/source identifier")
    return f"{organization_id}/sources/{source_id}/"


class ArtifactStore(ABC):
    @abstractmethod
    def owns_source_uri(self, organization_id: str, source_id: str, uri: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def list_source(self, organization_id: str, source_id: str) -> list[SourceObject]:
        """List the entire exact source prefix, including unreferenced legacy objects."""
        raise NotImplementedError

    @abstractmethod
    async def delete_source(self, organization_id: str, source_id: str) -> list[SourceObject]:
        """Return deleted objects; never delete outside this organization/source prefix."""
        raise NotImplementedError

    @abstractmethod
    async def put(
        self, organization_id: str, key: str, content: bytes, media_type: str | None = None
    ) -> str:
        raise NotImplementedError

    @abstractmethod
    async def get(self, organization_id: str, uri: str) -> bytes:
        raise NotImplementedError

    async def signature(self, organization_id: str, uri: str) -> bytes:
        """Read only the first bytes to identify a source without buffering it."""
        return (await self.get(organization_id, uri))[:32]

    def presigned_get(self, organization_id: str, uri: str, *, media_type: str) -> str | None:
        return None


MAX_FILE_SIZE_BYTES = 200 * 1024 * 1024  # 200 MB limit per user requirement


class StorageError(RuntimeError):
    pass


class LocalArtifactStore(ArtifactStore):
    def owns_source_uri(self, organization_id: str, source_id: str, uri: str) -> bool:
        return uri.startswith(f"local://{source_prefix(organization_id, source_id)}")

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    async def list_source(self, organization_id: str, source_id: str) -> list[SourceObject]:
        prefix = source_prefix(organization_id, source_id)
        path = self._root / prefix

        def scan() -> list[SourceObject]:
            if not path.exists():
                return []
            if path.resolve() != path.absolute() or path.is_symlink():
                raise ValueError("Source prefix must not traverse symbolic links")
            result = []
            for child in path.rglob("*"):
                if child.is_symlink() or not child.resolve().is_relative_to(path.resolve()):
                    raise ValueError("Source artifact escapes exact source prefix")
                if child.is_file():
                    result.append(
                        SourceObject(child.relative_to(self._root).as_posix(), child.stat().st_size)
                    )
            return sorted(result, key=lambda item: item.key)

        return await anyio.to_thread.run_sync(scan)

    async def delete_source(self, organization_id: str, source_id: str) -> list[SourceObject]:
        objects = await self.list_source(organization_id, source_id)
        prefix = (self._root / source_prefix(organization_id, source_id)).resolve()
        for item in objects:
            path = (self._root / item.key).resolve()
            if not path.is_relative_to(prefix):
                raise ValueError("Deletion target escapes exact source prefix")
            await anyio.to_thread.run_sync(partial(path.unlink, missing_ok=True))
        return objects

    def _path(self, organization_id: str, key: str) -> Path:
        candidate = (self._root / organization_id / key).resolve()
        if self._root not in candidate.parents:
            raise ValueError("Invalid artifact key")
        return candidate

    async def put(
        self, organization_id: str, key: str, content: bytes, media_type: str | None = None
    ) -> str:
        if len(content) > MAX_FILE_SIZE_BYTES:
            mb = len(content) / (1024 * 1024)
            limit_mb = MAX_FILE_SIZE_BYTES // (1024 * 1024)
            raise ValueError(f"File size {mb:.1f}MB exceeds maximum allowed limit of {limit_mb}MB")
        path = self._path(organization_id, key)
        await anyio.to_thread.run_sync(lambda: path.parent.mkdir(parents=True, exist_ok=True))
        await anyio.to_thread.run_sync(path.write_bytes, content)
        return f"local://{organization_id}/{key}"

    async def get(self, organization_id: str, uri: str) -> bytes:
        prefix = f"local://{organization_id}/"
        if not uri.startswith(prefix):
            raise PermissionError("Artifact does not belong to the active organization")
        path = self._path(organization_id, uri[len(prefix) :])
        if not path.exists():
            raise StorageError(f"Artifact not found at {path}")
        return await anyio.to_thread.run_sync(path.read_bytes)

    def local_path(self, organization_id: str, uri: str) -> Path:
        prefix = f"local://{organization_id}/"
        if not uri.startswith(prefix):
            raise PermissionError("Artifact does not belong to the active organization")
        return self._path(organization_id, uri[len(prefix) :])

    async def signature(self, organization_id: str, uri: str) -> bytes:
        path = self.local_path(organization_id, uri)
        if not path.is_file():
            raise StorageError("Artifact not found")

        def read() -> bytes:
            with path.open("rb") as stream:
                return stream.read(32)

        return await anyio.to_thread.run_sync(read)


class S3ArtifactStore(ArtifactStore):
    def owns_source_uri(self, organization_id: str, source_id: str, uri: str) -> bool:
        return uri.startswith(f"s3://{self._bucket}/{source_prefix(organization_id, source_id)}")

    async def list_source(self, organization_id: str, source_id: str) -> list[SourceObject]:
        prefix = source_prefix(organization_id, source_id)

        def scan() -> list[SourceObject]:
            result = []
            for page in self._client.get_paginator("list_objects_v2").paginate(
                Bucket=self._bucket, Prefix=prefix
            ):
                for item in page.get("Contents", []):
                    key = item["Key"]
                    if not key.startswith(prefix):
                        raise StorageError("Object listing escaped exact source prefix")
                    result.append(SourceObject(key, item["Size"]))
            return sorted(result, key=lambda item: item.key)

        return await anyio.to_thread.run_sync(scan)

    async def delete_source(self, organization_id: str, source_id: str) -> list[SourceObject]:
        objects = await self.list_source(organization_id, source_id)
        for start in range(0, len(objects), 1000):
            batch = objects[start : start + 1000]
            response = await anyio.to_thread.run_sync(
                partial(
                    self._client.delete_objects,
                    Bucket=self._bucket,
                    Delete={"Objects": [{"Key": item.key} for item in batch]},
                )
            )
            if response.get("Errors"):
                raise StorageError("Some exact source objects could not be deleted; retry purge")
        if await self.list_source(organization_id, source_id):
            raise StorageError("Source prefix deletion could not be verified")
        return objects

    def __init__(
        self,
        bucket: str,
        region: str,
        endpoint_url: str | None,
        access_key: str,
        secret_key: str,
    ) -> None:
        self._bucket = bucket
        self._client = boto3.client(
            "s3",
            region_name=region,
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )

    async def put(
        self, organization_id: str, key: str, content: bytes, media_type: str | None = None
    ) -> str:
        if len(content) > MAX_FILE_SIZE_BYTES:
            mb = len(content) / (1024 * 1024)
            limit_mb = MAX_FILE_SIZE_BYTES // (1024 * 1024)
            raise ValueError(f"File size {mb:.1f}MB exceeds maximum allowed limit of {limit_mb}MB")
        object_key = f"{organization_id}/{key}"
        try:
            if media_type:
                await anyio.to_thread.run_sync(
                    lambda: self._client.put_object(
                        Bucket=self._bucket,
                        Key=object_key,
                        Body=content,
                        ContentType=media_type,
                    )
                )
            else:
                await anyio.to_thread.run_sync(
                    lambda: self._client.put_object(
                        Bucket=self._bucket,
                        Key=object_key,
                        Body=content,
                    )
                )
        except Exception as err:
            raise StorageError(f"Failed to store artifact in S3/R2: {err}") from err
        return f"s3://{self._bucket}/{object_key}"

    async def get(self, organization_id: str, uri: str) -> bytes:
        prefix = f"s3://{self._bucket}/{organization_id}/"
        if not uri.startswith(prefix):
            raise PermissionError("Artifact does not belong to the active organization")
        object_key = f"{organization_id}/{uri[len(prefix) :]}"
        try:
            response = await anyio.to_thread.run_sync(
                lambda: self._client.get_object(Bucket=self._bucket, Key=object_key)
            )
            return await anyio.to_thread.run_sync(response["Body"].read)
        except Exception as err:
            raise StorageError(f"Failed to retrieve artifact from S3/R2: {err}") from err

    def _object_key(self, organization_id: str, uri: str) -> str:
        prefix = f"s3://{self._bucket}/{organization_id}/"
        if not uri.startswith(prefix):
            raise PermissionError("Artifact does not belong to the active organization")
        return f"{organization_id}/{uri[len(prefix) :]}"

    async def signature(self, organization_id: str, uri: str) -> bytes:
        key = self._object_key(organization_id, uri)
        try:
            response = await anyio.to_thread.run_sync(
                lambda: self._client.get_object(Bucket=self._bucket, Key=key, Range="bytes=0-31")
            )

            def read() -> bytes:
                try:
                    return response["Body"].read(32)
                finally:
                    response["Body"].close()

            return await anyio.to_thread.run_sync(read)
        except Exception as err:
            raise StorageError("Failed to inspect private source artifact") from err

    def presigned_get(self, organization_id: str, uri: str, *, media_type: str) -> str:
        key = self._object_key(organization_id, uri)
        return str(
            self._client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": self._bucket,
                    "Key": key,
                    "ResponseContentType": media_type,
                    "ResponseContentDisposition": "inline",
                },
                ExpiresIn=120,
            )
        )
