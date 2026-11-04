"""
tests/test_database.py - Tests for SQLite Database and Audit Log Module
SafeAgent Wallet - CommitCon Hackathon (Hour 16–18)

Covers:
- Database schema initialization, columns, and indexes.
- Integer-cent storage ($4.50 -> 450 cents, $100.00 -> 10000 cents).
- Recording of all event types:
    * PAYMENT_SUCCESS
    * HUMAN_APPROVAL
    * HUMAN_REJECTION
    * PAYMENT_FAILED
    * AUTH_FAILED
    * RUNAWAY_BLOCKED
- Primary key constraint preventing duplicate transaction IDs.
- Idempotent migration from legacy JSON.
- Query filtering by status, event_type, search query, and ordering.
- State survival across database reopens.
"""

from decimal import Decimal
import json
from pathlib import Path
import sqlite3
import pytest

import config
from database import DatabaseManager, cents_to_dollars, dollars_to_cents
from purchase import ApprovalCenter
from wallet import SafeAgentWallet


class TestDatabaseSchemaAndInitialization:
    """Tests SQLite database creation, table schema, and indexes."""

    def test_database_initialization_and_schema(self, temp_db_path: Path):
        """Verifies database file creation, table structure, column types, and indexes."""
        db = DatabaseManager(temp_db_path)
        assert temp_db_path.exists()

        conn = sqlite3.connect(str(temp_db_path))
        try:
            cursor = conn.cursor()

            # Verify 'transactions' table
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='transactions';")
            assert cursor.fetchone() is not None

            # Verify columns
            cursor.execute("PRAGMA table_info(transactions);")
            columns = {row[1]: row[2] for row in cursor.fetchall()}
            expected = {
                "transaction_id": "TEXT",
                "request_id": "TEXT",
                "agent_id": "TEXT",
                "amount": "INTEGER",
                "description": "TEXT",
                "status": "TEXT",
                "reason": "TEXT",
                "timestamp": "TEXT",
                "balance_after": "INTEGER",
                "event_type": "TEXT",
                "lifetime_spent_after": "INTEGER",
                "attempt_number": "INTEGER",
            }
            for col, col_type in expected.items():
                assert col in columns
                assert columns[col] == col_type

            # Verify indexes
            cursor.execute("SELECT name FROM sqlite_master WHERE type='index';")
            indexes = {row[0] for row in cursor.fetchall()}
            for idx in [
                "idx_tx_timestamp",
                "idx_tx_status",
                "idx_tx_event_type",
                "idx_tx_agent_id",
                "idx_tx_request_id",
            ]:
                assert idx in indexes

            assert db.count_transactions() == 0
        finally:
            conn.close()

    def test_integer_cents_conversion_helpers(self):
        """Verifies dollars_to_cents and cents_to_dollars precision."""
        assert dollars_to_cents(Decimal("4.50")) == 450
        assert dollars_to_cents(4.50) == 450
        assert dollars_to_cents("15.00") == 1500
        assert dollars_to_cents(100) == 10000

        assert cents_to_dollars(450) == Decimal("4.50")
        assert cents_to_dollars(1500) == Decimal("15.00")
        assert cents_to_dollars(10000) == Decimal("100.00")


