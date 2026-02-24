"""Tests for credit system SQLAlchemy models."""

import uuid
from decimal import Decimal

from src.db.models import UserCredits, CreditPricing, CreditUsageLog


class TestUserCreditsModel:
    def test_create_per_batch_row(self):
        uc = UserCredits(
            user_id=uuid.uuid4(),
            original_amount=Decimal("10.00"),
            remaining_amount=Decimal("10.00"),
            source="purchase",
            is_refunded=False,
        )
        assert uc.original_amount == Decimal("10.00")
        assert uc.remaining_amount == Decimal("10.00")
        assert uc.source == "purchase"
        assert uc.is_refunded is False

    def test_signup_bonus(self):
        uc = UserCredits(
            user_id=uuid.uuid4(),
            original_amount=Decimal("1.00"),
            remaining_amount=Decimal("1.00"),
            source="signup_bonus",
        )
        assert uc.source == "signup_bonus"
        assert uc.credit_transaction_id is None

    def test_purchase_with_transaction_id(self):
        tx_id = uuid.uuid4()
        uc = UserCredits(
            user_id=uuid.uuid4(),
            original_amount=Decimal("10.00"),
            remaining_amount=Decimal("10.00"),
            source="purchase",
            credit_transaction_id=tx_id,
        )
        assert uc.credit_transaction_id == tx_id

    def test_column_defaults(self):
        """Verify that column-level defaults are configured correctly."""
        col = UserCredits.__table__.c.is_refunded
        assert col.default.arg is False


class TestCreditPricingModel:
    def test_create_pricing(self):
        pricing = CreditPricing(
            operation="story_generation",
            credit_cost=Decimal("1.00"),
            description="Story text generation",
            is_active=True,
        )
        assert pricing.operation == "story_generation"
        assert pricing.credit_cost == Decimal("1.00")
        assert pricing.is_active is True

    def test_default_values(self):
        pricing = CreditPricing(operation="test", credit_cost=Decimal("5.00"))
        assert pricing.description is None

    def test_column_defaults(self):
        """Verify that column-level defaults are configured correctly."""
        col = CreditPricing.__table__.c.is_active
        assert col.default.arg is True


class TestCreditUsageLogModel:
    def test_create_usage_log(self):
        user_id = uuid.uuid4()
        job_id = uuid.uuid4()
        log = CreditUsageLog(
            user_id=user_id,
            job_id=job_id,
            job_type="story",
            credits_used=Decimal("1.00"),
            status="reserved",
            description="Story: Test Story",
            extra_metadata={"pages": 5},
        )
        assert log.user_id == user_id
        assert log.job_id == job_id
        assert log.job_type == "story"
        assert log.credits_used == Decimal("1.00")
        assert log.status == "reserved"

    def test_column_defaults(self):
        """Verify that column-level defaults are configured correctly."""
        col = CreditUsageLog.__table__.c.status
        assert col.default.arg == "reserved"

    def test_table_structure(self):
        """Verify key table constraints and indexes exist."""
        table = CreditUsageLog.__table__
        index_names = {idx.name for idx in table.indexes}
        assert "idx_credit_usage_logs_user_id" in index_names
        assert "idx_credit_usage_logs_status" in index_names
        assert "idx_credit_usage_logs_created_at" in index_names
