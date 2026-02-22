"""Tests for CreditService — credit deduction with FIFO batch consumption."""

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.credit_service import CreditService, InsufficientCreditsError


@pytest.fixture
def mock_session():
    session = AsyncMock()
    return session


@pytest.fixture
def service(mock_session):
    return CreditService(mock_session)


class TestGetPricing:
    @pytest.mark.asyncio
    async def test_returns_active_pricing_dict(self, service, mock_session):
        mock_row1 = MagicMock()
        mock_row1.operation = "story_generation"
        mock_row1.credit_cost = Decimal("1.00")
        mock_row2 = MagicMock()
        mock_row2.operation = "page_with_images"
        mock_row2.credit_cost = Decimal("2.00")
        mock_row3 = MagicMock()
        mock_row3.operation = "page_without_images"
        mock_row3.credit_cost = Decimal("1.00")

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_row1, mock_row2, mock_row3]
        mock_session.execute.return_value = mock_result

        pricing = await service.get_pricing()
        assert pricing == {
            "story_generation": Decimal("1.00"),
            "page_with_images": Decimal("2.00"),
            "page_without_images": Decimal("1.00"),
        }


class TestCalculateCosts:
    @pytest.mark.asyncio
    async def test_story_cost(self, service):
        with patch.object(service, "get_pricing", return_value={
            "story_generation": Decimal("1.00"),
            "page_with_images": Decimal("2.00"),
            "page_without_images": Decimal("1.00"),
        }):
            cost = await service.calculate_story_cost()
            assert cost == Decimal("1.00")

    @pytest.mark.asyncio
    async def test_book_cost_with_images(self, service):
        with patch.object(service, "get_pricing", return_value={
            "story_generation": Decimal("1.00"),
            "page_with_images": Decimal("2.00"),
            "page_without_images": Decimal("1.00"),
        }):
            cost = await service.calculate_book_cost(pages=8, with_images=True)
            assert cost == Decimal("16.00")

    @pytest.mark.asyncio
    async def test_book_cost_without_images(self, service):
        with patch.object(service, "get_pricing", return_value={
            "story_generation": Decimal("1.00"),
            "page_with_images": Decimal("2.00"),
            "page_without_images": Decimal("1.00"),
        }):
            cost = await service.calculate_book_cost(pages=8, with_images=False)
            assert cost == Decimal("8.00")

    @pytest.mark.asyncio
    async def test_book_cost_fractional(self, service):
        with patch.object(service, "get_pricing", return_value={
            "page_without_images": Decimal("0.50"),
        }):
            cost = await service.calculate_book_cost(pages=3, with_images=False)
            assert cost == Decimal("1.50")

    @pytest.mark.asyncio
    async def test_book_cost_zero_pages(self, service):
        with patch.object(service, "get_pricing", return_value={
            "page_with_images": Decimal("2.00"),
        }):
            cost = await service.calculate_book_cost(pages=0, with_images=True)
            assert cost == Decimal("0")


class TestGetBalance:
    @pytest.mark.asyncio
    async def test_returns_sum_of_remaining(self, service, mock_session):
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = Decimal("25.50")
        mock_session.execute.return_value = mock_result
        balance = await service.get_balance(uuid.uuid4())
        assert balance == Decimal("25.50")

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_rows(self, service, mock_session):
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = Decimal("0")
        mock_session.execute.return_value = mock_result
        balance = await service.get_balance(uuid.uuid4())
        assert balance == Decimal("0")


