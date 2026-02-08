"""Unit tests for src/core/storage.py — R2Storage client."""

import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from botocore.exceptions import ClientError

from src.core.storage import R2Storage, is_r2_configured, get_storage, _storage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_storage() -> R2Storage:
    return R2Storage(
        account_id="test-account",
        access_key_id="test-key",
        secret_access_key="test-secret",
        bucket_name="test-bucket",
    )


def _mock_client():
    """Return an AsyncMock that works as an async context manager."""
    client = AsyncMock()
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm, client


# ---------------------------------------------------------------------------
# R2Storage.__init__
# ---------------------------------------------------------------------------


class TestR2StorageInit:
    def test_sets_endpoint_url(self):
        s = _make_storage()
        assert s.endpoint_url == "https://test-account.r2.cloudflarestorage.com"

    def test_sets_bucket(self):
        s = _make_storage()
        assert s.bucket_name == "test-bucket"


# ---------------------------------------------------------------------------
# upload_bytes
# ---------------------------------------------------------------------------


class TestUploadBytes:
    async def test_calls_put_object(self):
        s = _make_storage()
        cm, client = _mock_client()
        with patch.object(s, "_client", return_value=cm):
            await s.upload_bytes(b"hello", "my/key", "text/plain")
            client.put_object.assert_awaited_once_with(
                Bucket="test-bucket",
                Key="my/key",
                Body=b"hello",
                ContentType="text/plain",
            )

    async def test_default_content_type(self):
        s = _make_storage()
        cm, client = _mock_client()
        with patch.object(s, "_client", return_value=cm):
            await s.upload_bytes(b"data", "key")
            call_kwargs = client.put_object.call_args.kwargs
            assert call_kwargs["ContentType"] == "application/octet-stream"


# ---------------------------------------------------------------------------
# upload_file
# ---------------------------------------------------------------------------


class TestUploadFile:
    async def test_reads_file_and_uploads(self, tmp_path):
        s = _make_storage()
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"pdf-bytes-here")

        cm, client = _mock_client()
        with patch.object(s, "_client", return_value=cm):
            size = await s.upload_file(str(test_file), "pdfs/test.pdf", "application/pdf")
            assert size == len(b"pdf-bytes-here")
            client.put_object.assert_awaited_once()

    async def test_returns_file_size(self, tmp_path):
        s = _make_storage()
        test_file = tmp_path / "data.bin"
        content = b"x" * 1024
        test_file.write_bytes(content)

        cm, client = _mock_client()
        with patch.object(s, "_client", return_value=cm):
            size = await s.upload_file(str(test_file), "key")
            assert size == 1024


# ---------------------------------------------------------------------------
# download_bytes
# ---------------------------------------------------------------------------


class TestDownloadBytes:
    async def test_returns_data(self):
        s = _make_storage()
        cm, client = _mock_client()

        body_mock = AsyncMock()
        body_mock.read = AsyncMock(return_value=b"image-data")
        client.get_object = AsyncMock(return_value={"Body": body_mock})

        with patch.object(s, "_client", return_value=cm):
            data = await s.download_bytes("images/test.png")
            assert data == b"image-data"

    async def test_returns_none_on_nosuchkey(self):
        s = _make_storage()
        cm, client = _mock_client()

        error_response = {"Error": {"Code": "NoSuchKey"}}
        client.get_object = AsyncMock(
            side_effect=ClientError(error_response, "GetObject")
        )

        with patch.object(s, "_client", return_value=cm):
            data = await s.download_bytes("missing/key")
            assert data is None

    async def test_returns_none_on_404(self):
        s = _make_storage()
        cm, client = _mock_client()

        error_response = {"Error": {"Code": "404"}}
        client.get_object = AsyncMock(
            side_effect=ClientError(error_response, "GetObject")
        )

        with patch.object(s, "_client", return_value=cm):
            data = await s.download_bytes("missing/key")
            assert data is None

    async def test_raises_on_other_errors(self):
        s = _make_storage()
        cm, client = _mock_client()

        error_response = {"Error": {"Code": "AccessDenied"}}
        client.get_object = AsyncMock(
            side_effect=ClientError(error_response, "GetObject")
        )

        with patch.object(s, "_client", return_value=cm):
            with pytest.raises(ClientError):
                await s.download_bytes("forbidden/key")


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


class TestDelete:
    async def test_calls_delete_object(self):
        s = _make_storage()
        cm, client = _mock_client()

        with patch.object(s, "_client", return_value=cm):
            await s.delete("some/key")
            client.delete_object.assert_awaited_once_with(
                Bucket="test-bucket", Key="some/key"
            )


# ---------------------------------------------------------------------------
# delete_prefix
# ---------------------------------------------------------------------------


class TestDeletePrefix:
    async def test_deletes_objects_and_returns_count(self):
        s = _make_storage()
        cm, client = _mock_client()

        # Mock paginator
        page_data = {
            "Contents": [
                {"Key": "prefix/a.png"},
                {"Key": "prefix/b.png"},
            ]
        }

        async def mock_paginate(**kwargs):
            yield page_data

        paginator = MagicMock()
        paginator.paginate = mock_paginate
        client.get_paginator = MagicMock(return_value=paginator)

        with patch.object(s, "_client", return_value=cm):
            count = await s.delete_prefix("prefix/")
            assert count == 2
            client.delete_objects.assert_awaited_once()

    async def test_empty_prefix_returns_zero(self):
        s = _make_storage()
        cm, client = _mock_client()

        async def mock_paginate(**kwargs):
            yield {"Contents": []}

        paginator = MagicMock()
        paginator.paginate = mock_paginate
        client.get_paginator = MagicMock(return_value=paginator)

        with patch.object(s, "_client", return_value=cm):
            count = await s.delete_prefix("empty/")
            assert count == 0


