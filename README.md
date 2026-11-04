# SafeAgent Wallet 🛡️💳

**A Secure Autonomous Payment Gateway for AI Agents**  
Built for **CommitCon 24-Hour Hackathon**  
**Problem Statement #7:** *Stripe – Agents That Can Pay*

---

## 1. Project Overview & The Problem We Solve

As autonomous AI agents evolve from informational assistants into economic actors capable of purchasing compute, data, API credits, and goods, a fundamental security challenge arises:

> **How can autonomous agents pay for resources without risking catastrophic fund depletion, runaway loops, or unauthorized transactions?**

Giving an AI agent direct, unrestricted API keys to credit cards or treasury accounts is dangerous. Rogue loops, prompt injection, or logic bugs can drain balances in seconds.

**SafeAgent Wallet** solves this by inserting an active security governance layer between the AI agent and the payment settlement layer. Agents cannot execute financial transactions directly; every payment directive must flow through a deterministic policy engine that enforces budget bounds, rate limits, anti-tamper mechanisms, human authorization queues, and an immutable SQLite audit log.

---

## 2. How SafeAgent Wallet Works

SafeAgent Wallet operates a multi-agent marketplace with strict separation of privileges:

```
┌─────────────────┐       1. Purchase Intent        ┌────────────────────────┐
│      User       │ ──────────────────────────────> │   SafeAgent Buyer Bot  │
└─────────────────┘                                 └────────────────────────┘
                                                                 │
                                                    2. Catalog Search & Quote
                                                                 ▼
┌────────────────────────┐                          ┌────────────────────────┐
│ SafeAgent Approval Ctr │                          │ Simulated Marketplace  │
│ (Human in the Loop)    │                          │ (Seller Agents 1, 2, 3)│
└────────────────────────┘                          └────────────────────────┘
          ▲                                                      │
          │ 4. If > $10.00: Queue for Approval                   │ 3. Invoice Generated
          │    (Requires Cryptographic Token)                    ▼
          └──────────────────────────────────────── ┌────────────────────────┐
                                                    │    SafeAgent Wallet    │
                                                    │    Security Engine     │
                                                    └────────────────────────┘
                                                                 │
                                                    5. Policy Verification:
                                                       - Balance >= Amount
                                                       - Total Spent <= $80
                                                       - Rate Limit <= 3/60s
                                                       - Anti-Tamper Check
                                                                 ▼
                                                    ┌────────────────────────┐
                                                    │   data/safeagent.db    │
                                                    │  (SQLite Audit Ledger) │
                                                    └────────────────────────┘
```

1. **User Request:** The user issues a natural language purchase directive (e.g., *"Buy durable USB-C charging cable"*).
2. **Autonomous Negotiation:** The **Buyer Agent** searches the **Marketplace Catalog**, locates the matching product, and requests a formal invoice quote from the responsible **Seller Agent**.
3. **Privilege Separation:** Sellers never have wallet access; Buyer Agents cannot alter wallet balances directly. The Buyer Agent forwards the seller invoice to **SafeAgentWallet**.
4. **Policy Enforcement:** SafeAgentWallet evaluates:
   - **Amount & Balance Invariant:** Validates numeric values; guarantees balance never drops below $0.00.
   - **Automatic Threshold ($10.00):** Purchases $\le \$10.00$ execute automatically. Purchases $> \$10.00$ are intercepted and routed to the Human Approval Center.
   - **Lifetime Spending Limit ($80.00):** Absolute maximum cumulative allowance. Human approval cannot bypass this cap.
   - **Rolling 60-Second Rate Limiting:** Enforces a maximum of 3 payment requests per rolling 60-second window. A 4th rapid attempt instantly triggers an anti-runaway lockout.
   - **Anti-Tamper Lockout:** 3 invalid authorization attempts lock the wallet permanently until an administrator unlocks it.
5. **Immutable Audit Persistence:** Every success, human approval, human rejection, balance failure, and blocked attempt is written to an indexed SQLite ledger (`data/safeagent.db`) storing amounts with integer-cent monetary precision.

