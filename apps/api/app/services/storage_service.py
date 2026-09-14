from abc import ABC, abstractmethod
from pathlib import Path

import anyio
import boto3


class ArtifactStore(ABC):
    @abstractmethod
    async def put(self, organization_id: str, key: str, content: bytes) -> str:
        raise NotImplementedError

    @abstractmethod
    async def get(self, organization_id: str, uri: str) -> bytes:
        raise NotImplementedError


class LocalArtifactStore(ArtifactStore):
    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    def _path(self, organization_id: str, key: str) -> Path:
        candidate = (self._root / organization_id / key).resolve()
        if self._root not in candidate.parents:
            raise ValueError("Invalid artifact key")
        return candidate

    async def put(self, organization_id: str, key: str, content: bytes) -> str:
        path = self._path(organization_id, key)
        await anyio.to_thread.run_sync(lambda: path.parent.mkdir(parents=True, exist_ok=True))
        await anyio.to_thread.run_sync(path.write_bytes, content)
        return f"local://{organization_id}/{key}"

    async def get(self, organization_id: str, uri: str) -> bytes:
        prefix = f"local://{organization_id}/"
        if not uri.startswith(prefix):
            raise PermissionError("Artifact does not belong to the active organization")
        path = self._path(organization_id, uri[len(prefix) :])
        return await anyio.to_thread.run_sync(path.read_bytes)


class S3ArtifactStore(ArtifactStore):
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

    async def put(self, organization_id: str, key: str, content: bytes) -> str:
        object_key = f"{organization_id}/{key}"
        await anyio.to_thread.run_sync(
            lambda: self._client.put_object(Bucket=self._bucket, Key=object_key, Body=content)
        )
        return f"s3://{self._bucket}/{object_key}"

    async def get(self, organization_id: str, uri: str) -> bytes:
        prefix = f"s3://{self._bucket}/{organization_id}/"
        if not uri.startswith(prefix):
            raise PermissionError("Artifact does not belong to the active organization")
        object_key = f"{organization_id}/{uri[len(prefix) :]}"
        response = await anyio.to_thread.run_sync(
            lambda: self._client.get_object(Bucket=self._bucket, Key=object_key)
        )
        return await anyio.to_thread.run_sync(response["Body"].read)