class TestTransactionPersistenceAndEventTypes:
    """Tests writing and querying diverse event types in SQLite."""

    def test_successful_payment_persisted_in_cents(self, wallet: SafeAgentWallet):
        """Successful payment persists with status=SUCCESS, event_type=PAYMENT_SUCCESS, and integer cents."""
        res = wallet.execute_payment(
            amount=Decimal("4.50"),
            recipient="USB-C Cable",
            agent_id="BuyerAgent",
        )
        assert res.success is True

        tx = wallet.db.get_transaction(res.transaction_id)
        assert tx is not None
        assert tx["transaction_id"] == res.transaction_id
        assert tx["status"] == config.STATUS_SUCCESS
        assert tx["event_type"] == config.EVENT_PAYMENT_SUCCESS
        assert tx["amount_cents"] == 450
        assert tx["balance_after_cents"] == 9550
        assert tx["amount"] == "4.50"
        assert tx["balance_after"] == "95.50"

    def test_human_approval_event_persisted(
        self,
        wallet: SafeAgentWallet,
        approval_center: ApprovalCenter,
        marketplace,
        sellers,
    ):
        """Human approval persists with event_type=HUMAN_APPROVAL and request_id."""
        prod = marketplace.get_product("prod_headphones")
        req = approval_center.create_request(
            product=prod,
            seller=sellers[prod.seller_id],
            user_query="buy headphones",
            order_id="ord_db_appr_1",
        )

        ok, msg, res = approval_center.approve_request(
            req.request_id, wallet, marketplace, config.DEFAULT_AUTH_TOKEN
        )
        assert ok is True

        tx = wallet.db.get_transaction(res.transaction_id)
        assert tx is not None
        assert tx["event_type"] == config.EVENT_HUMAN_APPROVAL
        assert tx["request_id"] == req.request_id
        assert tx["status"] == config.STATUS_SUCCESS
        assert tx["amount_cents"] == 1500

    def test_human_rejection_event_persisted(
        self,
        wallet: SafeAgentWallet,
        approval_center: ApprovalCenter,
        marketplace,
        sellers,
    ):
        """Human rejection persists with event_type=HUMAN_REJECTION, reason, and $0 balance change."""
        prod = marketplace.get_product("prod_headphones")
        req = approval_center.create_request(
            product=prod,
            seller=sellers[prod.seller_id],
            user_query="buy headphones",
            order_id="ord_db_rej_1",
        )

        ok, msg = approval_center.reject_request(
            req.request_id, wallet, reason="Price too high."
        )
        assert ok is True

        records = wallet.db.get_all_transactions(event_type=config.EVENT_HUMAN_REJECTION)
        assert len(records) >= 1
        tx = records[0]
        assert tx["request_id"] == req.request_id
        assert tx["status"] == config.STATUS_REJECTED
        assert tx["event_type"] == config.EVENT_HUMAN_REJECTION
        assert tx["balance_after_cents"] == 10000

    def test_failed_purchases_persisted(self, wallet: SafeAgentWallet):
        """Insufficient balance and invalid authorization are recorded in SQLite."""
        # 1. Insufficient balance
        res_insufficient = wallet.execute_payment(
            amount=Decimal("150.00"),
            recipient="Enterprise Server",
            human_approved=True,
            auth_token=config.DEFAULT_AUTH_TOKEN,
        )
        tx1 = wallet.db.get_transaction(res_insufficient.transaction_id)
        assert tx1 is not None
        assert tx1["status"] == config.STATUS_REJECTED
        assert tx1["event_type"] == config.EVENT_PAYMENT_FAILED

        # 2. Invalid auth token
        res_bad_auth = wallet.execute_payment(
            amount=Decimal("25.00"),
            recipient="Keyboard",
            human_approved=True,
            auth_token="BAD_TOKEN",
        )
        tx2 = wallet.db.get_transaction(res_bad_auth.transaction_id)
        assert tx2 is not None
        assert tx2["event_type"] == config.EVENT_AUTH_FAILED

    def test_runaway_agent_events_persisted(self, wallet: SafeAgentWallet):
        """Rate limit breach and subsequent locked wallet blocks persist with RUNAWAY_BLOCKED."""
        results = wallet.simulate_runaway_agent_attack(attempts=6)
        breach_res = results[3]  # Attempt 4
        blocked_res = results[4]  # Attempt 5

        tx_breach = wallet.db.get_transaction(breach_res.transaction_id)
        assert tx_breach is not None
        assert tx_breach["status"] == config.STATUS_BLOCKED
        assert tx_breach["event_type"] == config.EVENT_RUNAWAY_BLOCKED

        tx_blocked = wallet.db.get_transaction(blocked_res.transaction_id)
        assert tx_blocked is not None
        assert tx_blocked["status"] == config.STATUS_BLOCKED
        assert tx_blocked["event_type"] == config.EVENT_RUNAWAY_BLOCKED