---

## 3. Main Implemented Features

- **Virtual Wallet with Initial $100.00 Balance:** Precision math using Python's `Decimal` module and SQLite integer-cent storage ($100.00 = 10000 cents) prevents floating-point rounding discrepancies.
- **Multi-Agent Marketplace:** Simulated Buyer Agent and 3 independent Seller Agents (Cables, Mouse, Audio) handling real quotes, availability checks, and price verification.
- **Dynamic Human Approval Center:** Interactive Streamlit dashboard enabling humans to review pending purchase requests, view order details, and authorize or reject transactions with full state-machine integrity.
- **Duplicate Payment Prevention:** Cryptographic UUID transaction IDs and database `PRIMARY KEY` constraints prevent double-click or replay vulnerabilities.
- **Runaway Agent Security Shield:** Rolling 60-second sliding time window detects rogue loops; automatically halts execution on attempt 4 and blocks attempts 5–10 with zero funds lost.
- **Anti-Tamper Lockout & Isolation:** 3 invalid authorization attempts trigger a security lock. Normal human rejections strictly do *not* count against the invalid auth counter.
- **SQLite Audit Log & UI Ledger:** Complete transaction history querying `data/safeagent.db` with live filters by Status, Event Type (`PAYMENT_SUCCESS`, `HUMAN_APPROVAL`, `HUMAN_REJECTION`, `RUNAWAY_BLOCKED`, etc.), and search.
- **Modern Fintech UI:** Dark-mode glassmorphic interface inspired by modern fintech security dashboards with live balance cards, trace logs, and an interactive Runaway Agent Simulator.

---

## 4. Technology Stack

- **Core Language:** Python 3.10+ (tested on Python 3.14)
- **UI & Dashboard:** Streamlit 1.40+
- **Persistence Layer:** SQLite3 with WAL (Write-Ahead Logging) mode and thread-safe connection pooling
- **Testing Frameworks:** `pytest`, `pytest-cov`, `unittest`
- **Standard Libraries:** `decimal` (financial math), `threading` (thread-safety), `uuid` (unique IDs)

---

## 5. Project Folder Structure

```
SafeAgent-Wallet/
├── .gitignore                   # Excludes .venv, cache, coverage, and temp files
├── LICENSE                      # MIT Open Source License (2026 Abhyjoit Singh)
├── README.md                    # Project documentation, architecture, and setup guide
├── app.py                       # Modern fintech Streamlit dashboard UI
├── buyer_agent.py               # Autonomous Buyer Agent logic & negotiation pipeline
├── config.py                    # Global financial limits, thresholds, and event constants
├── database.py                  # Thread-safe SQLite manager & integer-cent conversions
├── marketplace.py               # Marketplace catalog, products, and search indexing
├── purchase.py                  # Purchase orders, Seller responses, and Approval Center
├── requirements.txt             # Clean third-party dependency manifest
├── security.py                  # Rolling-window rate limiter & anti-tamper authorization
├── seller_agent.py              # Vendor agents generating quotes and invoices
├── transactions.py              # Dual-persistence transaction manager
├── wallet.py                    # SafeAgentWallet core security state machine
├── pytest.ini                   # Pytest testpath & discovery configuration
├── data/
│   ├── safeagent.db             # Persistent SQLite audit database
│   └── transactions.json        # Backward-compatible JSON transaction sync
└── tests/                       # Modular Pytest test suite
    ├── __init__.py
    ├── conftest.py              # Shared fixtures & deterministic MockClock
    ├── test_approval.py         # Human Approval Center & double-approval tests
    ├── test_database.py         # SQLite schema, index, event type, & migration tests
    ├── test_purchases.py        # Multi-agent purchase, search, & mismatch tests
    ├── test_rate_limiter.py     # Rolling 60s rate limiter & runaway attack tests
    ├── test_security.py         # Anti-tamper 3-strike lockout & bypass prevention tests
    └── test_wallet.py           # Core wallet, spending limit, & boundary tests
```

---

## 6. Installation Instructions

### Prerequisites
- Python 3.10 or higher
- Git

