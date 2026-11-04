"""
transactions.py - Transaction Logging and SQLite / JSON Persistence
SafeAgent Wallet - CommitCon Hackathon (Hours 14–16)

This module records all payment transactions and audit events:
- Persists primarily to persistent SQLite database (data/safeagent.db).
- Maintains synchronized JSON file backups for backwards compatibility.
- Seamlessly migrates existing legacy JSON records without data loss.
"""

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import threading
from typing import Any, Dict, List, Optional, Union

from config import (
    DATABASE_FILE,
    EVENT_AUTH_FAILED,
    EVENT_HUMAN_APPROVAL,
    EVENT_HUMAN_REJECTION,
    EVENT_PAYMENT_FAILED,
    EVENT_PAYMENT_SUCCESS,
    EVENT_RUNAWAY_BLOCKED,
    STATUS_BLOCKED,
    STATUS_REJECTED,
    STATUS_SUCCESS,
    TRANSACTIONS_FILE,
)
from database import DatabaseManager, cents_to_dollars, dollars_to_cents


@dataclass
class Transaction:
    """Represents a single payment transaction or audit event record."""

    transaction_id: str
    timestamp: str
    amount: str
    recipient: str
    status: str  # SUCCESS, REJECTED, or BLOCKED
    reason: str
    balance_after: str
    lifetime_spent_after: str
    requires_human_approval: bool
    human_approved: Optional[bool] = None
    agent_id: Optional[str] = None
    attempt_number: Optional[int] = None
    request_id: Optional[str] = None
    event_type: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert transaction to a JSON/SQLite-serializable dictionary."""
        d = asdict(self)
        d["description"] = self.recipient
        d["amount_cents"] = dollars_to_cents(self.amount)
        d["balance_after_cents"] = dollars_to_cents(self.balance_after)
        d["lifetime_spent_cents"] = dollars_to_cents(self.lifetime_spent_after)
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Transaction":
        """Reconstruct Transaction instance from dictionary (supporting either cents or dollar formats)."""
        amt = data.get("amount", "0.00")
        if isinstance(amt, int) and "amount_cents" not in data and not isinstance(data.get("amount"), str):
            amt_str = f"{cents_to_dollars(amt):.2f}"
        else:
            amt_str = str(amt)

        bal = data.get("balance_after", "0.00")
        if isinstance(bal, int) and not isinstance(data.get("balance_after"), str):
            bal_str = f"{cents_to_dollars(bal):.2f}"
        else:
            bal_str = str(bal)

        spent = data.get("lifetime_spent_after", "0.00")
        if isinstance(spent, int) and not isinstance(data.get("lifetime_spent_after"), str):
            spent_str = f"{cents_to_dollars(spent):.2f}"
        else:
            spent_str = str(spent)

        recip = data.get("description") or data.get("recipient", "Unknown")
        st = str(data.get("status", STATUS_REJECTED)).upper()
        evt = data.get("event_type")
        if not evt:
            if st == STATUS_SUCCESS:
                evt = EVENT_PAYMENT_SUCCESS
            elif st == STATUS_BLOCKED:
                evt = EVENT_RUNAWAY_BLOCKED
            elif data.get("human_approved") is False:
                evt = EVENT_HUMAN_REJECTION
            elif data.get("human_approved") is True:
                evt = EVENT_HUMAN_APPROVAL
            else:
                evt = EVENT_PAYMENT_FAILED

        return cls(
            transaction_id=str(data.get("transaction_id", "")),
            timestamp=str(data.get("timestamp", "")),
            amount=amt_str,
            recipient=str(recip),
            status=st,
            reason=str(data.get("reason", "")),
            balance_after=bal_str,
            lifetime_spent_after=spent_str,
            requires_human_approval=bool(data.get("requires_human_approval", False)),
            human_approved=data.get("human_approved"),
            agent_id=data.get("agent_id"),
            attempt_number=data.get("attempt_number"),
            request_id=data.get("request_id"),
            event_type=evt,
        )


class TransactionManager:
    """
    Manages transaction logs using SQLite as the primary durable storage engine,
    with synchronized JSON persistence for backwards compatibility.
    Thread-safe and ACID compliant.
    """

    def __init__(
        self,
        file_path: Union[str, Path] = TRANSACTIONS_FILE,
        db_path: Optional[Union[str, Path]] = None,
    ):
        self.file_path = Path(file_path)
        self._lock = threading.RLock()
        self._transactions: List[Transaction] = []
        self._transaction_ids: set[str] = set()

        # Determine appropriate SQLite database path
        if db_path is not None:
            self.db_path = Path(db_path)
        elif self.file_path == TRANSACTIONS_FILE:
            self.db_path = DATABASE_FILE
        else:
            # When tests specify an isolated temp transactions file, place the SQLite DB in the same temp directory
            self.db_path = self.file_path.with_suffix(".db")

        # Ensure parent directories exist
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize SQLite database manager
        self.db = DatabaseManager(db_path=self.db_path)

        # Auto-migrate existing JSON transactions into SQLite if any exist
        if self.file_path.exists() and self.file_path.stat().st_size > 0:
            self.db.migrate_from_json(self.file_path)

        # Load transactions into memory
        self.load_transactions()

    def load_transactions(self) -> List[Transaction]:
        """
        Loads transaction records from SQLite database into memory cache.
        Also ensures JSON file reflects current database state.
        """
        with self._lock:
            self._transactions.clear()
            self._transaction_ids.clear()

            db_records = self.db.get_all_transactions(latest_first=False)
            for row in db_records:
                tx = Transaction.from_dict(row)
                self._transactions.append(tx)
                self._transaction_ids.add(tx.transaction_id)

            # Keep JSON file in sync
            self._sync_to_file()
            return list(self._transactions)

    def _sync_to_file(self) -> None:
        """Writes current transactions to JSON file atomically."""
        serialized = [t.to_dict() for t in self._transactions]
        temp_file = self.file_path.with_suffix(".tmp")
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(serialized, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_file, self.file_path)
        except OSError:
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except OSError:
                    pass

    def record_transaction(self, tx: Transaction) -> Transaction:
        """
        Persists a transaction into SQLite database and synchronizes JSON file.
        Strictly prevents duplicates.
        """
        with self._lock:
            # 1. Insert into SQLite
            tx_dict = tx.to_dict()
            self.db.insert_transaction(tx_dict)

            # 2. Append to memory cache and JSON file
            if tx.transaction_id not in self._transaction_ids:
                self._transactions.append(tx)
                self._transaction_ids.add(tx.transaction_id)
                self._sync_to_file()

            return tx

    def has_transaction_id(self, transaction_id: str) -> bool:
        """Checks if a transaction ID has already been recorded."""
        with self._lock:
            if transaction_id in self._transaction_ids:
                return True
            return self.db.has_transaction_id(transaction_id)

    def get_transaction(self, transaction_id: str) -> Optional[Transaction]:
        """Finds a transaction by ID."""
        with self._lock:
            for tx in self._transactions:
                if tx.transaction_id == transaction_id:
                    return tx
            db_row = self.db.get_transaction(transaction_id)
            if db_row:
                return Transaction.from_dict(db_row)
            return None

    def get_all_transactions(self) -> List[Transaction]:
        """Returns a copy of all recorded transactions."""
        with self._lock:
            return list(self._transactions)

    def get_successful_transactions(self) -> List[Transaction]:
        """Returns all successful transactions."""
        with self._lock:
            return [tx for tx in self._transactions if tx.status == STATUS_SUCCESS]

    def get_rejected_transactions(self) -> List[Transaction]:
        """Returns all rejected transactions."""
        with self._lock:
            return [tx for tx in self._transactions if tx.status == STATUS_REJECTED]

    def get_blocked_transactions(self) -> List[Transaction]:
        """Returns all blocked runaway agent transactions."""
        with self._lock:
            return [tx for tx in self._transactions if tx.status == STATUS_BLOCKED]

    def clear(self) -> None:
        """Clears all transactions in SQLite database, memory, and JSON file."""
        with self._lock:
            self.db.clear()
            self._transactions.clear()
            self._transaction_ids.clear()
            self._sync_to_file()
