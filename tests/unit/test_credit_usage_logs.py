"""Tests for CreditService.get_usage_logs — paginated, date-filtered queries."""

import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.credit_service import CreditService


@pytest.fixture
def mock_session():
    return AsyncMock()


@pytest.fixture
def service(mock_session):
    return CreditService(mock_session)


class TestGetUsageLogs:
    @pytest.mark.asyncio
    async def test_returns_items_and_total(self, service, mock_session):
        now = datetime.now(timezone.utc)
        from_date = now - timedelta(hours=24)

        mock_log = MagicMock()
        mock_log.id = uuid.uuid4()
        mock_log.job_id = uuid.uuid4()
        mock_log.job_type = "story"
        mock_log.credits_used = Decimal("1.00")
        mock_log.status = "confirmed"
        mock_log.description = "A test story"
        mock_log.extra_metadata = {"title": "Test"}
        mock_log.created_at = now

        # First call: count query
        mock_count_result = MagicMock()
        mock_count_result.scalar_one.return_value = 1

        # Second call: items query
        mock_items_result = MagicMock()
        mock_items_result.scalars.return_value.all.return_value = [mock_log]

        mock_session.execute.side_effect = [mock_count_result, mock_items_result]

        items, total = await service.get_usage_logs(
            user_id=uuid.uuid4(),
            from_date=from_date,
            to_date=now,
            page=1,
            page_size=20,
        )

        assert total == 1
        assert len(items) == 1
        assert items[0].job_type == "story"
        assert items[0].credits_used == Decimal("1.00")

    @pytest.mark.asyncio
    async def test_pagination_offset(self, service, mock_session):
        now = datetime.now(timezone.utc)
        from_date = now - timedelta(hours=24)

        mock_count_result = MagicMock()
        mock_count_result.scalar_one.return_value = 0

        mock_items_result = MagicMock()
        mock_items_result.scalars.return_value.all.return_value = []

        mock_session.execute.side_effect = [mock_count_result, mock_items_result]

        items, total = await service.get_usage_logs(
            user_id=uuid.uuid4(),
            from_date=from_date,
            to_date=now,
            page=2,
            page_size=10,
        )

        assert total == 0
        assert len(items) == 0
