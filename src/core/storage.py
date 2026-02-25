"""
Async Cloudflare R2 storage client (S3-compatible).

Uses aioboto3 for non-blocking uploads/downloads inside asyncio.gather().
"""

import asyncio
import os
import logging
from pathlib import Path
from typing import Optional

import aioboto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

_storage: Optional["R2Storage"] = None


class R2Storage:
    """Async wrapper around Cloudflare R2 (S3-compatible) using aioboto3."""

    def __init__(
        self,
        account_id: str,
        access_key_id: str,
        secret_access_key: str,
        bucket_name: str,
    ):
        self.bucket_name = bucket_name
        self.endpoint_url = f"https://{account_id}.r2.cloudflarestorage.com"
        self._session = aioboto3.Session()
        self._access_key_id = access_key_id
        self._secret_access_key = secret_access_key

    def _client(self):
        """Return an async context-manager S3 client."""
        return self._session.client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self._access_key_id,
            aws_secret_access_key=self._secret_access_key,
            config=BotoConfig(signature_version="s3v4"),
        )

    async def upload_bytes(
        self, data: bytes, key: str, content_type: str = "application/octet-stream"
    ) -> None:
        """Upload raw bytes to R2."""
        async with self._client() as client:
            await client.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=data,
                ContentType=content_type,
            )
        logger.debug(f"Uploaded {len(data)} bytes to {key}")

    async def upload_file(
        self, file_path: str, key: str, content_type: str = "application/octet-stream"
    ) -> int:
        """Read a local file and upload to R2. Returns file size in bytes."""
        data = await asyncio.to_thread(Path(file_path).read_bytes)
        await self.upload_bytes(data, key, content_type)
        return len(data)

    async def download_bytes(self, key: str) -> Optional[bytes]:
        """Download object as bytes. Returns None if the key does not exist."""
        try:
            async with self._client() as client:
                resp = await client.get_object(Bucket=self.bucket_name, Key=key)
                data = await resp["Body"].read()
                return data
        except ClientError as e:
            if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
                return None
            raise

    async def delete(self, key: str) -> None:
        """Delete a single object. No error if missing."""
        async with self._client() as client:
            await client.delete_object(Bucket=self.bucket_name, Key=key)

    async def delete_prefix(self, prefix: str) -> int:
        """Delete all objects under a prefix. Returns count of deleted objects."""
        deleted = 0
        async with self._client() as client:
            paginator = client.get_paginator("list_objects_v2")
            async for page in paginator.paginate(
                Bucket=self.bucket_name, Prefix=prefix
            ):
                contents = page.get("Contents", [])
                if not contents:
                    continue
                objects = [{"Key": obj["Key"]} for obj in contents]
                await client.delete_objects(
                    Bucket=self.bucket_name, Delete={"Objects": objects}
                )
                deleted += len(objects)
        logger.debug(f"Deleted {deleted} objects under prefix {prefix}")
        return deleted

    async def generate_presigned_url(
        self,
        key: str,
        expiration: int = 3600,
        response_filename: Optional[str] = None,
    ) -> str:
        """Generate a presigned GET URL for downloading an object."""
        params = {"Bucket": self.bucket_name, "Key": key}
        if response_filename:
            params["ResponseContentDisposition"] = (
                f'attachment; filename="{response_filename}"'
            )
        async with self._client() as client:
            url = await client.generate_presigned_url(
                "get_object", Params=params, ExpiresIn=expiration
            )
        return url


def is_r2_configured() -> bool:
    """Check whether all R2 env vars are set (sync, no I/O)."""
    return all(
        os.getenv(var)
        for var in (
            "R2_ACCOUNT_ID",
            "R2_ACCESS_KEY_ID",
            "R2_SECRET_ACCESS_KEY",
            "R2_BUCKET_NAME",
        )
    )


def get_storage() -> R2Storage:
    """Return module-level R2Storage singleton. Raises if not configured."""
    global _storage
    if _storage is not None:
        return _storage

    account_id = os.getenv("R2_ACCOUNT_ID", "")
    access_key_id = os.getenv("R2_ACCESS_KEY_ID", "")
    secret_access_key = os.getenv("R2_SECRET_ACCESS_KEY", "")
    bucket_name = os.getenv("R2_BUCKET_NAME", "")

    if not all([account_id, access_key_id, secret_access_key, bucket_name]):
        raise RuntimeError(
            "R2 storage not configured. Set R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, "
            "R2_SECRET_ACCESS_KEY, and R2_BUCKET_NAME environment variables."
        )

    _storage = R2Storage(
        account_id=account_id,
        access_key_id=access_key_id,
        secret_access_key=secret_access_key,
        bucket_name=bucket_name,
    )
    return _storage
