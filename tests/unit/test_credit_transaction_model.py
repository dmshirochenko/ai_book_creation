"""Tests for CreditTransaction SQLAlchemy model."""

import uuid
from decimal import Decimal

from src.db.models import CreditTransaction


class TestCreditTransactionModel:
    def test_create_purchase_transaction(self):
        tx = CreditTransaction(
            user_id=uuid.uuid4(),
            amount=Decimal("10.00"),
            transaction_type="purchase",
            stripe_session_id="cs_test_abc123",
            stripe_event_id="evt_abc123",
        )
        assert tx.amount == Decimal("10.00")
        assert tx.transaction_type == "purchase"
        assert tx.stripe_session_id == "cs_test_abc123"
        assert tx.stripe_event_id == "evt_abc123"

    def test_create_refund_transaction(self):
        tx = CreditTransaction(
            user_id=uuid.uuid4(),
            amount=Decimal("-10.00"),
            transaction_type="refund",
            stripe_session_id="cs_test_abc123",
            stripe_event_id="evt_refund_123",
            extra_metadata={"refund_id": "re_123", "reason": "requested_by_customer"},
        )
        assert tx.amount == Decimal("-10.00")
        assert tx.transaction_type == "refund"
        assert tx.extra_metadata["reason"] == "requested_by_customer"

    def test_table_structure(self):
        table = CreditTransaction.__table__
        index_names = {idx.name for idx in table.indexes}
        assert "idx_credit_transactions_stripe_event_id" in index_names
        assert "idx_credit_transactions_user_id" in index_names
