"""
test_database.py - Comprehensive Unit Tests for Database and Audit Log Module
SafeAgent Wallet - CommitCon Hackathon (Hour 14–16)

Tests cover:
1. test_01_database_initialization: Table creation, schema verification, and index creation in temporary DB.
2. test_02_successful_payment_persisted: Verifies successful payments persist with correct amount in cents, balance_after, status=SUCCESS, and event_type=PAYMENT_SUCCESS.
3. test_03_approval_event_persisted: Verifies approval events persist with event_type=HUMAN_APPROVAL and request_id recorded.
4. test_04_rejection_event_persisted: Verifies rejection events persist with event_type=HUMAN_REJECTION, rejection reason, and $0 balance change.
5. test_05_failed_purchase_persisted: Verifies insufficient balance and invalid auth attempts persist as failed records.
6. test_06_runaway_attempt_persisted: Verifies rate limit violation attempt persists with event_type=RUNAWAY_BLOCKED.
7. test_07_blocked_transaction_persisted: Verifies blocked transactions persist with status=BLOCKED and WALLET_LOCKED.
8. test_08_duplicate_transaction_ids_prevented: Verifies duplicate transaction IDs are prevented and do not create duplicate rows.
9. test_09_existing_json_transactions_migrate_correctly: Verifies migration from JSON to SQLite imports all records without duplicates.
10. test_10_transaction_history_retrieves_records_correctly: Verifies filtering by status, event_type, and search works accurately.
11. test_11_database_survives_application_restart: Verifies that creating a new DatabaseManager or SafeAgentWallet instance retains all previous transactions.
12. test_12_existing_wallet_and_approval_tests_pass: Verifies end-to-end multi-agent purchase lifecycle passes seamlessly with SQLite active.
"""

from decimal import Decimal
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest

from buyer_agent import BuyerAgent
import config
from database import DatabaseManager, cents_to_dollars, dollars_to_cents
from marketplace import Marketplace
from purchase import ApprovalCenter
from seller_agent import create_default_sellers
from wallet import PaymentResult, SafeAgentWallet