# ---------------------------------------------------------------------------
# generate_presigned_url
# ---------------------------------------------------------------------------


class TestGeneratePresignedUrl:
    async def test_returns_url(self):
        s = _make_storage()
        cm, client = _mock_client()
        client.generate_presigned_url = AsyncMock(
            return_value="https://presigned.example.com/file"
        )

        with patch.object(s, "_client", return_value=cm):
            url = await s.generate_presigned_url("pdfs/test.pdf")
            assert url == "https://presigned.example.com/file"

    async def test_passes_expiration(self):
        s = _make_storage()
        cm, client = _mock_client()
        client.generate_presigned_url = AsyncMock(return_value="https://url")

        with patch.object(s, "_client", return_value=cm):
            await s.generate_presigned_url("key", expiration=7200)
            call_kwargs = client.generate_presigned_url.call_args.kwargs
            assert call_kwargs["ExpiresIn"] == 7200

    async def test_includes_content_disposition_when_filename_given(self):
        s = _make_storage()
        cm, client = _mock_client()
        client.generate_presigned_url = AsyncMock(return_value="https://url")

        with patch.object(s, "_client", return_value=cm):
            await s.generate_presigned_url(
                "key", response_filename="book.pdf"
            )
            call_kwargs = client.generate_presigned_url.call_args.kwargs
            params = call_kwargs["Params"]
            assert "ResponseContentDisposition" in params
            assert "book.pdf" in params["ResponseContentDisposition"]

    async def test_no_disposition_without_filename(self):
        s = _make_storage()
        cm, client = _mock_client()
        client.generate_presigned_url = AsyncMock(return_value="https://url")

        with patch.object(s, "_client", return_value=cm):
            await s.generate_presigned_url("key")
            call_kwargs = client.generate_presigned_url.call_args.kwargs
            params = call_kwargs["Params"]
            assert "ResponseContentDisposition" not in params


# ---------------------------------------------------------------------------
# is_r2_configured
# ---------------------------------------------------------------------------


class TestIsR2Configured:
    def test_all_vars_set(self, monkeypatch):
        monkeypatch.setenv("R2_ACCOUNT_ID", "acct")
        monkeypatch.setenv("R2_ACCESS_KEY_ID", "key")
        monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "secret")
        monkeypatch.setenv("R2_BUCKET_NAME", "bucket")
        assert is_r2_configured() is True

    def test_missing_one_var(self, monkeypatch):
        monkeypatch.setenv("R2_ACCOUNT_ID", "acct")
        monkeypatch.setenv("R2_ACCESS_KEY_ID", "key")
        monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "secret")
        monkeypatch.delenv("R2_BUCKET_NAME", raising=False)
        assert is_r2_configured() is False

    def test_all_missing(self, monkeypatch):
        monkeypatch.delenv("R2_ACCOUNT_ID", raising=False)
        monkeypatch.delenv("R2_ACCESS_KEY_ID", raising=False)
        monkeypatch.delenv("R2_SECRET_ACCESS_KEY", raising=False)
        monkeypatch.delenv("R2_BUCKET_NAME", raising=False)
        assert is_r2_configured() is False


# ---------------------------------------------------------------------------
# get_storage
# ---------------------------------------------------------------------------


class TestGetStorage:
    def test_raises_when_not_configured(self, monkeypatch):
        # Reset singleton
        import src.core.storage
        src.core.storage._storage = None

        monkeypatch.delenv("R2_ACCOUNT_ID", raising=False)
        monkeypatch.delenv("R2_ACCESS_KEY_ID", raising=False)
        monkeypatch.delenv("R2_SECRET_ACCESS_KEY", raising=False)
        monkeypatch.delenv("R2_BUCKET_NAME", raising=False)

        with pytest.raises(RuntimeError, match="R2 storage not configured"):
            get_storage()

    def test_creates_storage_when_configured(self, monkeypatch):
        import src.core.storage
        src.core.storage._storage = None

        monkeypatch.setenv("R2_ACCOUNT_ID", "acct")
        monkeypatch.setenv("R2_ACCESS_KEY_ID", "key")
        monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "secret")
        monkeypatch.setenv("R2_BUCKET_NAME", "bucket")

        storage = get_storage()
        assert isinstance(storage, R2Storage)
        assert storage.bucket_name == "bucket"

        # Cleanup singleton
        src.core.storage._storage = None

    def test_returns_singleton(self, monkeypatch):
        import src.core.storage
        src.core.storage._storage = None

        monkeypatch.setenv("R2_ACCOUNT_ID", "acct")
        monkeypatch.setenv("R2_ACCESS_KEY_ID", "key")
        monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "secret")
        monkeypatch.setenv("R2_BUCKET_NAME", "bucket")

        s1 = get_storage()
        s2 = get_storage()
        assert s1 is s2

        # Cleanup singleton
        src.core.storage._storage = None
