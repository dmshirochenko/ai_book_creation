"""Tests for retry-related repository functions."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest
from sqlalchemy import select, update, delete

from src.db import repository as repo
from src.db.models import GeneratedImage, GeneratedPdf


class TestGetFailedImagesForBook:
    async def test_calls_select_with_correct_filters(self):
        session = AsyncMock()
        book_job_id = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=mock_result)

        result = await repo.get_failed_images_for_book(session, book_job_id)
        assert result == []
        session.execute.assert_awaited_once()


class TestResetImageForRetry:
    async def test_updates_image_fields(self):
        session = AsyncMock()
        image_id = uuid.uuid4()

        await repo.reset_image_for_retry(session, image_id, retry_attempt=1)
        session.execute.assert_awaited_once()
        session.commit.assert_awaited_once()


class TestDeletePdfsForBook:
    async def test_deletes_pdfs_and_returns_r2_keys(self):
        session = AsyncMock()
        book_job_id = uuid.uuid4()

        mock_pdf1 = MagicMock()
        mock_pdf1.file_path = "pdfs/job1/booklet.pdf"
        mock_pdf2 = MagicMock()
        mock_pdf2.file_path = "pdfs/job1/review.pdf"

        mock_select_result = MagicMock()
        mock_select_result.scalars.return_value.all.return_value = [mock_pdf1, mock_pdf2]

        mock_delete_result = MagicMock()

        session.execute = AsyncMock(side_effect=[mock_select_result, mock_delete_result])

        r2_keys = await repo.delete_pdfs_for_book(session, book_job_id)
        assert r2_keys == ["pdfs/job1/booklet.pdf", "pdfs/job1/review.pdf"]
        assert session.execute.call_count == 2
        session.commit.assert_awaited_once()
