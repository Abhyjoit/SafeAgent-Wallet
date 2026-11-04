"""
conftest.py - Pytest fixtures and shared testing utilities
SafeAgent Wallet - CommitCon Hackathon (Hour 16–18)
"""

from decimal import Decimal
import os
from pathlib import Path
import sys
import tempfile
import time
from typing import Dict, Generator

import pytest

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from buyer_agent import BuyerAgent
import config
from database import DatabaseManager
from marketplace import Marketplace
from purchase import ApprovalCenter
from seller_agent import SellerAgent, create_default_sellers
from wallet import SafeAgentWallet


class MockClock:
    """
    Deterministic controllable clock for testing rolling rate limiters
    and time-sensitive security rules without sleep-based delays.
    """

    def __init__(self, start_time: float = 1700000000.0):
        self._current_time = float(start_time)

    def time(self) -> float:
        return self._current_time

    def advance(self, seconds: float) -> float:
        self._current_time += float(seconds)
        return self._current_time

    def set_time(self, timestamp: float) -> None:
        self._current_time = float(timestamp)

    def __call__(self) -> float:
        return self._current_time


@pytest.fixture
def mock_clock() -> MockClock:
    """Provides a deterministic mock clock."""
    return MockClock()


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Provides an isolated temporary directory for test artifacts."""
    with tempfile.TemporaryDirectory() as td:
        yield Path(td)


@pytest.fixture
def temp_db_path(temp_dir: Path) -> Path:
    """Provides a temporary SQLite database path."""
    return temp_dir / "test_safeagent.db"


@pytest.fixture
def temp_json_path(temp_dir: Path) -> Path:
    """Provides a temporary transactions JSON path."""
    return temp_dir / "test_transactions.json"


@pytest.fixture
def db_manager(temp_db_path: Path) -> DatabaseManager:
    """Provides an initialized SQLite DatabaseManager on a temporary database."""
    return DatabaseManager(temp_db_path)


@pytest.fixture
def wallet(temp_db_path: Path, temp_json_path: Path) -> SafeAgentWallet:
    """
    Provides a clean SafeAgentWallet initialized with:
    - $100.00 initial balance
    - $80.00 lifetime spending limit
    - $10.00 automatic payment threshold
    - Isolated temporary SQLite and JSON storage
    """
    return SafeAgentWallet(
        initial_balance=Decimal("100.00"),
        db_path=temp_db_path,
        transactions_file=temp_json_path,
        load_existing=False,
    )


@pytest.fixture
def marketplace() -> Marketplace:
    """Provides an initialized simulated marketplace with default products."""
    return Marketplace()


@pytest.fixture
def sellers() -> Dict[str, SellerAgent]:
    """Provides default simulated seller agents."""
    return create_default_sellers()


@pytest.fixture
def approval_center() -> ApprovalCenter:
    """Provides a clean Human Approval Center."""
    return ApprovalCenter()


@pytest.fixture
def buyer_agent(
    marketplace: Marketplace,
    wallet: SafeAgentWallet,
    sellers: Dict[str, SellerAgent],
    approval_center: ApprovalCenter,
) -> BuyerAgent:
    """Provides an initialized BuyerAgent connected to all marketplace subsystems."""
    return BuyerAgent(
        marketplace=marketplace,
        wallet=wallet,
        sellers=sellers,
        approval_center=approval_center,
    )
