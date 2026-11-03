"""
transactions.py - Transaction Logging and JSON Persistence
SafeAgent Wallet - CommitCon Hackathon

This module records all payment transactions (both successful and rejected)
and persists them safely to a JSON file on disk.
"""

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import threading
from typing import Any, Dict, List, Optional

from config import STATUS_REJECTED, STATUS_SUCCESS, TRANSACTIONS_FILE


@dataclass
class Transaction:
    """Represents a single payment transaction record."""

    transaction_id: str
    timestamp: str
    amount: str
    recipient: str
    status: str  # SUCCESS or REJECTED
    reason: str
    balance_after: str
    lifetime_spent_after: str
    requires_human_approval: bool
    human_approved: Optional[bool] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert transaction to a JSON-serializable dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Transaction":
        """Reconstruct Transaction instance from dictionary."""
        return cls(
            transaction_id=str(data.get("transaction_id", "")),
            timestamp=str(data.get("timestamp", "")),
            amount=str(data.get("amount", "0.00")),
            recipient=str(data.get("recipient", "Unknown")),
            status=str(data.get("status", STATUS_REJECTED)),
            reason=str(data.get("reason", "")),
            balance_after=str(data.get("balance_after", "0.00")),
            lifetime_spent_after=str(data.get("lifetime_spent_after", "0.00")),
            requires_human_approval=bool(data.get("requires_human_approval", False)),
            human_approved=data.get("human_approved"),
        )


class TransactionManager:
    """
    Manages in-memory transaction logs and persists them to JSON file storage.
    Thread-safe and atomic file updates prevent data corruption.
    """

    def __init__(self, file_path: Path = TRANSACTIONS_FILE):
        self.file_path = Path(file_path)
        self._lock = threading.Lock()
        self._transactions: List[Transaction] = []
        self._transaction_ids: set[str] = set()

        # Ensure parent directory exists
        self.file_path.parent.mkdir(parents=True, exist_ok=True)

        # Load existing transactions or initialize storage
        self.load_transactions()

    def load_transactions(self) -> List[Transaction]:
        """
        Safely loads transaction records from the JSON file.
        If file is missing or empty, initializes with an empty list.
        """
        with self._lock:
            self._transactions.clear()
            self._transaction_ids.clear()

            if not self.file_path.exists() or self.file_path.stat().st_size == 0:
                self._save_to_file([])
                return []

            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        for item in data:
                            tx = Transaction.from_dict(item)
                            self._transactions.append(tx)
                            self._transaction_ids.add(tx.transaction_id)
            except (json.JSONDecodeError, OSError):
                # If file is corrupted or empty, initialize clean list
                self._transactions = []
                self._transaction_ids = set()
                self._save_to_file([])

            return list(self._transactions)

    def _save_to_file(self, data: List[Dict[str, Any]]) -> None:
        """
        Writes JSON data atomically using a temporary file to avoid corruption.
        """
        temp_file = self.file_path.with_suffix(".tmp")
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_file, self.file_path)
        except OSError:
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except OSError:
                    pass
            raise

    def record_transaction(self, tx: Transaction) -> Transaction:
        """
        Appends a transaction to history and persists to JSON.
        """
        with self._lock:
            self._transactions.append(tx)
            self._transaction_ids.add(tx.transaction_id)
            serialized = [t.to_dict() for t in self._transactions]
            self._save_to_file(serialized)
            return tx

    def has_transaction_id(self, transaction_id: str) -> bool:
        """Checks if a transaction ID has already been recorded."""
        with self._lock:
            return transaction_id in self._transaction_ids

    def get_transaction(self, transaction_id: str) -> Optional[Transaction]:
        """Finds a transaction by ID."""
        with self._lock:
            for tx in self._transactions:
                if tx.transaction_id == transaction_id:
                    return tx
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

    def clear(self) -> None:
        """Clears all transactions in memory and resets the JSON file."""
        with self._lock:
            self._transactions.clear()
            self._transaction_ids.clear()
            self._save_to_file([])