class TestDatabaseIntegrityAndQueries:
    """Tests duplicate rejection, query filtering, and restart persistence."""

    def test_duplicate_transaction_id_rejected_by_primary_key(self, db_manager: DatabaseManager):
        """Primary key constraint prevents duplicate transaction_id rows."""
        tx_data = {
            "transaction_id": "tx_pk_unique_1",
            "request_id": "req_1",
            "agent_id": "AgentX",
            "amount": 5.00,
            "description": "Item",
            "status": "SUCCESS",
            "reason": "OK",
            "timestamp": "2026-11-04T05:00:00Z",
            "balance_after": 95.00,
            "event_type": config.EVENT_PAYMENT_SUCCESS,
        }

        # 1st insert
        assert db_manager.insert_transaction(tx_data) is True
        assert db_manager.count_transactions() == 1

        # Duplicate insert fails
        assert db_manager.insert_transaction(tx_data) is False
        assert db_manager.count_transactions() == 1

    def test_query_filtering_and_search(self, db_manager: DatabaseManager):
        """Tests filtering by status, event_type, search term, and latest_first sorting."""
        items = [
            ("tx_q1", "req_1", "USB-C Fast Cable", "SUCCESS", config.EVENT_PAYMENT_SUCCESS, 4.50, "2026-11-04T01:00:00Z"),
            ("tx_q2", "req_2", "Wireless Mouse", "SUCCESS", config.EVENT_PAYMENT_SUCCESS, 9.00, "2026-11-04T02:00:00Z"),
            ("tx_q3", "req_3", "Bluetooth Headphones", "REJECTED", config.EVENT_HUMAN_REJECTION, 15.00, "2026-11-04T03:00:00Z"),
            ("tx_q4", "req_4", "USB-C Rapid Cable", "BLOCKED", config.EVENT_RUNAWAY_BLOCKED, 4.50, "2026-11-04T04:00:00Z"),
        ]
        for tx_id, r_id, desc, st, evt, amt, ts in items:
            db_manager.insert_transaction({
                "transaction_id": tx_id,
                "request_id": r_id,
                "agent_id": "Bot",
                "amount": amt,
                "description": desc,
                "status": st,
                "reason": "test",
                "timestamp": ts,
                "balance_after": 90.00,
                "event_type": evt,
            })

        # Filter by status
        assert len(db_manager.get_all_transactions(status="SUCCESS")) == 2
        assert len(db_manager.get_all_transactions(status="BLOCKED")) == 1

        # Filter by event_type
        assert len(db_manager.get_all_transactions(event_type=config.EVENT_HUMAN_REJECTION)) == 1

        # Search by description substring
        assert len(db_manager.get_all_transactions(search="Cable")) == 2

        # Search by request_id
        found = db_manager.get_all_transactions(search="req_3")
        assert len(found) == 1
        assert found[0]["transaction_id"] == "tx_q3"

        # Ordering
        latest_first = db_manager.get_all_transactions(latest_first=True)
        assert latest_first[0]["transaction_id"] == "tx_q4"
        assert latest_first[-1]["transaction_id"] == "tx_q1"

    def test_database_persistence_across_wallet_reopens(
        self,
        temp_db_path: Path,
        temp_json_path: Path,
    ):
        """Data persists intact when creating a fresh SafeAgentWallet on an existing SQLite database."""
        # Session 1: Create wallet & execute payment
        w1 = SafeAgentWallet(
            initial_balance=Decimal("100.00"),
            db_path=temp_db_path,
            transactions_file=temp_json_path,
        )
        res = w1.execute_payment(Decimal("4.50"), "USB-C Cable")
        assert res.success is True
        del w1

        # Session 2: Fresh instance on same db_path
        w2 = SafeAgentWallet(
            load_existing=True,
            db_path=temp_db_path,
            transactions_file=temp_json_path,
        )
        assert w2.db.count_transactions() == 1
        tx = w2.db.get_transaction(res.transaction_id)
        assert tx is not None
        assert tx["amount_cents"] == 450
        assert tx["status"] == config.STATUS_SUCCESS

    def test_json_migration_idempotent_and_non_destructive(
        self,
        temp_db_path: Path,
        temp_json_path: Path,
    ):
        """Migration imports valid records from JSON without duplicates and preserves file."""
        sample_json = [
            {
                "transaction_id": "tx_mig_1",
                "timestamp": "2026-11-04T00:00:00Z",
                "amount": "4.50",
                "recipient": "USB-C Cable",
                "status": "SUCCESS",
                "reason": "OK",
                "balance_after": "95.50",
                "lifetime_spent_after": "4.50",
                "requires_human_approval": False,
                "human_approved": None,
                "agent_id": "Bot",
                "attempt_number": None,
            }
        ]
        with open(temp_json_path, "w", encoding="utf-8") as f:
            json.dump(sample_json, f)

        db = DatabaseManager(temp_db_path)
        assert db.count_transactions() == 0

        # Import 1
        imported = db.migrate_from_json(temp_json_path)
        assert imported == 1
        assert db.count_transactions() == 1

        # Re-import -> 0 new records
        re_imported = db.migrate_from_json(temp_json_path)
        assert re_imported == 0
        assert db.count_transactions() == 1

        # JSON file remains on disk
        assert temp_json_path.exists()