### macOS & Linux
```bash
# 1. Clone repository
git clone https://github.com/Abhyjoit/SafeAgent-Wallet.git
cd SafeAgent-Wallet

# 2. Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install required dependencies
pip install -r requirements.txt
```

### Windows (PowerShell)
```powershell
# 1. Clone repository
git clone https://github.com/Abhyjoit/SafeAgent-Wallet.git
cd SafeAgent-Wallet

# 2. Create and activate virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1

# 3. Install required dependencies
pip install -r requirements.txt
```

---

## 7. How to Run the Application

Launch the Streamlit fintech dashboard:

```bash
streamlit run app.py
```

The application will open in your browser at `http://localhost:8501`.

---

## 8. How to Run the Tests

SafeAgent Wallet includes dual testing support (both `pytest` and `unittest`):

### Run Pytest Suite
```bash
pytest -v
```

### Run Coverage Analysis
```bash
pytest --cov=. --cov-report=term-missing
```

### Run Regression Unittest Suite
```bash
python -m unittest discover -v
```

---

## 9. Example Walkthrough

### Scenario A: Automatic Small Purchase ($\le \$10.00$)
1. Navigate to the **Marketplace** tab in the sidebar.
2. Select **USB-C Cable ($4.50)** or enter *"Buy USB-C cable"* in the Buyer Agent bar.
3. The Buyer Agent requests a quote, verifies price consistency, and submits the invoice to the wallet.
4. Because $\$4.50 \le \$10.00$, the transaction **executes automatically**:
   - Wallet balance updates: $\$100.00 \rightarrow \$95.50$.
   - Transaction is logged in the SQLite audit ledger with event `PAYMENT_SUCCESS`.

### Scenario B: High-Value Purchase Requiring Human Approval ($> \$10.00$)
1. Select **Bluetooth Headphones ($15.00)**.
2. The Buyer Agent contacts the seller and receives invoice `#ord_audio_...`.
3. SafeAgentWallet detects $\$15.00 > \$10.00$ auto-threshold:
   - Payment is intercepted; **$0.00 is deducted**.
   - An approval request is enqueued in the **Human Approval Center**.
4. Open the **Approval Center** in the sidebar.
5. Review the invoice, buyer agent identity, and reason.
6. Click **Approve Transaction**:
   - The human authorization credential token (`COMMITCON-SECURE-2026`) is verified.
   - Wallet executes the payment: $\$95.50 \rightarrow \$80.50$.
   - Event `HUMAN_APPROVAL` is permanently recorded in `safeagent.db`.

### Scenario C: Rogue Runaway Agent Attack Simulation
1. Click **🚨 Simulate Runaway Agent Attack** on the dashboard.
2. The agent attempts 10 purchases of $\$4.50$ in rapid succession:
   - **Attempts 1–3:** Allowed ($\$13.50$ deducted).
   - **Attempt 4:** Rate limit breached ($>3$ requests per 60s); wallet **automatically locks**.
   - **Attempts 5–10:** Instantly blocked by the locked wallet. **$0.00 deducted**.
   - A high-priority **Runaway Agent Alert** appears on the dashboard.

---

## 10. Security Limitations

> [!IMPORTANT]
> **Simulated Hackathon Prototype:**  
> SafeAgent Wallet is an architectural reference and working prototype created for the CommitCon Hackathon.
> - **Virtual Funds:** All balances and currencies are simulated and do not represent real fiat or cryptocurrency.
> - **No Real Banking Settlement:** It does not bind to live Stripe live-mode credentials, banks, or card payment rails.
> - **Production Deployment:** For production deployments, this architecture should be paired with secure Stripe Issuing / Financial Connections APIs, mutual TLS (mTLS), and hardware security modules (HSM) for authorization tokens.

---

## 11. Team Members & Attribution

- **Abhyjoit Singh** ([GitHub: @Abhyjoit](https://github.com/Abhyjoit)) — Lead Architecture, Multi-Agent Marketplace, Security State Machine, and Dashboard UI.

---

## 12. License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.
