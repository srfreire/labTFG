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

    # -- lifecycle -------------------------------------------------------------

    async def connect(self) -> None:
        """Create the aioboto3 session and ensure the bucket exists."""
        self._session = aioboto3.Session()
        async with self._client() as client:
            try:
                await client.head_bucket(Bucket=self._settings.MINIO_BUCKET)
            except ClientError:
                await client.create_bucket(Bucket=self._settings.MINIO_BUCKET)

    async def close(self) -> None:
        """Clean up resources."""
        self._session = None

    # -- helpers ---------------------------------------------------------------

    def _client(self):
        """Return an async-context-manager S3 client."""
        if self._session is None:
            raise RuntimeError("StorageService not connected — call connect() first")
        return self._session.client(
            "s3",
            endpoint_url=f"http://{self._settings.MINIO_ENDPOINT}",
            aws_access_key_id=self._settings.MINIO_ACCESS_KEY,
            aws_secret_access_key=self._settings.MINIO_SECRET_KEY,
        )

    # -- public API ------------------------------------------------------------

    async def put(
        self,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Upload raw bytes and return the key."""
        async with self._client() as client:
            await client.put_object(
                Bucket=self._settings.MINIO_BUCKET,
                Key=key,
                Body=data,
                ContentType=content_type,
            )
        return key

    async def get(self, key: str) -> bytes:
        """Download an object as raw bytes."""
        async with self._client() as client:
            resp = await client.get_object(
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
        async with self._client() as client:
            resp = await client.list_objects_v2(
                Bucket=self._settings.MINIO_BUCKET,
                Prefix=prefix,
            )
            return [obj["Key"] for obj in resp.get("Contents", [])]

    async def delete(self, key: str) -> None:
        """Delete an object by key."""
        async with self._client() as client:
            await client.delete_object(
                Bucket=self._settings.MINIO_BUCKET,
                Key=key,
            )

    async def exists(self, key: str) -> bool:
        """Return True if *key* exists in the bucket."""
        async with self._client() as client:
            try:
                await client.head_object(
                    Bucket=self._settings.MINIO_BUCKET,
                    Key=key,
                )
                return True
            except ClientError as exc:
                if exc.response["Error"]["Code"] == "404":
                    return False
                raise
