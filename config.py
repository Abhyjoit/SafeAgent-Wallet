"""
config.py - SafeAgent Wallet Security Constants and Settings
CommitCon Hackathon

This module defines all security limits, financial thresholds, rate limits,
and file paths for SafeAgent Wallet.
"""

import os
from decimal import Decimal
from pathlib import Path

# Base Paths
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
TRANSACTIONS_FILE = DATA_DIR / "transactions.json"
DATABASE_FILE = DATA_DIR / "safeagent.db"

# Financial Rules & Limits
# Using Decimal to avoid floating-point rounding inaccuracies in financial calculations.
INITIAL_BALANCE = Decimal("100.00")
LIFETIME_SPENDING_LIMIT = Decimal("80.00")
AUTO_PAYMENT_THRESHOLD = Decimal("10.00")  # Inclusive: payments <= $10.00 are automatic

# Rate Limiting
# Maximum 3 payment requests allowed within any rolling 60-second window.
RATE_LIMIT_MAX_REQUESTS = 3
RATE_LIMIT_WINDOW_SECONDS = 60.0

# Human Authorization Protection
# Wallet locks permanently/until reset after 3 invalid authorization attempts.
MAX_INVALID_AUTH_ATTEMPTS = 3
# Set SAFEAGENT_AUTH_TOKEN in the environment. Never commit a real authorization secret.
DEFAULT_AUTH_TOKEN = os.getenv("SAFEAGENT_AUTH_TOKEN")

# Transaction Statuses
STATUS_SUCCESS = "SUCCESS"
STATUS_REJECTED = "REJECTED"
STATUS_PENDING = "PENDING"
STATUS_BLOCKED = "BLOCKED"

# Blocked & Security Reasons
REASON_RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
REASON_WALLET_LOCKED = "WALLET_LOCKED"

# Audit Log Event Types
EVENT_PAYMENT_SUCCESS = "PAYMENT_SUCCESS"
EVENT_HUMAN_APPROVAL = "HUMAN_APPROVAL"
EVENT_HUMAN_REJECTION = "HUMAN_REJECTION"
EVENT_PAYMENT_FAILED = "PAYMENT_FAILED"
EVENT_AUTH_FAILED = "AUTH_FAILED"
EVENT_RUNAWAY_BLOCKED = "RUNAWAY_BLOCKED"
EVENT_WALLET_LOCKED = "WALLET_LOCKED"
