"""
database.py - SQLite Database Management and Audit Log Storage
SafeAgent Wallet - CommitCon Hackathon (Hours 14–16)

This module provides persistent SQLite database storage for SafeAgent Wallet audit logs:
1. Thread-safe SQLite connection management and atomic operations.
2. Transactions table schema with integer cents monetary precision.
3. Parameterized queries protecting against SQL injection.
4. Comprehensive audit event persistence (payments, approvals, rejections, failures, runaway blocks).
5. Seamless migration from legacy JSON transaction logs without data loss.
"""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
import logging
from pathlib import Path
import sqlite3
import threading
from typing import Any, Dict, List, Optional, Tuple, Union

from config import (
    DATABASE_FILE,
    EVENT_AUTH_FAILED,
    EVENT_HUMAN_APPROVAL,
    EVENT_HUMAN_REJECTION,
    EVENT_PAYMENT_FAILED,
    EVENT_PAYMENT_SUCCESS,
    EVENT_RUNAWAY_BLOCKED,
    EVENT_WALLET_LOCKED,
    STATUS_BLOCKED,
    STATUS_REJECTED,
    STATUS_SUCCESS,
)

logger = logging.getLogger("SafeAgentDatabase")


def dollars_to_cents(amount: Any) -> int:
    """
    Converts a dollar amount (Decimal, float, str, int) to integer cents
    to prevent floating-point precision inaccuracies in SQLite.
    Example: $4.50 -> 450 cents; $100.00 -> 10000 cents.
    """
    if amount is None:
        return 0
    try:
        if isinstance(amount, int):
            # If value is already an integer, check if it's already cents vs dollars
            # Usually numbers like 15 mean $15 -> 1500 cents
            dec = Decimal(str(amount))
        elif isinstance(amount, float):
            dec = Decimal(str(amount))
        elif isinstance(amount, str):
            dec = Decimal(amount.strip() or "0")
        elif isinstance(amount, Decimal):
            dec = amount
        else:
            dec = Decimal(str(amount))

        return int((dec * Decimal(100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, TypeError, ValueError):
        return 0


def cents_to_dollars(cents: Union[int, None]) -> Decimal:
    """
    Converts integer cents to a 2-decimal-place quantized Decimal dollar amount.
    Example: 450 cents -> Decimal('4.50').
    """
    if cents is None:
        return Decimal("0.00")
    try:
        return (Decimal(cents) / Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0.00")


class DatabaseManager:
    """
    Thread-safe SQLite Database Manager for SafeAgent Wallet audit logs.
    """

    def __init__(self, db_path: Union[str, Path] = DATABASE_FILE):
        self.db_path = Path(db_path)
        self._lock = threading.RLock()

        # Ensure parent directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize schema
        self.init_db()

    def get_connection(self) -> sqlite3.Connection:
        """
        Creates and configures an SQLite database connection.
        Enables WAL mode and foreign keys for durability and concurrency.
        """
        conn = sqlite3.connect(
            str(self.db_path),
            timeout=30.0,
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        with conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA foreign_keys=ON;")
            conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def init_db(self) -> None:
        """
        Initializes the SQLite database tables and indexes if they do not exist.
        Schema stores monetary amounts as integer cents.
        """
        with self._lock:
            conn = self.get_connection()
            try:
                with conn:
                    conn.execute(
                        """
                        CREATE TABLE IF NOT EXISTS transactions (
                            transaction_id TEXT PRIMARY KEY,
                            request_id TEXT,
                            agent_id TEXT,
                            amount INTEGER NOT NULL DEFAULT 0,
                            description TEXT,
                            status TEXT NOT NULL,
                            reason TEXT,
                            timestamp TEXT NOT NULL,
                            balance_after INTEGER NOT NULL DEFAULT 0,
                            event_type TEXT NOT NULL,
                            lifetime_spent_after INTEGER DEFAULT 0,
                            attempt_number INTEGER
                        );
                        """
                    )
                    # Indexes for rapid query filtering and sorting
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_tx_timestamp ON transactions(timestamp);")
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_tx_status ON transactions(status);")
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_tx_event_type ON transactions(event_type);")
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_tx_agent_id ON transactions(agent_id);")
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_tx_request_id ON transactions(request_id);")
            finally:
                conn.close()

    def insert_transaction(self, tx_data: Dict[str, Any]) -> bool:
        """
        Inserts a single transaction event into the audit log using parameterized SQL.
        Strictly prevents duplicate transaction_ids by enforcing PRIMARY KEY constraint.

        Returns:
            True if inserted successfully, False if duplicate or failed.
        """
        tx_id = str(tx_data.get("transaction_id", "")).strip()
        if not tx_id:
            logger.error("Cannot insert transaction without transaction_id.")
            return False

        # Normalize amount & balance fields to integer cents
        raw_amt = tx_data.get("amount")
        amt_cents = raw_amt if isinstance(raw_amt, int) and "amount_cents" not in tx_data else dollars_to_cents(raw_amt)

        raw_bal = tx_data.get("balance_after")
        bal_cents = raw_bal if isinstance(raw_bal, int) and "balance_after_cents" not in tx_data else dollars_to_cents(raw_bal)

        raw_spent = tx_data.get("lifetime_spent_after")
        spent_cents = raw_spent if isinstance(raw_spent, int) and "lifetime_spent_cents" not in tx_data else dollars_to_cents(raw_spent)

        # Normalize status & event_type
        status = str(tx_data.get("status", STATUS_REJECTED)).upper()
        event_type = tx_data.get("event_type")
        if not event_type:
            if status == STATUS_SUCCESS:
                event_type = EVENT_PAYMENT_SUCCESS
            elif status == STATUS_BLOCKED:
                event_type = EVENT_RUNAWAY_BLOCKED
            elif tx_data.get("human_approved") is False:
                event_type = EVENT_HUMAN_REJECTION
            elif tx_data.get("human_approved") is True:
                event_type = EVENT_HUMAN_APPROVAL
            else:
                event_type = EVENT_PAYMENT_FAILED

        description = tx_data.get("description") or tx_data.get("recipient", "Unknown")
        timestamp = str(tx_data.get("timestamp", ""))

        with self._lock:
            conn = self.get_connection()
            try:
                with conn:
                    conn.execute(
                        """
                        INSERT INTO transactions (
                            transaction_id,
                            request_id,
                            agent_id,
                            amount,
                            description,
                            status,
                            reason,
                            timestamp,
                            balance_after,
                            event_type,
                            lifetime_spent_after,
                            attempt_number
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                        """,
                        (
                            tx_id,
                            tx_data.get("request_id"),
                            tx_data.get("agent_id"),
                            amt_cents,
                            description,
                            status,
                            tx_data.get("reason", ""),
                            timestamp,
                            bal_cents,
                            event_type,
                            spent_cents,
                            tx_data.get("attempt_number"),
                        ),
                    )
                return True
            except sqlite3.IntegrityError as e:
                logger.warning(f"Duplicate transaction_id '{tx_id}' rejected by database constraint: {e}")
                return False
            except Exception as e:
                logger.error(f"Database error inserting transaction '{tx_id}': {e}")
                raise
            finally:
                conn.close()

    def has_transaction_id(self, transaction_id: str) -> bool:
        """Checks if a transaction ID exists in the database."""
        if not transaction_id:
            return False
        with self._lock:
            conn = self.get_connection()
            try:
                cursor = conn.execute(
                    "SELECT 1 FROM transactions WHERE transaction_id = ? LIMIT 1;",
                    (transaction_id,),
                )
                return cursor.fetchone() is not None
            finally:
                conn.close()

    def get_transaction(self, transaction_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a single transaction by ID, returning values in both cents and formatted dollars."""
        if not transaction_id:
            return None
        with self._lock:
            conn = self.get_connection()
            try:
                cursor = conn.execute(
                    "SELECT * FROM transactions WHERE transaction_id = ? LIMIT 1;",
                    (transaction_id,),
                )
                row = cursor.fetchone()
                if not row:
                    return None
                return self._row_to_dict(row)
            finally:
                conn.close()

    def get_all_transactions(
        self,
        status: Optional[str] = None,
        event_type: Optional[str] = None,
        search: Optional[str] = None,
        limit: Optional[int] = None,
        latest_first: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Retrieves transactions with optional filtering and search.
        Uses parameterized SQL queries.
        """
        query = "SELECT * FROM transactions WHERE 1=1"
        params: List[Any] = []

        if status and status.upper() != "ALL":
            query += " AND status = ?"
            params.append(status.upper())

        if event_type and event_type.upper() != "ALL":
            query += " AND event_type = ?"
            params.append(event_type.upper())

        if search and search.strip():
            search_term = f"%{search.strip()}%"
            query += " AND (transaction_id LIKE ? OR request_id LIKE ? OR description LIKE ? OR agent_id LIKE ?)"
            params.extend([search_term, search_term, search_term, search_term])

        order_dir = "DESC" if latest_first else "ASC"
        query += f" ORDER BY timestamp {order_dir}, rowid {order_dir}"

        if limit is not None and limit > 0:
            query += " LIMIT ?"
            params.append(int(limit))

        with self._lock:
            conn = self.get_connection()
            try:
                cursor = conn.execute(query, tuple(params))
                return [self._row_to_dict(row) for row in cursor.fetchall()]
            finally:
                conn.close()

    def get_successful_transactions(self) -> List[Dict[str, Any]]:
        """Returns all successful payment transactions ordered chronologically."""
        return self.get_all_transactions(status=STATUS_SUCCESS, latest_first=False)

    def get_blocked_transactions(self) -> List[Dict[str, Any]]:
        """Returns all blocked runaway agent attempts ordered chronologically."""
        return self.get_all_transactions(status=STATUS_BLOCKED, latest_first=False)

    def count_transactions(self) -> int:
        """Returns total number of transactions recorded."""
        with self._lock:
            conn = self.get_connection()
            try:
                cursor = conn.execute("SELECT COUNT(*) FROM transactions;")
                return int(cursor.fetchone()[0])
            finally:
                conn.close()

    def clear(self) -> None:
        """Deletes all records from the transactions table."""
        with self._lock:
            conn = self.get_connection()
            try:
                with conn:
                    conn.execute("DELETE FROM transactions;")
            finally:
                conn.close()

    def migrate_from_json(self, json_file_path: Union[str, Path]) -> int:
        """
        Inspects legacy JSON transaction file and safely imports valid records into SQLite.
        - Avoids duplicate records by checking has_transaction_id.
        - Preserves all original transaction details.
        - Converts monetary strings to integer cents.
        - Does NOT delete the JSON file.

        Returns:
            Number of newly migrated transactions.
        """
        p = Path(json_file_path)
        if not p.exists() or p.stat().st_size == 0:
            return 0

        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Could not read JSON file '{p}' for migration: {e}")
            return 0

        if not isinstance(data, list):
            return 0

        migrated_count = 0
        with self._lock:
            for item in data:
                if not isinstance(item, dict):
                    continue
                tx_id = item.get("transaction_id")
                if not tx_id or self.has_transaction_id(tx_id):
                    continue

                try:
                    success = self.insert_transaction(item)
                    if success:
                        migrated_count += 1
                except Exception as e:
                    logger.warning(f"Error migrating record {tx_id}: {e}")

        logger.info(f"Successfully migrated {migrated_count} records from '{p}' to SQLite.")
        return migrated_count

    def _row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        """
        Converts an SQLite row to a standardized dictionary.
        Supplies both integer cents and formatted dollar string representations.
        """
        amt_cents = int(row["amount"] or 0)
        bal_cents = int(row["balance_after"] or 0)
        spent_cents = int(row["lifetime_spent_after"] or 0)

        amt_dollars = cents_to_dollars(amt_cents)
        bal_dollars = cents_to_dollars(bal_cents)
        spent_dollars = cents_to_dollars(spent_cents)

        return {
            "transaction_id": row["transaction_id"],
            "request_id": row["request_id"],
            "agent_id": row["agent_id"],
            "amount": f"{amt_dollars:.2f}",
            "amount_cents": amt_cents,
            "description": row["description"],
            "recipient": row["description"],  # Backwards compatibility alias
            "status": row["status"],
            "reason": row["reason"],
            "timestamp": row["timestamp"],
            "balance_after": f"{bal_dollars:.2f}",
            "balance_after_cents": bal_cents,
            "event_type": row["event_type"],
            "lifetime_spent_after": f"{spent_dollars:.2f}",
            "lifetime_spent_after_cents": spent_cents,
            "attempt_number": row["attempt_number"],
        }
