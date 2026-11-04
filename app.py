"""
app.py - SafeAgent Wallet
CommitCon 24-Hour Hackathon - Problem Statement #7: Stripe – Agents That Can Pay

Multi-Page Professional Fintech Security Dashboard:
- Overview: Core balances, recent activity, system telemetry, and quick actions.
- Wallet: Financial invariants, direct payment controls, catalog purchases, and resets.
- Agent Activity: Autonomous Buyer Agent order negotiations, multi-agent traces, and seller catalog.
- Approvals: Human-in-the-loop review center for transactions > $10.00 with inline confirmation.
- Security Center: Rate limiting, runaway agent simulator, threat mitigation, and lock management.
- Transactions: Operational transaction ledger with status filtering and live search.
- Audit Logs: Database-backed immutable event ledger in SQLite with integer-cent precision.
- Settings: Global financial rules, security policies, database health, and system metadata.
"""

from decimal import Decimal
import html
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st

from buyer_agent import BuyerAgent
import config
from database import DatabaseManager, cents_to_dollars, dollars_to_cents
from marketplace import Marketplace, Product
from purchase import (
    AgentTraceStep,
    ApprovalCenter,
    ApprovalRequest,
    PurchaseFlowResult,
)
from seller_agent import SellerAgent, create_default_sellers
from wallet import PaymentResult, SafeAgentWallet

# =============================================================================
# 1. PAGE CONFIGURATION & FINTECH DESIGN THEME
# =============================================================================