class TestReserve:
    @pytest.mark.asyncio
    async def test_skip_if_zero_amount(self, service, mock_session):
        result = await service.reserve(
            user_id=uuid.uuid4(), amount=Decimal("0"),
            job_id=uuid.uuid4(), job_type="story",
            description="test", metadata={},
        )
        assert result is None
        mock_session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_insufficient_credits_raises(self, service, mock_session):
        batch_a = MagicMock(); batch_a.id = uuid.uuid4(); batch_a.remaining_amount = Decimal("3.00")
        batch_b = MagicMock(); batch_b.id = uuid.uuid4(); batch_b.remaining_amount = Decimal("2.00")
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [batch_a, batch_b]
        mock_session.execute.return_value = mock_result
        with pytest.raises(InsufficientCreditsError) as exc_info:
            await service.reserve(user_id=uuid.uuid4(), amount=Decimal("10.00"),
                job_id=uuid.uuid4(), job_type="story", description="test", metadata={})
        assert exc_info.value.balance == Decimal("5.00")
        assert exc_info.value.required == Decimal("10.00")

    @pytest.mark.asyncio
    async def test_fifo_single_batch(self, service, mock_session):
        batch = MagicMock(); batch.id = uuid.uuid4(); batch.remaining_amount = Decimal("10.00")
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [batch]
        mock_session.execute.return_value = mock_result
        mock_session.add = MagicMock()
        async def fake_refresh(obj, **kw):
            obj.id = uuid.uuid4()
        mock_session.refresh = fake_refresh
        result = await service.reserve(user_id=uuid.uuid4(), amount=Decimal("3.00"),
            job_id=uuid.uuid4(), job_type="story", description="test", metadata={})
        assert result is not None
        assert batch.remaining_amount == Decimal("7.00")

    @pytest.mark.asyncio
    async def test_fifo_multi_batch(self, service, mock_session):
        batch_a = MagicMock(); batch_a.id = uuid.uuid4(); batch_a.remaining_amount = Decimal("2.00")
        batch_b = MagicMock(); batch_b.id = uuid.uuid4(); batch_b.remaining_amount = Decimal("5.00")
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [batch_a, batch_b]
        mock_session.execute.return_value = mock_result
        mock_session.add = MagicMock()
        async def fake_refresh(obj, **kw):
            obj.id = uuid.uuid4()
        mock_session.refresh = fake_refresh
        result = await service.reserve(user_id=uuid.uuid4(), amount=Decimal("3.00"),
            job_id=uuid.uuid4(), job_type="story", description="test", metadata={})
        assert result is not None
        assert batch_a.remaining_amount == Decimal("0")
        assert batch_b.remaining_amount == Decimal("4.00")


class TestConfirm:
    @pytest.mark.asyncio
    async def test_confirm_reserved_log(self, service, mock_session):
        mock_log = MagicMock(); mock_log.status = "reserved"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_log
        mock_session.execute.return_value = mock_result
        await service.confirm(uuid.uuid4())
        assert mock_log.status == "confirmed"
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_confirm_already_confirmed_is_noop(self, service, mock_session):
        mock_log = MagicMock(); mock_log.status = "confirmed"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_log
        mock_session.execute.return_value = mock_result
        await service.confirm(uuid.uuid4())
        mock_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_confirm_none_id_is_noop(self, service, mock_session):
        await service.confirm(None)
        mock_session.execute.assert_not_called()


class TestRelease:
    @pytest.mark.asyncio
    async def test_release_reserved_restores_batches(self, service, mock_session):
        batch_a_id = uuid.uuid4(); batch_b_id = uuid.uuid4()
        mock_log = MagicMock()
        mock_log.status = "reserved"
        mock_log.credits_used = Decimal("3.00")
        mock_log.extra_metadata = {
            "batches_consumed": [
                {"batch_id": str(batch_a_id), "amount": 2.0},
                {"batch_id": str(batch_b_id), "amount": 1.0},
            ]
        }
        batch_a = MagicMock(); batch_a.remaining_amount = Decimal("0")
        batch_b = MagicMock(); batch_b.remaining_amount = Decimal("4.00")
        mock_result_log = MagicMock(); mock_result_log.scalar_one_or_none.return_value = mock_log
        mock_result_a = MagicMock(); mock_result_a.scalar_one_or_none.return_value = batch_a
        mock_result_b = MagicMock(); mock_result_b.scalar_one_or_none.return_value = batch_b
        mock_session.execute.side_effect = [mock_result_log, mock_result_a, mock_result_b]
        await service.release(uuid.uuid4())
        assert mock_log.status == "refunded"
        assert batch_a.remaining_amount == Decimal("2.00")
        assert batch_b.remaining_amount == Decimal("5.00")
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_release_already_refunded_is_noop(self, service, mock_session):
        mock_log = MagicMock(); mock_log.status = "refunded"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_log
        mock_session.execute.return_value = mock_result
        await service.release(uuid.uuid4())
        mock_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_release_none_id_is_noop(self, service, mock_session):
        await service.release(None)
        mock_session.execute.assert_not_called()