class TestDatabaseAndAuditLog(unittest.TestCase):
    """Full test suite for SQLite Database persistence and audit logging."""

    def setUp(self):
        """Creates an isolated temporary directory for each test."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.db_path = self.temp_path / "test_safeagent.db"
        self.json_path = self.temp_path / "test_transactions.json"

    def tearDown(self):
        """Cleans up the temporary directory after each test."""
        self.temp_dir.cleanup()

    def test_01_database_initialization(self):
        """
        Scenario 1: Verifies database initialization, table creation, schema,
        and required indexes in a temporary database.
        """
        db = DatabaseManager(self.db_path)
        self.assertTrue(self.db_path.exists(), "Database file should exist on disk.")

        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.cursor()

            # Verify 'transactions' table exists
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='transactions';"
            )
            table = cursor.fetchone()
            self.assertIsNotNone(table, "Table 'transactions' must exist.")

            # Verify schema columns
            cursor.execute("PRAGMA table_info(transactions);")
            columns = {row[1]: row[2] for row in cursor.fetchall()}

            expected_columns = [
                ("transaction_id", "TEXT"),
                ("request_id", "TEXT"),
                ("agent_id", "TEXT"),
                ("amount", "INTEGER"),
                ("description", "TEXT"),
                ("status", "TEXT"),
                ("reason", "TEXT"),
                ("timestamp", "TEXT"),
                ("balance_after", "INTEGER"),
                ("event_type", "TEXT"),
                ("lifetime_spent_after", "INTEGER"),
                ("attempt_number", "INTEGER"),
            ]
            for col_name, col_type in expected_columns:
                self.assertIn(col_name, columns, f"Column '{col_name}' missing from transactions table.")
                self.assertEqual(columns[col_name], col_type, f"Column '{col_name}' type mismatch.")

            # Verify indexes
            cursor.execute("SELECT name FROM sqlite_master WHERE type='index';")
            indexes = {row[0] for row in cursor.fetchall()}
            expected_indexes = [
                "idx_tx_timestamp",
                "idx_tx_status",
                "idx_tx_event_type",
                "idx_tx_agent_id",
                "idx_tx_request_id",
            ]
            for idx in expected_indexes:
                self.assertIn(idx, indexes, f"Index '{idx}' missing.")

            # Table should be initially empty
            self.assertEqual(db.count_transactions(), 0)
        finally:
            conn.close()

    def test_02_successful_payment_persisted(self):
        """
        Scenario 2: Verifies that successful payments persist with correct amount in cents,
        balance_after, status=SUCCESS, and event_type=PAYMENT_SUCCESS.
        """
        wallet = SafeAgentWallet(
            initial_balance=Decimal("100.00"),
            db_path=self.db_path,
            transactions_file=self.json_path,
        )

        res = wallet.execute_payment(
            amount=Decimal("4.50"),
            recipient="USB-C Fast Charging Cable",
            agent_id="TestBuyerAgent",
        )
        self.assertTrue(res.success)
        self.assertEqual(res.status, config.STATUS_SUCCESS)

        # Retrieve from SQLite database
        tx = wallet.db.get_transaction(res.transaction_id)
        self.assertIsNotNone(tx)
        self.assertEqual(tx["transaction_id"], res.transaction_id)
        self.assertEqual(tx["status"], config.STATUS_SUCCESS)
        self.assertEqual(tx["event_type"], config.EVENT_PAYMENT_SUCCESS)
        # Verify integer-cent storage
        self.assertEqual(tx["amount_cents"], 450)
        self.assertEqual(tx["balance_after_cents"], 9550)
        self.assertEqual(tx["amount"], "4.50")
        self.assertEqual(tx["balance_after"], "95.50")
        self.assertEqual(tx["agent_id"], "TestBuyerAgent")

    def test_03_approval_event_persisted(self):
        """
        Scenario 3: Verifies that human approval events persist with
        event_type=HUMAN_APPROVAL and request_id recorded.
        """
        wallet = SafeAgentWallet(
            initial_balance=Decimal("100.00"),
            db_path=self.db_path,
            transactions_file=self.json_path,
        )
        approval_center = ApprovalCenter()

        marketplace = Marketplace()
        product = marketplace.get_product("prod_headphones")  # $15.00
        self.assertIsNotNone(product)

        appr_req = approval_center.create_request(
            product=product,
            seller=create_default_sellers()[product.seller_id],
            user_query="buy headphones",
            order_id="ord_test_approval_123",
        )

        ok, msg, wallet_res = approval_center.approve_request(
            request_id=appr_req.request_id,
            wallet=wallet,
            marketplace=marketplace,
            auth_token=config.DEFAULT_AUTH_TOKEN,
        )
        self.assertTrue(ok)
        self.assertIsNotNone(wallet_res)
        self.assertTrue(wallet_res.success)

        # Verify DB record
        tx = wallet.db.get_transaction(wallet_res.transaction_id)
        self.assertIsNotNone(tx)
        self.assertEqual(tx["event_type"], config.EVENT_HUMAN_APPROVAL)
        self.assertEqual(tx["request_id"], appr_req.request_id)
        self.assertEqual(tx["status"], config.STATUS_SUCCESS)
        self.assertEqual(tx["amount_cents"], 1500)
        self.assertEqual(tx["balance_after_cents"], 8500)

    def test_04_rejection_event_persisted(self):
        """
        Scenario 4: Verifies rejection events persist with event_type=HUMAN_REJECTION,
        rejection reason, and $0 balance change.
        """
        wallet = SafeAgentWallet(
            initial_balance=Decimal("100.00"),
            db_path=self.db_path,
            transactions_file=self.json_path,
        )
        approval_center = ApprovalCenter()
        marketplace = Marketplace()
        product = marketplace.get_product("prod_headphones")

        appr_req = approval_center.create_request(
            product=product,
            seller=create_default_sellers()[product.seller_id],
            user_query="buy headphones",
            order_id="ord_test_rejection_456",
        )

        initial_balance = wallet.balance
        ok, msg = approval_center.reject_request(
            request_id=appr_req.request_id,
            wallet=wallet,
            reason="Price exceeds quarterly gadget allowance.",
        )
        self.assertTrue(ok)

        # Balance must remain completely unchanged
        self.assertEqual(wallet.balance, initial_balance)

        # Check DB audit records
        audit_records = wallet.db.get_all_transactions(event_type=config.EVENT_HUMAN_REJECTION)
        self.assertGreaterEqual(len(audit_records), 1)
        tx = audit_records[0]
        self.assertEqual(tx["request_id"], appr_req.request_id)
        self.assertEqual(tx["status"], config.STATUS_REJECTED)
        self.assertEqual(tx["event_type"], config.EVENT_HUMAN_REJECTION)
        self.assertIn("rejected by human reviewer", tx["reason"].lower())
        self.assertEqual(appr_req.decision_reason, "Price exceeds quarterly gadget allowance.")
        self.assertEqual(tx["balance_after_cents"], 10000)

    def test_05_failed_purchase_persisted(self):
        """
        Scenario 5: Verifies insufficient balance and invalid auth attempts persist as failed records.
        """
        wallet = SafeAgentWallet(
            initial_balance=Decimal("100.00"),
            db_path=self.db_path,
            transactions_file=self.json_path,
        )

        # 1. Attempt payment exceeding balance
        res_insufficient = wallet.execute_payment(
            amount=Decimal("150.00"),
            recipient="Enterprise Server Rack",
            human_approved=True,
            auth_token=config.DEFAULT_AUTH_TOKEN,
        )
        self.assertFalse(res_insufficient.success)
        self.assertEqual(res_insufficient.status, config.STATUS_REJECTED)

        tx_insufficient = wallet.db.get_transaction(res_insufficient.transaction_id)
        self.assertIsNotNone(tx_insufficient)
        self.assertEqual(tx_insufficient["status"], config.STATUS_REJECTED)
        self.assertEqual(tx_insufficient["event_type"], config.EVENT_PAYMENT_FAILED)
        self.assertIn("Insufficient wallet balance", tx_insufficient["reason"])

        # 2. Attempt payment with invalid auth token
        res_invalid_auth = wallet.execute_payment(
            amount=Decimal("25.00"),
            recipient="Mechanical Keyboard",
            human_approved=True,
            auth_token="TAMPERED_TOKEN_999",
        )
        self.assertFalse(res_invalid_auth.success)
        self.assertEqual(res_invalid_auth.status, config.STATUS_REJECTED)

        tx_auth = wallet.db.get_transaction(res_invalid_auth.transaction_id)
        self.assertIsNotNone(tx_auth)
        self.assertEqual(tx_auth["event_type"], config.EVENT_AUTH_FAILED)
        self.assertIn("Invalid human authorization", tx_auth["reason"])

    def test_06_runaway_attempt_persisted(self):
        """
        Scenario 6: Verifies rate limit violation attempt persists with event_type=RUNAWAY_BLOCKED.
        """
        wallet = SafeAgentWallet(
            initial_balance=Decimal("100.00"),
            db_path=self.db_path,
            transactions_file=self.json_path,
        )

        sim_time = 1000.0
        # Attempts 1, 2, 3: Allowed
        for i in range(1, 4):
            res = wallet.execute_payment(
                amount=Decimal("4.50"),
                recipient="USB-C Cable",
                attempt_number=i,
                current_time=sim_time + (i * 0.1),
            )
            self.assertTrue(res.success)

        # Attempt 4: Rate limit breach -> Locked & Blocked
        res_breach = wallet.execute_payment(
            amount=Decimal("4.50"),
            recipient="USB-C Cable",
            attempt_number=4,
            current_time=sim_time + 0.4,
        )
        self.assertFalse(res_breach.success)
        self.assertEqual(res_breach.status, config.STATUS_BLOCKED)

        tx = wallet.db.get_transaction(res_breach.transaction_id)
        self.assertIsNotNone(tx)
        self.assertEqual(tx["status"], config.STATUS_BLOCKED)
        self.assertEqual(tx["event_type"], config.EVENT_RUNAWAY_BLOCKED)
        self.assertEqual(tx["attempt_number"], 4)
        self.assertIn(config.REASON_RATE_LIMIT_EXCEEDED, tx["reason"])

    def test_07_blocked_transaction_persisted(self):
        """
        Scenario 7: Verifies blocked transactions persist with status=BLOCKED, WALLET_LOCKED,
        and zero funds deducted.
        """
        wallet = SafeAgentWallet(
            initial_balance=Decimal("100.00"),
            db_path=self.db_path,
            transactions_file=self.json_path,
        )
        wallet.lock(reason=config.REASON_RATE_LIMIT_EXCEEDED)
        self.assertTrue(wallet.is_locked)

        initial_bal = wallet.balance
        res = wallet.execute_payment(
            amount=Decimal("4.50"),
            recipient="USB-C Cable",
            agent_id="RunawayAgent",
            attempt_number=5,
            is_agent_attempt=True,
        )
        self.assertFalse(res.success)
        self.assertEqual(res.status, config.STATUS_BLOCKED)
        self.assertEqual(wallet.balance, initial_bal)

        tx = wallet.db.get_transaction(res.transaction_id)
        self.assertIsNotNone(tx)
        self.assertEqual(tx["status"], config.STATUS_BLOCKED)
        self.assertIn(config.REASON_WALLET_LOCKED, tx["reason"])
        self.assertEqual(tx["balance_after_cents"], 10000)

    def test_08_duplicate_transaction_ids_prevented(self):
        """
        Scenario 8: Verifies duplicate transaction IDs are prevented and do not create duplicate rows.
        """
        db = DatabaseManager(self.db_path)

        tx_payload = {
            "transaction_id": "tx_unique_001",
            "request_id": "req_001",
            "agent_id": "Agent1",
            "amount": 4.50,
            "description": "USB-C Cable",
            "status": config.STATUS_SUCCESS,
            "reason": "Payment executed.",
            "timestamp": "2026-11-04T05:00:00Z",
            "balance_after": 95.50,
            "event_type": config.EVENT_PAYMENT_SUCCESS,
        }

        # First insert succeeds
        self.assertTrue(db.insert_transaction(tx_payload))
        self.assertEqual(db.count_transactions(), 1)

        # Duplicate insert fails
        self.assertFalse(db.insert_transaction(tx_payload))
        self.assertEqual(db.count_transactions(), 1)

        # Wallet level duplicate rejection
        wallet = SafeAgentWallet(
            initial_balance=Decimal("100.00"),
            db_path=self.db_path,
            transactions_file=self.json_path,
        )
        res_dup = wallet.execute_payment(
            amount=Decimal("4.50"),
            recipient="USB-C Cable",
            transaction_id="tx_unique_001",
        )
        self.assertFalse(res_dup.success)
        self.assertIn("Duplicate transaction ID", res_dup.reason)
        # Database count remains 1
        self.assertEqual(db.count_transactions(), 1)

    def test_09_existing_json_transactions_migrate_correctly(self):
        """
        Scenario 9: Verifies migration from JSON to SQLite imports all records without duplicates.
        Ensures transactions.json is preserved.
        """
        sample_json_data = [
            {
                "transaction_id": "tx_json_001",
                "timestamp": "2026-11-04T01:00:00Z",
                "amount": "4.50",
                "recipient": "USB-C Cable",
                "status": "SUCCESS",
                "reason": "Payment executed successfully.",
                "balance_after": "95.50",
                "lifetime_spent_after": "4.50",
                "requires_human_approval": False,
                "human_approved": None,
                "agent_id": "BuyerBot",
                "attempt_number": 1,
            },
            {
                "transaction_id": "tx_json_002",
                "timestamp": "2026-11-04T01:05:00Z",
                "amount": "15.00",
                "recipient": "Bluetooth Headphones",
                "status": "REJECTED",
                "reason": "Declined by human reviewer.",
                "balance_after": "95.50",
                "lifetime_spent_after": "4.50",
                "requires_human_approval": True,
                "human_approved": False,
                "agent_id": "BuyerBot",
                "attempt_number": None,
            },
        ]

        with open(self.json_path, "w", encoding="utf-8") as f:
            json.dump(sample_json_data, f, indent=2)

        db = DatabaseManager(self.db_path)
        self.assertEqual(db.count_transactions(), 0)

        # Migrate from JSON
        imported_count = db.migrate_from_json(self.json_path)
        self.assertEqual(imported_count, 2)
        self.assertEqual(db.count_transactions(), 2)

        # Check records imported properly
        tx1 = db.get_transaction("tx_json_001")
        self.assertIsNotNone(tx1)
        self.assertEqual(tx1["amount_cents"], 450)
        self.assertEqual(tx1["status"], "SUCCESS")
        self.assertEqual(tx1["event_type"], config.EVENT_PAYMENT_SUCCESS)

        tx2 = db.get_transaction("tx_json_002")
        self.assertIsNotNone(tx2)
        self.assertEqual(tx2["amount_cents"], 1500)
        self.assertEqual(tx2["status"], "REJECTED")
        self.assertEqual(tx2["event_type"], config.EVENT_HUMAN_REJECTION)

        # Re-running migration must not create duplicates
        second_import = db.migrate_from_json(self.json_path)
        self.assertEqual(second_import, 0)
        self.assertEqual(db.count_transactions(), 2)

        # JSON file must still exist and not be deleted
        self.assertTrue(self.json_path.exists())

    def test_10_transaction_history_retrieves_records_correctly(self):
        """
        Scenario 10: Verifies filtering by status, event_type, search term, and ordering.
        """
        db = DatabaseManager(self.db_path)

        records = [
            {
                "transaction_id": "tx_hist_01",
                "request_id": "req_cable_01",
                "agent_id": "BuyerAgent1",
                "amount": 4.50,
                "description": "USB-C Cable",
                "status": config.STATUS_SUCCESS,
                "reason": "Success",
                "timestamp": "2026-11-04T01:00:00Z",
                "balance_after": 95.50,
                "event_type": config.EVENT_PAYMENT_SUCCESS,
            },
            {
                "transaction_id": "tx_hist_02",
                "request_id": "req_mouse_02",
                "agent_id": "BuyerAgent1",
                "amount": 8.00,
                "description": "Wireless Mouse",
                "status": config.STATUS_SUCCESS,
                "reason": "Success",
                "timestamp": "2026-11-04T02:00:00Z",
                "balance_after": 87.50,
                "event_type": config.EVENT_PAYMENT_SUCCESS,
            },
            {
                "transaction_id": "tx_hist_03",
                "request_id": "req_phones_03",
                "agent_id": "BuyerAgent2",
                "amount": 15.00,
                "description": "Noise-Cancelling Headphones",
                "status": config.STATUS_REJECTED,
                "reason": "Rejected by human",
                "timestamp": "2026-11-04T03:00:00Z",
                "balance_after": 87.50,
                "event_type": config.EVENT_HUMAN_REJECTION,
            },
            {
                "transaction_id": "tx_hist_04",
                "request_id": "req_rogue_04",
                "agent_id": "RunawayAgent",
                "amount": 4.50,
                "description": "USB-C Cable",
                "status": config.STATUS_BLOCKED,
                "reason": "Rate limit breached",
                "timestamp": "2026-11-04T04:00:00Z",
                "balance_after": 87.50,
                "event_type": config.EVENT_RUNAWAY_BLOCKED,
            },
        ]
        for r in records:
            db.insert_transaction(r)

        self.assertEqual(db.count_transactions(), 4)

        # Filter by status
        success_txs = db.get_all_transactions(status="SUCCESS")
        self.assertEqual(len(success_txs), 2)

        blocked_txs = db.get_all_transactions(status="BLOCKED")
        self.assertEqual(len(blocked_txs), 1)
        self.assertEqual(blocked_txs[0]["transaction_id"], "tx_hist_04")

        # Filter by event_type
        rej_txs = db.get_all_transactions(event_type=config.EVENT_HUMAN_REJECTION)
        self.assertEqual(len(rej_txs), 1)
        self.assertEqual(rej_txs[0]["transaction_id"], "tx_hist_03")

        # Search by description
        cable_txs = db.get_all_transactions(search="Cable")
        self.assertEqual(len(cable_txs), 2)

        # Search by request ID
        req_txs = db.get_all_transactions(search="req_phones_03")
        self.assertEqual(len(req_txs), 1)
        self.assertEqual(req_txs[0]["description"], "Noise-Cancelling Headphones")

        # Latest first ordering
        all_desc = db.get_all_transactions(latest_first=True)
        self.assertEqual(all_desc[0]["transaction_id"], "tx_hist_04")
        self.assertEqual(all_desc[-1]["transaction_id"], "tx_hist_01")

    def test_11_database_survives_application_restart(self):
        """
        Scenario 11: Verifies that creating a new DatabaseManager or SafeAgentWallet instance
        on an existing database file retains all previous transactions.
        """
        # Session 1: Create wallet, execute payments
        wallet1 = SafeAgentWallet(
            initial_balance=Decimal("100.00"),
            db_path=self.db_path,
            transactions_file=self.json_path,
        )
        res1 = wallet1.execute_payment(Decimal("4.50"), "USB-C Cable")
        res2 = wallet1.execute_payment(Decimal("8.00"), "Wireless Mouse")
        self.assertTrue(res1.success)
        self.assertTrue(res2.success)
        self.assertEqual(wallet1.balance, Decimal("87.50"))
        del wallet1

        # Session 2: Fresh instance pointing to the same db_path
        wallet2 = SafeAgentWallet(
            load_existing=True,
            db_path=self.db_path,
            transactions_file=self.json_path,
        )
        # History retrieved intact from database
        self.assertEqual(wallet2.db.count_transactions(), 2)
        history = wallet2.get_transaction_history()
        self.assertEqual(len(history), 2)
        tx_ids = [t["transaction_id"] for t in history]
        self.assertIn(res1.transaction_id, tx_ids)
        self.assertIn(res2.transaction_id, tx_ids)

    def test_12_existing_wallet_and_approval_tests_pass(self):
        """
        Scenario 12: End-to-end multi-agent purchase flow passes seamlessly with SQLite active.
        """
        wallet = SafeAgentWallet(
            initial_balance=Decimal("100.00"),
            db_path=self.db_path,
            transactions_file=self.json_path,
        )
        approval_center = ApprovalCenter()
        marketplace = Marketplace()
        buyer = BuyerAgent(
            marketplace=marketplace,
            wallet=wallet,
            approval_center=approval_center,
        )

        # 1. Automatic purchase ($4.50)
        res_auto = buyer.execute_purchase("buy a usb cable")
        self.assertTrue(res_auto.success)
        self.assertEqual(res_auto.status, "COMPLETED")
        self.assertEqual(wallet.balance, Decimal("95.50"))

        # 2. Purchase requiring human approval ($15.00)
        res_appr = buyer.execute_purchase("buy headphones")
        self.assertFalse(res_appr.success)
        self.assertTrue(res_appr.requires_human_approval)
        self.assertEqual(approval_center.get_pending_count(), 1)

        # 3. Human authorizes through ApprovalCenter
        pending_req = approval_center.get_pending_requests()[0]
        ok, msg, tx_res = approval_center.approve_request(
            request_id=pending_req.request_id,
            wallet=wallet,
            marketplace=marketplace,
            auth_token=config.DEFAULT_AUTH_TOKEN,
        )
        self.assertTrue(ok)
        self.assertEqual(wallet.balance, Decimal("80.50"))

        # 4. Check DB audit records
        # Contains: 1 auto payment + 1 unapproved attempt + 1 approved payment = 3 records
        all_txs = wallet.db.get_all_transactions()
        self.assertEqual(len(all_txs), 3)
        event_types = [t["event_type"] for t in all_txs]
        self.assertIn(config.EVENT_PAYMENT_SUCCESS, event_types)
        self.assertIn(config.EVENT_HUMAN_APPROVAL, event_types)


if __name__ == "__main__":
    unittest.main()