st.set_page_config(
    page_title="SafeAgent Wallet — Security Dashboard",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Professional Fintech Light CSS Theme
st.markdown(
    """
    <style>
    /* Global Background and Typography */
    .stApp {
        background-color: #F8FAFC;
        color: #0F172A;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }

    /* Sidebar Styling */
    [data-testid="stSidebar"] {
        background-color: #FFFFFF;
        border-right: 1px solid #E2E8F0;
    }
    
    [data-testid="stSidebar"] hr {
        margin: 12px 0;
        border-color: #E2E8F0;
    }

    /* Fintech Card Container */
    .fintech-card {
        background-color: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 8px;
        padding: 20px 24px;
        margin-bottom: 20px;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.03);
    }
    
    .fintech-card-header {
        font-size: 1rem;
        font-weight: 600;
        color: #0F172A;
        margin-bottom: 12px;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }

    /* Metric Boxes */
    .metric-box {
        background-color: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 8px;
        padding: 16px 18px;
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.02);
        margin-bottom: 12px;
    }
    .metric-box-label {
        font-size: 0.75rem;
        font-weight: 600;
        color: #64748B;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 4px;
    }
    .metric-box-value {
        font-size: 1.55rem;
        font-weight: 700;
        color: #0F172A;
        line-height: 1.2;
    }
    .metric-box-sub {
        font-size: 0.75rem;
        color: #64748B;
        margin-top: 4px;
    }

    /* Status Pills */
    .status-pill {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 9999px;
        font-size: 0.75rem;
        font-weight: 600;
        line-height: 1.4;
    }
    .status-pill-success {
        background-color: #DCFCE7;
        color: #15803D;
        border: 1px solid #BBF7D0;
    }
    .status-pill-warning {
        background-color: #FEF3C7;
        color: #B45309;
        border: 1px solid #FDE68A;
    }
    .status-pill-danger {
        background-color: #FEE2E2;
        color: #B91C1C;
        border: 1px solid #FECACA;
    }
    .status-pill-neutral {
        background-color: #F1F5F9;
        color: #475569;
        border: 1px solid #E2E8F0;
    }

    /* Notice Banners */
    .notice-banner-danger {
        background-color: #FEF2F2;
        border-left: 4px solid #DC2626;
        border-radius: 0 6px 6px 0;
        padding: 12px 16px;
        color: #991B1B;
        font-size: 0.88rem;
        margin-bottom: 16px;
    }
    .notice-banner-warning {
        background-color: #FFFBEB;
        border-left: 4px solid #D97706;
        border-radius: 0 6px 6px 0;
        padding: 12px 16px;
        color: #92400E;
        font-size: 0.88rem;
        margin-bottom: 16px;
    }
    .notice-banner-success {
        background-color: #F0FDF4;
        border-left: 4px solid #16A34A;
        border-radius: 0 6px 6px 0;
        padding: 12px 16px;
        color: #166534;
        font-size: 0.88rem;
        margin-bottom: 16px;
    }

    /* Product Grid Card */
    .product-grid-card {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 8px;
        padding: 16px;
        margin-bottom: 12px;
        min-height: 180px;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.02);
    }
    .product-grid-title {
        font-size: 0.95rem;
        font-weight: 600;
        color: #0F172A;
    }
    .product-grid-desc {
        font-size: 0.8rem;
        color: #64748B;
        margin: 4px 0 8px 0;
    }
    .product-grid-price {
        font-size: 1.15rem;
        font-weight: 700;
        color: #0F172A;
    }

    /* Clean Empty State Box */
    .empty-state-box {
        background-color: #FFFFFF;
        border: 1px dashed #CBD5E1;
        border-radius: 8px;
        padding: 36px 20px;
        text-align: center;
        margin: 16px 0;
    }
    .empty-state-title {
        font-size: 1rem;
        font-weight: 600;
        color: #334155;
        margin-bottom: 4px;
    }
    .empty-state-desc {
        font-size: 0.82rem;
        color: #64748B;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# =============================================================================
# 2. SESSION STATE INITIALIZATION
# =============================================================================

if "wallet" not in st.session_state:
    st.session_state.wallet = SafeAgentWallet(load_existing=True)

if "marketplace" not in st.session_state:
    st.session_state.marketplace = Marketplace()

if "sellers" not in st.session_state:
    st.session_state.sellers = create_default_sellers()

if "approval_center" not in st.session_state:
    st.session_state.approval_center = ApprovalCenter()

if "buyer_agent" not in st.session_state:
    st.session_state.buyer_agent = BuyerAgent(
        marketplace=st.session_state.marketplace,
        wallet=st.session_state.wallet,
        sellers=st.session_state.sellers,
        approval_center=st.session_state.approval_center,
    )

if "last_agent_result" not in st.session_state:
    st.session_state.last_agent_result = None

if "simulation_results" not in st.session_state:
    st.session_state.simulation_results = None

if "action_notice" not in st.session_state:
    st.session_state.action_notice = None

if "agent_history" not in st.session_state:
    st.session_state.agent_history = []

# Active references
wallet: SafeAgentWallet = st.session_state.wallet
marketplace: Marketplace = st.session_state.marketplace
sellers: Dict[str, SellerAgent] = st.session_state.sellers
approval_center: ApprovalCenter = st.session_state.approval_center
buyer_agent: BuyerAgent = st.session_state.buyer_agent


# =============================================================================
# 3. ACTION HANDLERS
# =============================================================================

def set_notice(level: str, text: str) -> None:
    """Sets a global notification message."""
    st.session_state.action_notice = (level, text)


def render_notice() -> None:
    """Renders any queued notification banner."""
    if st.session_state.action_notice:
        level, text = st.session_state.action_notice
        if level == "success":
            st.markdown(f'<div class="notice-banner-success">{html.escape(text)}</div>', unsafe_allow_html=True)
        elif level == "warning":
            st.markdown(f'<div class="notice-banner-warning">{html.escape(text)}</div>', unsafe_allow_html=True)
        elif level == "danger":
            st.markdown(f'<div class="notice-banner-danger">{html.escape(text)}</div>', unsafe_allow_html=True)
        st.session_state.action_notice = None


def handle_purchase_directive(query_text: str) -> None:
    """Dispatches a natural-language purchase directive through Buyer Agent."""
    if not query_text or not query_text.strip():
        return
    res: PurchaseFlowResult = buyer_agent.execute_purchase(query_text.strip())
    st.session_state.last_agent_result = res
    st.session_state.agent_history.insert(0, {
        "query": query_text.strip(),
        "status": res.status,
        "product_name": res.product.name if res.product else "None",
        "price": f"${res.product.price:.2f}" if res.product else "—",
        "seller": res.product.seller_id if res.product else "—",
        "order_id": res.order_id or "—",
        "summary": res.summary_message,
    })

    if res.status == "COMPLETED":
        set_notice("success", f"Purchase completed: {res.summary_message}")
    elif res.status == "AWAITING_APPROVAL":
        set_notice("warning", f"Human approval required: Order queued in Approvals ({res.summary_message})")
    elif res.status == "NOT_FOUND":
        set_notice("warning", f"Catalog search: {res.summary_message}")
    else:
        set_notice("danger", f"Purchase stopped: {res.summary_message}")


def handle_approve(request_id: str, auth_token: str) -> None:
    """Executes a human approval on a pending request."""
    if not auth_token or not auth_token.strip():
        set_notice("danger", "Authorization failed: A valid authorization credential token is required.")
        return

    ok, msg, wallet_res = approval_center.approve_request(
        request_id=request_id,
        wallet=wallet,
        marketplace=marketplace,
        auth_token=auth_token.strip(),
    )
    if ok and wallet_res:
        set_notice(
            "success",
            f"Payment Authorized: Transaction {wallet_res.transaction_id} executed. "
            f"Deducted ${wallet_res.amount:.2f}. Remaining balance: ${wallet_res.balance:.2f}."
        )
    else:
        set_notice("danger", f"Authorization Rejected: {msg}")


def handle_reject(request_id: str, reason: str) -> None:
    """Rejects a pending approval request."""
    ok, msg = approval_center.reject_request(
        request_id=request_id,
        wallet=wallet,
        reason=reason.strip() or "Declined by human reviewer.",
    )
    if ok:
        set_notice("success", f"Request Rejected: {msg}")
    else:
        set_notice("danger", f"Rejection Error: {msg}")


def handle_runaway_sim() -> None:
    """Executes the controlled 10-attempt runaway agent attack simulation."""
    results = wallet.simulate_runaway_agent_attack(
        attempts=10,
        amount=Decimal("4.50"),
        recipient="USB-C Cable (CableCraft Direct)",
        agent_id="SafeAgent Buyer Bot v1.0",
    )
    st.session_state.simulation_results = results
    set_notice(
        "danger",
        "Runaway Agent Simulation Executed: 10 rapid attempts generated. "
        "Attempts 1–3 allowed, Attempt 4 rate-limited (Auto-Locked), Attempts 5–10 blocked with $0 lost."
    )


def handle_reset_all() -> None:
    """Resets wallet, marketplace, approvals, and transaction logs."""
    wallet.reset()
    marketplace.reset_catalog()
    approval_center.clear()
    st.session_state.last_agent_result = None
    st.session_state.simulation_results = None
    st.session_state.agent_history.clear()
    set_notice("success", "Wallet and marketplace state reset to $100.00 initial balance.")


# =============================================================================
# 4. SIDEBAR NAVIGATION & SYSTEM TELEMETRY
# =============================================================================

with st.sidebar:
    st.markdown(
        """
        <div style="padding: 4px 0 12px 0;">
            <div style="font-size: 1.15rem; font-weight: 700; color: #0F172A; letter-spacing: -0.02em;">SafeAgent Wallet</div>
            <div style="font-size: 0.75rem; color: #64748B;">Autonomous Agent Payment Gateway</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    pending_count = approval_center.get_pending_count()
    approvals_label = f"Approvals ({pending_count})" if pending_count > 0 else "Approvals"

    nav_options = [
        "Overview",
        "Wallet",
        "Agent Activity",
        approvals_label,
        "Security Center",
        "Transactions",
        "Audit Logs",
        "Settings",
    ]

    selected_raw = st.radio(
        "Navigation Menu",
        nav_options,
        index=0,
        label_visibility="collapsed",
    )

    current_page = "Approvals" if "Approvals" in selected_raw else selected_raw

    st.divider()

    # System Telemetry Indicator
    st.markdown("<div style='font-size: 0.75rem; font-weight: 600; color: #64748B; text-transform: uppercase; margin-bottom: 6px;'>System Telemetry</div>", unsafe_allow_html=True)
    
    # Status badges
    lock_badge = '<span class="status-pill status-pill-danger">Locked</span>' if wallet.is_locked else '<span class="status-pill status-pill-success">Active</span>'
    db_badge = '<span class="status-pill status-pill-success">Connected</span>'
    
    st.markdown(
        f"""
        <div style="font-size: 0.82rem; line-height: 1.8;">
            <div><b>Wallet State:</b> {lock_badge}</div>
            <div><b>Database:</b> {db_badge} <code style="font-size: 0.75rem;">SQLite WAL</code></div>
            <div><b>Pending Queue:</b> <span class="status-pill status-pill-{'warning' if pending_count > 0 else 'neutral'}">{pending_count} items</span></div>
            <div><b>Rate Usage:</b> {wallet._rate_limiter.get_request_count()} / {config.RATE_LIMIT_MAX_REQUESTS} (60s)</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.divider()

    # Emergency / Quick Controls
    st.markdown("<div style='font-size: 0.75rem; font-weight: 600; color: #64748B; text-transform: uppercase; margin-bottom: 6px;'>Quick Controls</div>", unsafe_allow_html=True)
    if wallet.is_locked:
        if st.button("Unlock Wallet", type="primary", use_container_width=True):
            wallet.unlock()
            set_notice("success", "Wallet unlocked by administrator.")
            st.rerun()

    c_sb1, c_sb2 = st.columns(2)
    with c_sb1:
        if st.button("Reset Rate", use_container_width=True, help="Clears rolling 60-second window"):
            wallet.reset_rate_limiter()
            set_notice("success", "Rate limiter window cleared.")
            st.rerun()
    with c_sb2:
        if st.button("Reset All", use_container_width=True, help="Reset wallet to $100.00"):
            handle_reset_all()
            st.rerun()


# =============================================================================
# PAGE 1: OVERVIEW
# =============================================================================

if current_page == "Overview":
    st.markdown("<h2 style='font-size: 1.5rem; font-weight: 700; color: #0F172A; margin-bottom: 2px;'>Overview</h2>", unsafe_allow_html=True)
    st.markdown("<p style='font-size: 0.85rem; color: #64748B; margin-bottom: 20px;'>Real-time operational summary and financial invariants for SafeAgent Wallet.</p>", unsafe_allow_html=True)
    render_notice()

    # Top Level Overview Cards
    total_tx_count = wallet.db.count_transactions()
    col1, col2, col3, col4, col5, col6 = st.columns(6)

    with col1:
        st.markdown(
            f"""
            <div class="metric-box">
                <div class="metric-box-label">Current Balance</div>
                <div class="metric-box-value">${wallet.balance:.2f}</div>
                <div class="metric-box-sub">Available virtual funds</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col2:
        st.markdown(
            f"""
            <div class="metric-box">
                <div class="metric-box-label">Initial Balance</div>
                <div class="metric-box-value">${config.INITIAL_BALANCE:.2f}</div>
                <div class="metric-box-sub">Starting deposit</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col3:
        st.markdown(
            f"""
            <div class="metric-box">
                <div class="metric-box-label">Total Spent</div>
                <div class="metric-box-value">${wallet.total_spent:.2f}</div>
                <div class="metric-box-sub">Lifetime expenditure</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col4:
        st.markdown(
            f"""
            <div class="metric-box">
                <div class="metric-box-label">Total Transactions</div>
                <div class="metric-box-value">{total_tx_count}</div>
                <div class="metric-box-sub">Logged in SQLite DB</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col5:
        p_badge_cls = "status-pill-warning" if pending_count > 0 else "status-pill-neutral"
        st.markdown(
            f"""
            <div class="metric-box">
                <div class="metric-box-label">Pending Approvals</div>
                <div class="metric-box-value">{pending_count}</div>
                <div class="metric-box-sub"><span class="status-pill {p_badge_cls}">Awaiting Review</span></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col6:
        sec_text = "LOCKED" if wallet.is_locked else "ACTIVE"
        sec_cls = "status-pill-danger" if wallet.is_locked else "status-pill-success"
        st.markdown(
            f"""
            <div class="metric-box">
                <div class="metric-box-label">Security State</div>
                <div class="metric-box-value" style="font-size: 1.25rem; padding-top: 4px;">
                    <span class="status-pill {sec_cls}">{sec_text}</span>
                </div>
                <div class="metric-box-sub">Rate limit: 3 / 60s</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if wallet.is_locked:
        lock_reason = wallet._auth_guard.lock_reason or "Security violation detected."
        st.markdown(
            f"""
            <div class="notice-banner-danger">
                <b>Wallet Locked:</b> {html.escape(str(lock_reason))} All payment requests are blocked. Use the sidebar control to unlock.
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Sub-Grid: Recent Transactions & Quick Actions
    g_col1, g_col2 = st.columns([1.6, 1.4])

    with g_col1:
        st.markdown(
            """
            <div class="fintech-card">
                <div class="fintech-card-header">
                    <span>Recent Transactions</span>
                    <span style="font-size: 0.78rem; font-weight: normal; color: #64748B;">Latest database records</span>
                </div>
            """,
            unsafe_allow_html=True,
        )
        recent_txs = wallet.db.get_all_transactions(limit=5, latest_first=True)
        if not recent_txs:
            st.markdown(
                """
                <div class="empty-state-box">
                    <div class="empty-state-title">No Transactions Recorded</div>
                    <div class="empty-state-desc">Transactions initiated by agents will appear in this ledger.</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            rows = []
            for t in recent_txs:
                st_code = str(t.get("status", "")).upper()
                rows.append({
                    "Transaction ID": t.get("transaction_id", ""),
                    "Merchant / Description": t.get("description", ""),
                    "Amount": f"${float(t.get('amount', 0)):.2f}",
                    "Status": st_code,
                    "Timestamp": str(t.get("timestamp", ""))[:19].replace("T", " "),
                })
            st.dataframe(rows, use_container_width=True, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with g_col2:
        st.markdown(
            """
            <div class="fintech-card">
                <div class="fintech-card-header">
                    <span>Quick Purchase Actions</span>
                    <span style="font-size: 0.78rem; font-weight: normal; color: #64748B;">One-click automated tests</span>
                </div>
            """,
            unsafe_allow_html=True,
        )
        
        qa_col1, qa_col2, qa_col3 = st.columns(3)
        with qa_col1:
            if st.button("Buy Cable\n$4.50 (Auto)", use_container_width=True, help="Executes automatically under $10 threshold"):
                handle_purchase_directive("Buy USB-C Cable")
                st.rerun()
        with qa_col2:
            if st.button("Buy Mouse\n$9.00 (Auto)", use_container_width=True, help="Executes automatically under $10 threshold"):
                handle_purchase_directive("Buy Wireless Mouse")
                st.rerun()
        with qa_col3:
            if st.button("Buy Audio\n$15.00 (Approval)", use_container_width=True, help="Exceeds $10: Triggers Human Approval Queue"):
                handle_purchase_directive("Buy Bluetooth Headphones")
                st.rerun()

        st.divider()

        st.markdown("<div style='font-size: 0.82rem; font-weight: 600; color: #334155; margin-bottom: 8px;'>Rogue Agent Defense</div>", unsafe_allow_html=True)
        if st.button("Simulate Runaway Agent Attack (10 Rapid Attempts)", use_container_width=True, type="secondary"):
            handle_runaway_sim()
            st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)


# =============================================================================
# PAGE 2: WALLET
# =============================================================================

elif current_page == "Wallet":
    st.markdown("<h2 style='font-size: 1.5rem; font-weight: 700; color: #0F172A; margin-bottom: 2px;'>Wallet Management</h2>", unsafe_allow_html=True)
    st.markdown("<p style='font-size: 0.85rem; color: #64748B; margin-bottom: 20px;'>Financial invariants, balance reserves, and direct payment execution controls.</p>", unsafe_allow_html=True)
    render_notice()

    # Balance and Spending Limits Cards
    w_col1, w_col2, w_col3, w_col4 = st.columns(4)
    with w_col1:
        st.markdown(
            f"""
            <div class="metric-box">
                <div class="metric-box-label">Current Balance</div>
                <div class="metric-box-value">${wallet.balance:.2f}</div>
                <div class="metric-box-sub">Initial deposit: ${config.INITIAL_BALANCE:.2f}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with w_col2:
        st.markdown(
            f"""
            <div class="metric-box">
                <div class="metric-box-label">Total Spent</div>
                <div class="metric-box-value">${wallet.total_spent:.2f}</div>
                <div class="metric-box-sub">Cumulative expenditure</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with w_col3:
        st.markdown(
            f"""
            <div class="metric-box">
                <div class="metric-box-label">Remaining Spending Limit</div>
                <div class="metric-box-value">${wallet.remaining_spending_limit:.2f}</div>
                <div class="metric-box-sub">Lifetime limit: ${config.LIFETIME_SPENDING_LIMIT:.2f}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with w_col4:
        st.markdown(
            f"""
            <div class="metric-box">
                <div class="metric-box-label">Auto Payment Threshold</div>
                <div class="metric-box-value">${config.AUTO_PAYMENT_THRESHOLD:.2f}</div>
                <div class="metric-box-sub">Payments strictly above require approval</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.write("")

    # Direct Payment Execution Form
    st.markdown(
        """
        <div class="fintech-card">
            <div class="fintech-card-header">
                <span>Manual Payment Authorization Test</span>
                <span style="font-size: 0.78rem; font-weight: normal; color: #64748B;">Direct API validation harness</span>
            </div>
        """,
        unsafe_allow_html=True,
    )

    with st.form("manual_pay_form"):
        pf_c1, pf_c2 = st.columns(2)
        with pf_c1:
            pay_recipient = st.text_input("Merchant / Recipient Description", value="Direct Test Vendor")
            pay_amount = st.number_input("Payment Amount ($)", min_value=0.01, max_value=200.00, value=4.50, step=0.50)
        with pf_c2:
            pay_approved = st.checkbox("Include Human Approval Token", value=False, help="Required for amounts > $10.00")
            pay_token = st.text_input("Authorization Token", value=config.DEFAULT_AUTH_TOKEN if pay_approved else "")

        submitted = st.form_submit_button("Submit Payment to SafeAgent Wallet", type="primary")
        if submitted:
            res: PaymentResult = wallet.execute_payment(
                amount=Decimal(str(pay_amount)),
                recipient=pay_recipient.strip(),
                human_approved=True if pay_approved else None,
                auth_token=pay_token.strip(),
                agent_id="Manual UI Harness",
            )
            if res.success:
                set_notice("success", f"Payment Successful: {res.transaction_id} | Amount: ${res.amount:.2f} | Remaining: ${res.balance:.2f}")
            elif res.requires_human_approval:
                set_notice("warning", f"Security Hold: {res.reason} (Route to Approval Center)")
            else:
                set_notice("danger", f"Payment Rejected: {res.reason}")
            st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)

    # Catalog Quick Checkout
    st.markdown(
        """
        <div class="fintech-card">
            <div class="fintech-card-header">
                <span>Marketplace Quick Checkout</span>
                <span style="font-size: 0.78rem; font-weight: normal; color: #64748B;">Test standard catalog items</span>
            </div>
        """,
        unsafe_allow_html=True,
    )
    prods = marketplace.get_all_products()
    p_cols = st.columns(len(prods))
    for idx, p in enumerate(prods):
        with p_cols[idx]:
            st.markdown(
                f"""
                <div class="product-grid-card">
                    <div>
                        <div class="product-grid-title">{html.escape(p.name)}</div>
                        <div class="product-grid-desc">{html.escape(p.description)}</div>
                    </div>
                    <div>
                        <div class="product-grid-price">${p.price:.2f}</div>
                        <div style="font-size: 0.72rem; color: #64748B; margin-bottom: 8px;">Seller: <code>{p.seller_id}</code></div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button(f"Buy {p.name}", key=f"btn_buy_{p.product_id}", use_container_width=True):
                handle_purchase_directive(f"Buy {p.name}")
                st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)

    # Administrative Controls
    st.markdown(
        """
        <div class="fintech-card">
            <div class="fintech-card-header">
                <span>Administrative Controls</span>
                <span style="font-size: 0.78rem; font-weight: normal; color: #64748B;">Maintenance and reset operations</span>
            </div>
        """,
        unsafe_allow_html=True,
    )
    ac_col1, ac_col2, ac_col3 = st.columns(3)
    with ac_col1:
        if wallet.is_locked:
            if st.button("Unlock Wallet", type="primary", use_container_width=True):
                wallet.unlock()
                set_notice("success", "Wallet unlocked.")
                st.rerun()
        else:
            if st.button("Lock Wallet (Quarantine)", use_container_width=True):
                wallet.lock(reason="Administrative manual lock.")
                set_notice("warning", "Wallet locked for quarantine.")
                st.rerun()
    with ac_col2:
        if st.button("Reset Rate Limiter Window", use_container_width=True):
            wallet.reset_rate_limiter()
            set_notice("success", "Rate limiter sliding window reset.")
            st.rerun()
    with ac_col3:
        confirm_reset = st.checkbox("Confirm Complete State Reset", key="chk_reset_confirm")
        if st.button("Reset Wallet to $100.00", disabled=not confirm_reset, use_container_width=True):
            handle_reset_all()
            st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)


# =============================================================================
# PAGE 3: AGENT ACTIVITY
# =============================================================================

elif current_page == "Agent Activity":
    st.markdown("<h2 style='font-size: 1.5rem; font-weight: 700; color: #0F172A; margin-bottom: 2px;'>Agent Activity</h2>", unsafe_allow_html=True)
    st.markdown("<p style='font-size: 0.85rem; color: #64748B; margin-bottom: 20px;'>Autonomous purchase negotiations, seller invoicing, and multi-agent interaction trace logs.</p>", unsafe_allow_html=True)
    render_notice()

    # Agent Directive Bar
    st.markdown(
        """
        <div class="fintech-card">
            <div class="fintech-card-header">
                <span>Issue Agent Purchase Directive</span>
                <span style="font-size: 0.78rem; font-weight: normal; color: #64748B;">Autonomous Buyer Agent Natural Language Dispatch</span>
            </div>
        """,
        unsafe_allow_html=True,
    )
    dir_col1, dir_col2 = st.columns([3.5, 1])
    with dir_col1:
        user_query = st.text_input(
            "Natural Language Directive",
            placeholder="e.g. 'I need a durable USB-C charging cable', 'Order headphones', 'Buy mouse'",
            label_visibility="collapsed",
        )
    with dir_col2:
        dispatch_btn = st.button("Dispatch Buyer Agent", type="primary", use_container_width=True)

    if dispatch_btn and user_query:
        handle_purchase_directive(user_query)
        st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)

    # Latest Multi-Agent Execution Trace
    if st.session_state.last_agent_result:
        res: PurchaseFlowResult = st.session_state.last_agent_result
        st.markdown(
            f"""
            <div class="fintech-card">
                <div class="fintech-card-header">
                    <span>Multi-Agent Interaction Trace</span>
                    <span class="status-pill status-pill-{'success' if res.success else ('warning' if res.status == 'AWAITING_APPROVAL' else 'danger')}">{res.status}</span>
                </div>
            """,
            unsafe_allow_html=True,
        )
        for step in res.trace:
            st.markdown(
                f"""
                <div style="background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px; padding: 10px 14px; margin-bottom: 8px;">
                    <div style="display: flex; justify-content: space-between; font-size: 0.8rem; font-weight: 600; color: #334155; margin-bottom: 3px;">
                        <span>{html.escape(step.agent)} &rarr; {html.escape(step.action)}</span>
                        <span style="color: #94A3B8; font-weight: normal;">{step.timestamp}</span>
                    </div>
                    <div style="font-size: 0.82rem; color: #475569;">{html.escape(step.details)}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        st.markdown("</div>", unsafe_allow_html=True)

    # Activity Table
    st.markdown(
        """
        <div class="fintech-card">
            <div class="fintech-card-header">
                <span>Recent Agent Directives & Requests</span>
                <span style="font-size: 0.78rem; font-weight: normal; color: #64748B;">History of agent-negotiated orders</span>
            </div>
        """,
        unsafe_allow_html=True,
    )
    if not st.session_state.agent_history:
        st.markdown(
            """
            <div class="empty-state-box">
                <div class="empty-state-title">No Agent Activity Logged Yet</div>
                <div class="empty-state-desc">Dispatch a purchase directive above or use Quick Actions to see agent negotiation traces.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.dataframe(st.session_state.agent_history, use_container_width=True, hide_index=True)
    st.markdown("</div>", unsafe_allow_html=True)

    # Seller Agents Directory & Inventory Control
    st.markdown(
        """
        <div class="fintech-card">
            <div class="fintech-card-header">
                <span>Registered Seller Agents & Inventory Status</span>
                <span style="font-size: 0.78rem; font-weight: normal; color: #64748B;">Simulated vendor endpoints</span>
            </div>
        """,
        unsafe_allow_html=True,
    )
    s_col1, s_col2, s_col3 = st.columns(3)
    seller_list = list(sellers.values())
    for idx, s in enumerate(seller_list):
        with [s_col1, s_col2, s_col3][idx % 3]:
            prod = marketplace.get_product(s.product_id)
            is_avail = prod.availability if prod else False
            avail_badge = '<span class="status-pill status-pill-success">In Stock</span>' if is_avail else '<span class="status-pill status-pill-danger">Out of Stock</span>'
            st.markdown(
                f"""
                <div style="background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px; padding: 14px; margin-bottom: 10px;">
                    <div style="font-size: 0.95rem; font-weight: 600; color: #0F172A;">{html.escape(s.name)}</div>
                    <div style="font-size: 0.75rem; color: #64748B; margin: 2px 0 6px 0;">Seller ID: <code>{s.seller_id}</code></div>
                    <div style="font-size: 0.82rem; color: #334155; margin-bottom: 8px;">Product: <b>{html.escape(s.product_name)}</b> (${s.price:.2f})</div>
                    <div>Status: {avail_badge}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            btn_txt = "Mark Out of Stock" if is_avail else "Restock Product"
            if st.button(btn_txt, key=f"tgl_{s.seller_id}", use_container_width=True):
                marketplace.set_availability(s.product_id, not is_avail)
                st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)


# =============================================================================
# PAGE 4: APPROVALS
# =============================================================================

elif current_page == "Approvals":
    st.markdown("<h2 style='font-size: 1.5rem; font-weight: 700; color: #0F172A; margin-bottom: 2px;'>Human Approval Center</h2>", unsafe_allow_html=True)
    st.markdown("<p style='font-size: 0.85rem; color: #64748B; margin-bottom: 20px;'>Review, authorize, or decline purchase requests exceeding the $10.00 automatic threshold.</p>", unsafe_allow_html=True)
    render_notice()

    pending_reqs = approval_center.get_pending_requests()

    st.markdown(
        f"""
        <div class="fintech-card">
            <div class="fintech-card-header">
                <span>Pending Approval Queue ({len(pending_reqs)})</span>
                <span style="font-size: 0.78rem; font-weight: normal; color: #64748B;">Requires explicit human authorization token</span>
            </div>
        """,
        unsafe_allow_html=True,
    )

    if not pending_reqs:
        st.markdown(
            """
            <div class="empty-state-box">
                <div class="empty-state-title">No Pending Requests</div>
                <div class="empty-state-desc">Transactions exceeding the $10.00 threshold will be intercepted and queued here for human review.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        for req in pending_reqs:
            st.markdown(
                f"""
                <div style="background: #FFFFFF; border: 1px solid #CBD5E1; border-left: 4px solid #D97706; border-radius: 8px; padding: 18px; margin-bottom: 16px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                        <div>
                            <span style="font-size: 1.1rem; font-weight: 700; color: #0F172A;">{html.escape(req.product_name)}</span>
                            <span style="font-size: 0.8rem; color: #64748B; margin-left: 8px;">Order: <code>{html.escape(req.order_id or req.request_id)}</code></span>
                        </div>
                        <div style="font-size: 1.35rem; font-weight: 800; color: #0F172A;">${req.amount:.2f}</div>
                    </div>
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px; background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px; padding: 10px 14px; margin-bottom: 12px; font-size: 0.82rem;">
                        <div><span style="color: #64748B;">Request ID:</span> <br><code>{req.request_id}</code></div>
                        <div><span style="color: #64748B;">Merchant / Seller:</span> <br><b>{html.escape(req.seller_name)}</b></div>
                        <div><span style="color: #64748B;">Buyer Agent:</span> <br>{html.escape(req.buyer_agent)}</div>
                        <div><span style="color: #64748B;">Submitted At:</span> <br>{req.timestamp[:19].replace('T', ' ')}</div>
                    </div>
                    <div style="background: #FFFBEB; border: 1px solid #FDE68A; border-radius: 6px; padding: 10px 14px; font-size: 0.82rem; color: #92400E; margin-bottom: 14px;">
                        <b>Security Intercept:</b> {html.escape(req.reason)}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # Inline Authorization Action Controls
            with st.container():
                auth_c1, auth_c2, auth_c3 = st.columns([1.5, 1, 1])
                with auth_c1:
                    auth_token_input = st.text_input(
                        "Authorization Credential Token",
                        value=config.DEFAULT_AUTH_TOKEN,
                        key=f"token_{req.request_id}",
                        help="Cryptographic credential token required to authorize human transactions.",
                    )
                with auth_c2:
                    confirm_auth = st.checkbox("Confirm Authorization", key=f"chk_auth_{req.request_id}")
                    if st.button("Approve Payment", key=f"btn_appr_{req.request_id}", type="primary", disabled=not confirm_auth, use_container_width=True):
                        handle_approve(req.request_id, auth_token_input)
                        st.rerun()
                with auth_c3:
                    reject_reason = st.text_input("Rejection Reason", value="Declined by human reviewer", key=f"rej_reason_{req.request_id}")
                    if st.button("Reject Request", key=f"btn_rej_{req.request_id}", type="secondary", use_container_width=True):
                        handle_reject(req.request_id, reject_reason)
                        st.rerun()

            st.write("")

    st.markdown("</div>", unsafe_allow_html=True)

    # Historical Decisions
    st.markdown(
        """
        <div class="fintech-card">
            <div class="fintech-card-header">
                <span>Historical Approval Decisions</span>
                <span style="font-size: 0.78rem; font-weight: normal; color: #64748B;">Past human reviewer determinations</span>
            </div>
        """,
        unsafe_allow_html=True,
    )
    all_reqs = approval_center.get_all_requests()
    historical = [r for r in all_reqs if r.status != "PENDING"]
    if not historical:
        st.markdown(
            """
            <div class="empty-state-box">
                <div class="empty-state-title">No Historical Approvals</div>
                <div class="empty-state-desc">Reviewed transactions will be listed here with decision timestamps.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        h_rows = []
        for r in reversed(historical):
            h_rows.append({
                "Request ID": r.request_id,
                "Product": r.product_name,
                "Amount": f"${r.amount:.2f}",
                "Status": r.status,
                "Decision Reason": r.decision_reason or r.reason,
                "Decided At": r.decision_timestamp or r.timestamp,
                "Transaction ID": r.transaction_id or "—",
            })
        st.dataframe(h_rows, use_container_width=True, hide_index=True)

    st.markdown("</div>", unsafe_allow_html=True)


# =============================================================================
# PAGE 5: SECURITY CENTER
# =============================================================================

elif current_page == "Security Center":
    st.markdown("<h2 style='font-size: 1.5rem; font-weight: 700; color: #0F172A; margin-bottom: 2px;'>Security Center</h2>", unsafe_allow_html=True)
    st.markdown("<p style='font-size: 0.85rem; color: #64748B; margin-bottom: 20px;'>Real-time threat monitoring, rate limit sliding window, and runaway agent defenses.</p>", unsafe_allow_html=True)
    render_notice()

    # Security Metrics Row
    s_col1, s_col2, s_col3, s_col4 = st.columns(4)
    with s_col1:
        lock_status_text = "LOCKED" if wallet.is_locked else "ACTIVE"
        lock_status_cls = "status-pill-danger" if wallet.is_locked else "status-pill-success"
        st.markdown(
            f"""
            <div class="metric-box">
                <div class="metric-box-label">Wallet Lock State</div>
                <div class="metric-box-value"><span class="status-pill {lock_status_cls}">{lock_status_text}</span></div>
                <div class="metric-box-sub">Lock status invariant</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with s_col2:
        req_count_now = wallet._rate_limiter.get_request_count()
        st.markdown(
            f"""
            <div class="metric-box">
                <div class="metric-box-label">Rolling 60s Rate Limiter</div>
                <div class="metric-box-value">{req_count_now} / {config.RATE_LIMIT_MAX_REQUESTS}</div>
                <div class="metric-box-sub">Max allowed in 60s window</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with s_col3:
        st.markdown(
            f"""
            <div class="metric-box">
                <div class="metric-box-label">Failed Auth Counter</div>
                <div class="metric-box-value">{wallet.invalid_auth_attempts} / {config.MAX_INVALID_AUTH_ATTEMPTS}</div>
                <div class="metric-box-sub">Locks after 3 failed strikes</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with s_col4:
        st.markdown(
            f"""
            <div class="metric-box">
                <div class="metric-box-label">Blocked Attempts</div>
                <div class="metric-box-value">{wallet.blocked_attempts_count}</div>
                <div class="metric-box-sub">Unauthorized transactions thwarted</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Runaway Agent Active Alert
    if wallet.runaway_alert:
        ra = wallet.runaway_alert
        st.markdown(
            f"""
            <div class="notice-banner-danger" style="margin-top: 10px;">
                <div style="font-weight: 700; font-size: 0.95rem; margin-bottom: 4px;">Runaway Agent Detected: Autonomous Lockout Engaged</div>
                <div>{html.escape(ra.get('message', 'AI agent exceeded permitted transaction rate.'))}</div>
                <div style="margin-top: 8px; font-size: 0.8rem; color: #7F1D1D;">
                    <b>Agent ID:</b> <code>{html.escape(ra.get('agent_id', 'Unknown'))}</code> | 
                    <b>Breach Timestamp:</b> {ra.get('lock_timestamp', '')} | 
                    <b>Protection:</b> 100% of subsequent attempts blocked ($0 deducted).
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Runaway Agent Attack Simulation Harness
    st.markdown(
        """
        <div class="fintech-card">
            <div class="fintech-card-header">
                <span>Runaway Agent Attack Simulator</span>
                <span style="font-size: 0.78rem; font-weight: normal; color: #64748B;">Controlled security boundary stress test</span>
            </div>
            <p style="font-size: 0.82rem; color: #475569; margin-bottom: 14px;">
                Simulates an AI buyer agent falling into an uncontrolled infinite loop attempting 10 rapid purchases. 
                Attempts 1–3 are evaluated under normal financial limits; Attempt 4 triggers the rolling 60-second rate limiter breach and auto-locks the wallet; 
                Attempts 5–10 are blocked by the locked wallet. Zero unauthorized funds are deducted.
            </p>
        """,
        unsafe_allow_html=True,
    )

    if st.button("Trigger 10-Attempt Runaway Agent Attack Simulation", type="primary"):
        handle_runaway_sim()
        st.rerun()

    if st.session_state.simulation_results:
        sim_res = st.session_state.simulation_results
        sim_rows = []
        for idx, r in enumerate(sim_res):
            st_text = "ALLOWED" if r.success else "BLOCKED"
            sim_rows.append({
                "Attempt": f"#{idx + 1} of 10",
                "Transaction ID": r.transaction_id,
                "Amount": f"${r.amount:.2f}",
                "Status": st_text,
                "Security Result": r.reason,
                "Wallet Balance After": f"${r.balance:.2f}",
            })
        st.write("")
        st.dataframe(sim_rows, use_container_width=True, hide_index=True)

    st.markdown("</div>", unsafe_allow_html=True)

    # Blocked Security Events Ledger
    st.markdown(
        """
        <div class="fintech-card">
            <div class="fintech-card-header">
                <span>Blocked Security Events History</span>
                <span style="font-size: 0.78rem; font-weight: normal; color: #64748B;">SQLite-backed threat defense records</span>
            </div>
        """,
        unsafe_allow_html=True,
    )
    blocked_txs = wallet.db.get_blocked_transactions()
    if not blocked_txs:
        st.markdown(
            """
            <div class="empty-state-box">
                <div class="empty-state-title">No Blocked Events Recorded</div>
                <div class="empty-state-desc">Transactions rejected by rate limits or locked wallet checks will be recorded here.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        b_rows = []
        for t in reversed(blocked_txs):
            b_rows.append({
                "Transaction ID": t.get("transaction_id", ""),
                "Agent": t.get("agent_id", "Buyer Agent"),
                "Amount": f"${float(t.get('amount', 0)):.2f}",
                "Status": t.get("status", ""),
                "Event Type": t.get("event_type", ""),
                "Reason": t.get("reason", ""),
                "Timestamp": str(t.get("timestamp", ""))[:19].replace("T", " "),
            })
        st.dataframe(b_rows, use_container_width=True, hide_index=True)

    st.markdown("</div>", unsafe_allow_html=True)


# =============================================================================
# PAGE 6: TRANSACTIONS
# =============================================================================

elif current_page == "Transactions":
    st.markdown("<h2 style='font-size: 1.5rem; font-weight: 700; color: #0F172A; margin-bottom: 2px;'>Transactions</h2>", unsafe_allow_html=True)
    st.markdown("<p style='font-size: 0.85rem; color: #64748B; margin-bottom: 20px;'>Operational transaction records and settlement outcomes.</p>", unsafe_allow_html=True)
    render_notice()

    st.markdown(
        """
        <div class="fintech-card">
            <div class="fintech-card-header">
                <span>Transaction History</span>
                <span style="font-size: 0.78rem; font-weight: normal; color: #64748B;">Search and filter ledger</span>
            </div>
        """,
        unsafe_allow_html=True,
    )

    t_fcol1, t_fcol2 = st.columns([1, 2])
    with t_fcol1:
        tx_filter_status = st.selectbox(
            "Filter by Status",
            ["All", "SUCCESS", "REJECTED", "BLOCKED"],
            key="tx_page_status_filter",
        )
    with t_fcol2:
        tx_search_query = st.text_input(
            "Search Transactions",
            placeholder="Search Transaction ID, Description, or Agent ID...",
            key="tx_page_search_input",
        )

    db_st = None if tx_filter_status == "All" else tx_filter_status
    db_sq = tx_search_query.strip() if tx_search_query and tx_search_query.strip() else None

    records = wallet.db.get_all_transactions(
        status=db_st,
        search=db_sq,
        latest_first=True,
    )

    if not records:
        st.markdown(
            f"""
            <div class="empty-state-box">
                <div class="empty-state-title">No Transactions Found</div>
                <div class="empty-state-desc">No transactions matched status '{tx_filter_status}' and search criteria.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        table_rows = []
        for t in records:
            table_rows.append({
                "Transaction ID": t.get("transaction_id", ""),
                "Agent ID": t.get("agent_id") or "Buyer Agent",
                "Merchant / Description": t.get("description", ""),
                "Amount": f"${float(t.get('amount', 0)):.2f}",
                "Status": t.get("status", ""),
                "Timestamp": str(t.get("timestamp", ""))[:19].replace("T", " "),
                "Balance After": f"${float(t.get('balance_after', 0)):.2f}",
                "Outcome Reason": t.get("reason", ""),
            })
        st.dataframe(table_rows, use_container_width=True, hide_index=True)

    st.markdown("</div>", unsafe_allow_html=True)


# =============================================================================
# PAGE 7: AUDIT LOGS
# =============================================================================

elif current_page == "Audit Logs":
    st.markdown("<h2 style='font-size: 1.5rem; font-weight: 700; color: #0F172A; margin-bottom: 2px;'>Audit Logs</h2>", unsafe_allow_html=True)
    st.markdown("<p style='font-size: 0.85rem; color: #64748B; margin-bottom: 20px;'>Immutable, database-backed security ledger with integer-cent monetary precision.</p>", unsafe_allow_html=True)
    render_notice()

    total_audit_count = wallet.db.count_transactions()

    st.markdown(
        f"""
        <div class="fintech-card">
            <div class="fintech-card-header">
                <span>SQLite Event Ledger</span>
                <span style="font-size: 0.78rem; font-weight: normal; color: #64748B;">Total Records: <b>{total_audit_count}</b> | Storage: <code>data/safeagent.db</code></span>
            </div>
        """,
        unsafe_allow_html=True,
    )

    al_c1, al_c2, al_c3 = st.columns([1, 1, 2])
    with al_c1:
        audit_filter_event = st.selectbox(
            "Filter by Event Type",
            [
                "All",
                "PAYMENT_SUCCESS",
                "HUMAN_APPROVAL",
                "HUMAN_REJECTION",
                "PAYMENT_FAILED",
                "AUTH_FAILED",
                "RUNAWAY_BLOCKED",
                "WALLET_LOCKED",
            ],
            key="audit_filter_event",
        )
    with al_c2:
        audit_filter_status = st.selectbox(
            "Filter by Status",
            ["All", "SUCCESS", "REJECTED", "BLOCKED"],
            key="audit_filter_status",
        )
    with al_c3:
        audit_search = st.text_input(
            "Search Audit Records",
            placeholder="Search Transaction ID, Request ID, Agent, or Description...",
            key="audit_search_input",
        )

    evt_param = None if audit_filter_event == "All" else audit_filter_event
    st_param = None if audit_filter_status == "All" else audit_filter_status
    search_param = audit_search.strip() if audit_search and audit_search.strip() else None

    audit_records = wallet.db.get_all_transactions(
        status=st_param,
        event_type=evt_param,
        search=search_param,
        latest_first=True,
    )

    if not audit_records:
        st.markdown(
            """
            <div class="empty-state-box">
                <div class="empty-state-title">No Audit Records Found</div>
                <div class="empty-state-desc">No events matched the selected filter parameters.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        audit_table = []
        for a in audit_records:
            audit_table.append({
                "Event Type": a.get("event_type", ""),
                "Transaction ID": a.get("transaction_id", ""),
                "Request ID": a.get("request_id") or "—",
                "Agent": a.get("agent_id") or "Buyer Agent",
                "Amount ($)": f"${float(a.get('amount', 0)):.2f}",
                "Amount (Cents)": a.get("amount_cents", 0),
                "Status": a.get("status", ""),
                "Balance After ($)": f"${float(a.get('balance_after', 0)):.2f}",
                "Reason": a.get("reason", ""),
                "Timestamp": str(a.get("timestamp", ""))[:19].replace("T", " "),
            })
        st.dataframe(audit_table, use_container_width=True, hide_index=True)

    st.markdown("</div>", unsafe_allow_html=True)


# =============================================================================
# PAGE 8: SETTINGS
# =============================================================================

elif current_page == "Settings":
    st.markdown("<h2 style='font-size: 1.5rem; font-weight: 700; color: #0F172A; margin-bottom: 2px;'>Settings & System Configuration</h2>", unsafe_allow_html=True)
    st.markdown("<p style='font-size: 0.85rem; color: #64748B; margin-bottom: 20px;'>Operational parameters, financial bounds, and system metadata.</p>", unsafe_allow_html=True)
    render_notice()

    s_col1, s_col2 = st.columns(2)

    with s_col1:
        st.markdown(
            f"""
            <div class="fintech-card">
                <div class="fintech-card-header">
                    <span>Financial Policy Configuration</span>
                    <span style="font-size: 0.78rem; font-weight: normal; color: #64748B;">Core wallet bounds</span>
                </div>
                <div style="font-size: 0.85rem; line-height: 2;">
                    <div><b>Initial Virtual Balance:</b> <code>${config.INITIAL_BALANCE:.2f}</code></div>
                    <div><b>Lifetime Cumulative Spending Limit:</b> <code>${config.LIFETIME_SPENDING_LIMIT:.2f}</code></div>
                    <div><b>Automatic Payment Threshold:</b> <code>${config.AUTO_PAYMENT_THRESHOLD:.2f}</code> (Inclusive)</div>
                    <div><b>Human Approval Policy:</b> Mandatory for any transaction strictly &gt; ${config.AUTO_PAYMENT_THRESHOLD:.2f}</div>
                    <div><b>Overdraft Invariant:</b> Balance strictly bounded at &ge; $0.00</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(
            f"""
            <div class="fintech-card">
                <div class="fintech-card-header">
                    <span>Database & Persistence Health</span>
                    <span style="font-size: 0.78rem; font-weight: normal; color: #64748B;">Storage telemetry</span>
                </div>
                <div style="font-size: 0.85rem; line-height: 2;">
                    <div><b>Primary Database:</b> <code>data/safeagent.db</code></div>
                    <div><b>Database Engine:</b> SQLite3 (WAL Mode + Thread-safe RLock)</div>
                    <div><b>Monetary Storage:</b> Stored in integer cents (e.g. $4.50 &rarr; 450 cents)</div>
                    <div><b>Active Schema:</b> <code>transactions</code> (12 typed columns)</div>
                    <div><b>Database Indexes:</b> 5 performance indexes active</div>
                    <div><b>Total Persisted Events:</b> <code>{wallet.db.count_transactions()}</code></div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with s_col2:
        st.markdown(
            f"""
            <div class="fintech-card">
                <div class="fintech-card-header">
                    <span>Security & Anti-Tamper Configuration</span>
                    <span style="font-size: 0.78rem; font-weight: normal; color: #64748B;">Defense rules</span>
                </div>
                <div style="font-size: 0.85rem; line-height: 2;">
                    <div><b>Rate Limiter Window:</b> <code>{int(config.RATE_LIMIT_WINDOW_SECONDS)} seconds</code></div>
                    <div><b>Max Requests per Window:</b> <code>{config.RATE_LIMIT_MAX_REQUESTS} payment attempts</code></div>
                    <div><b>Rogue Loop Policy:</b> Lock wallet immediately on 4th attempt in window</div>
                    <div><b>Anti-Tamper Lockout:</b> Locks after <code>{config.MAX_INVALID_AUTH_ATTEMPTS} invalid credential strikes</code></div>
                    <div><b>Rejection Policy:</b> Normal human rejections never count toward strikes</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(
            """
            <div class="fintech-card">
                <div class="fintech-card-header">
                    <span>Application & Hackathon Metadata</span>
                    <span style="font-size: 0.78rem; font-weight: normal; color: #64748B;">System specifications</span>
                </div>
                <div style="font-size: 0.85rem; line-height: 2;">
                    <div><b>Application Name:</b> SafeAgent Wallet</div>
                    <div><b>Version:</b> 2.0 (Multi-Page Fintech Architecture)</div>
                    <div><b>Hackathon:</b> CommitCon 24-Hour Hackathon</div>
                    <div><b>Challenge:</b> Stripe – Agents That Can Pay (Problem Statement #7)</div>
                    <div><b>Lead Developer:</b> Abhyjoit Singh (<a href="https://github.com/Abhyjoit/SafeAgent-Wallet" target="_blank">@Abhyjoit</a>)</div>
                    <div><b>License:</b> MIT Open Source (2026)</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
