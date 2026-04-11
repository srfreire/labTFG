"""Async S3 client wrapping aioboto3 for MinIO object storage."""
from __future__ import annotations

import aioboto3
from botocore.exceptions import ClientError

from shared.settings import Settings


class StorageService:
    """Thin async wrapper around an S3-compatible object store (MinIO)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._session: aioboto3.Session | None = None
        self._client_ctx = None
        self._client = None

    # -- lifecycle -------------------------------------------------------------

    async def connect(self) -> None:
        """Create an aioboto3 session, open a persistent client, and ensure the bucket exists."""
        self._session = aioboto3.Session()
        self._client_ctx = self._session.client(
            "s3",
            endpoint_url=f"http://{self._settings.MINIO_ENDPOINT}",
            aws_access_key_id=self._settings.MINIO_ACCESS_KEY,
            aws_secret_access_key=self._settings.MINIO_SECRET_KEY,
        )
        self._client = await self._client_ctx.__aenter__()
        try:
            await self._client.head_bucket(Bucket=self._settings.MINIO_BUCKET)
        except ClientError:
            await self._client.create_bucket(Bucket=self._settings.MINIO_BUCKET)

    async def close(self) -> None:
        """Clean up the persistent client and session."""
        if self._client_ctx is not None:
            await self._client_ctx.__aexit__(None, None, None)
            self._client_ctx = None
            self._client = None
        self._session = None

    def _c(self):
        if self._client is None:
            raise RuntimeError("StorageService not connected — call connect() first")
        return self._client

    # -- public API ------------------------------------------------------------

    async def put(
        self,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Upload raw bytes and return the key."""
        await self._c().put_object(
            Bucket=self._settings.MINIO_BUCKET,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
        return key

    async def get(self, key: str) -> bytes:
        """Download an object as raw bytes."""
        resp = await self._c().get_object(
            Bucket=self._settings.MINIO_BUCKET,
            Key=key,
        )
        return await resp["Body"].read()

    async def put_text(
        self,
        key: str,
        text: str,
        content_type: str = "text/plain",
    ) -> str:
        """Upload a UTF-8 text object and return the key."""
        return await self.put(key, text.encode("utf-8"), content_type)

    async def get_text(self, key: str) -> str:
        """Download an object and decode as UTF-8 text."""
        data = await self.get(key)
        return data.decode("utf-8")

    async def list(self, prefix: str) -> list[str]:
        """List object keys matching *prefix*."""
        resp = await self._c().list_objects_v2(
            Bucket=self._settings.MINIO_BUCKET,
            Prefix=prefix,
        )
        return [obj["Key"] for obj in resp.get("Contents", [])]

    async def delete(self, key: str) -> None:
        """Delete an object by key."""
        await self._c().delete_object(
            Bucket=self._settings.MINIO_BUCKET,
            Key=key,
        )

    async def exists(self, key: str) -> bool:
        """Return True if *key* exists in the bucket."""
        try:
            await self._c().head_object(
                Bucket=self._settings.MINIO_BUCKET,
                Key=key,
            )
            return True
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "404":
                return False
            raise
