"""
app.py - SafeAgent Wallet & Human Approval Center
CommitCon 24-Hour Hackathon - Problem Statement #7: Stripe – Agents That Can Pay
Hours 10–12: Human Approval Center UI Implementation

Features:
- Modern glass-like fintech dashboard styling (dark navy, subtle glowing borders, status badges).
- Sidebar navigation: Dashboard, Marketplace, Approval Center (with live pending count badge), Transaction History, Security Settings.
- Real-time Wallet Overview Cards (Balance, Total Spent, Remaining Limit, Security Status).
- Visually prominent Human Approval Center for reviewing and authorizing payments exceeding $10.00.
- Single-execution idempotency (duplicate clicks never create duplicate payments).
- Full security re-verification (availability, balance, limit, lockout, rate limit).
- Autonomous Buyer Agent & 3 Seller Agents with multi-agent communication trace.
- Live Transaction Audit Ledger with filtering.
"""

from decimal import Decimal
import html
from typing import Any, Dict, List, Optional

import streamlit as st

from buyer_agent import BuyerAgent
import config
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
    page_title="SafeAgent Wallet - Human Approval Center",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    /* Global Background and Typography */
    .stApp {
        background-color: #0A0E1A;
        color: #E2E8F0;
    }
    
    /* Modern Glass-like Metric Cards */
    .metric-card {
        background: rgba(19, 26, 43, 0.75);
        backdrop-filter: blur(12px);
        border: 1px solid rgba(59, 130, 246, 0.18);
        border-radius: 14px;
        padding: 18px 20px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4), 0 0 15px rgba(59, 130, 246, 0.05);
        transition: transform 0.15s ease, border-color 0.15s ease;
    }
    .metric-card:hover {
        border-color: rgba(59, 130, 246, 0.4);
        transform: translateY(-1px);
    }
    .metric-label {
        font-size: 0.78rem;
        color: #8E9BAE;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        margin-bottom: 6px;
    }
    .metric-value {
        font-size: 1.85rem;
        font-weight: 800;
        color: #FFFFFF;
        line-height: 1.2;
    }
    .metric-subtext {
        font-size: 0.78rem;
        color: #64748B;
        margin-top: 5px;
    }

    /* Approval Center Prominent Cards */
    .approval-card {
        background: linear-gradient(145deg, rgba(28, 25, 23, 0.85) 0%, rgba(20, 26, 38, 0.95) 100%);
        backdrop-filter: blur(16px);
        border: 2px solid #F59E0B;
        border-radius: 16px;
        padding: 24px;
        box-shadow: 0 8px 30px rgba(0, 0, 0, 0.5), 0 0 20px rgba(245, 158, 11, 0.15);
        margin-bottom: 22px;
    }
    .approval-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 16px;
        border-bottom: 1px solid rgba(245, 158, 11, 0.2);
        padding-bottom: 12px;
    }
    .approval-title {
        font-size: 1.35rem;
        font-weight: 800;
        color: #F8FAFC;
        display: flex;
        align-items: center;
        gap: 10px;
    }
    .approval-amount {
        font-size: 1.6rem;
        font-weight: 800;
        color: #38BDF8;
    }
    .approval-meta-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 12px;
        background: rgba(15, 23, 42, 0.6);
        border: 1px solid rgba(255, 255, 255, 0.05);
        border-radius: 10px;
        padding: 14px;
        margin-bottom: 16px;
    }
    .meta-item-label {
        font-size: 0.72rem;
        color: #94A3B8;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }
    .meta-item-value {
        font-size: 0.92rem;
        color: #F1F5F9;
        font-weight: 600;
        margin-top: 2px;
    }
    .approval-reason-box {
        background: rgba(245, 158, 11, 0.1);
        border-left: 4px solid #F59E0B;
        border-radius: 0 8px 8px 0;
        padding: 12px 16px;
        font-size: 0.88rem;
        color: #FEF3C7;
        margin-bottom: 18px;
    }

    /* Product Cards */
    .product-box {
        background: rgba(24, 30, 42, 0.75);
        backdrop-filter: blur(10px);
        border: 1px solid rgba(59, 130, 246, 0.15);
        border-radius: 14px;
        padding: 22px;
        min-height: 250px;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        margin-bottom: 16px;
        transition: transform 0.15s ease, border-color 0.15s ease;
    }
    .product-box:hover {
        border-color: #3B82F6;
        transform: translateY(-2px);
    }
    .product-icon {
        font-size: 2.3rem;
        margin-bottom: 8px;
    }
    .product-title {
        font-size: 1.2rem;
        font-weight: 700;
        color: #F8FAFC;
        margin-bottom: 4px;
    }
    .product-desc {
        font-size: 0.85rem;
        color: #94A3B8;
        min-height: 44px;
        margin-bottom: 10px;
    }
    .product-price {
        font-size: 1.5rem;
        font-weight: 800;
        color: #38BDF8;
        margin-bottom: 6px;
    }
    .product-seller {
        font-size: 0.8rem;
        color: #A5B4FC;
        margin-bottom: 10px;
    }

    /* Status Badges */
    .badge-pending {
        background: rgba(245, 158, 11, 0.2);
        color: #FBBF24;
        border: 1px solid rgba(245, 158, 11, 0.4);
        border-radius: 9999px;
        padding: 4px 12px;
        font-size: 0.75rem;
        font-weight: 700;
        letter-spacing: 0.04em;
    }
    .badge-approved {
        background: rgba(16, 185, 129, 0.2);
        color: #34D399;
        border: 1px solid rgba(16, 185, 129, 0.4);
        border-radius: 9999px;
        padding: 4px 12px;
        font-size: 0.75rem;
        font-weight: 700;
    }
    .badge-rejected {
        background: rgba(239, 68, 68, 0.2);
        color: #F87171;
        border: 1px solid rgba(239, 68, 68, 0.4);
        border-radius: 9999px;
        padding: 4px 12px;
        font-size: 0.75rem;
        font-weight: 700;
    }
    .badge-auto {
        background: rgba(16, 185, 129, 0.15);
        color: #34D399;
        border: 1px solid rgba(16, 185, 129, 0.3);
        border-radius: 9999px;
        padding: 3px 10px;
        font-size: 0.72rem;
        font-weight: 600;
    }
    .badge-outofstock {
        background: rgba(239, 68, 68, 0.15);
        color: #F87171;
        border: 1px solid rgba(239, 68, 68, 0.3);
        border-radius: 9999px;
        padding: 3px 10px;
        font-size: 0.72rem;
        font-weight: 600;
    }

    /* Trace Timeline */
    .trace-card {
        background: #131A2B;
        border: 1px solid #232D42;
        border-radius: 10px;
        padding: 12px 16px;
        margin-bottom: 8px;
    }
    .trace-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 4px;
    }
    .trace-agent {
        font-size: 0.85rem;
        font-weight: 700;
    }
    .trace-time {
        font-size: 0.75rem;
        color: #64748B;
    }
    .trace-action {
        font-size: 0.85rem;
        font-weight: 600;
        color: #E2E8F0;
        margin-bottom: 3px;
    }
    .trace-details {
        font-size: 0.82rem;
        color: #94A3B8;
    }

    /* Clean Empty State */
    .empty-state-box {
        background: rgba(19, 26, 43, 0.6);
        border: 2px dashed rgba(59, 130, 246, 0.25);
        border-radius: 16px;
        padding: 48px 24px;
        text-align: center;
        margin: 20px 0;
    }
    .empty-state-icon {
        font-size: 3rem;
        margin-bottom: 12px;
    }
    .empty-state-title {
        font-size: 1.25rem;
        font-weight: 700;
        color: #F8FAFC;
        margin-bottom: 6px;
    }
    .empty-state-desc {
        font-size: 0.88rem;
        color: #94A3B8;
        max-width: 500px;
        margin: 0 auto;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# =============================================================================
# 2. SESSION STATE: WALLET & MULTI-AGENT SYSTEM INITIALIZATION
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

if "approval_alert" not in st.session_state:
    st.session_state.approval_alert = None

# Active references
wallet: SafeAgentWallet = st.session_state.wallet
marketplace: Marketplace = st.session_state.marketplace
sellers: Dict[str, SellerAgent] = st.session_state.sellers
approval_center: ApprovalCenter = st.session_state.approval_center
buyer_agent: BuyerAgent = st.session_state.buyer_agent


# =============================================================================
# 3. INTERACTION CALLBACK HANDLERS
# =============================================================================


def handle_agent_purchase(user_query: str) -> None:
    """Dispatches a natural-language purchase directive to the Buyer Agent."""
    if not user_query or not user_query.strip():
        return

    res: PurchaseFlowResult = buyer_agent.execute_purchase(user_query.strip())
    st.session_state.last_agent_result = res

    if res.status == "AWAITING_APPROVAL":
        st.session_state.approval_alert = (
            f"⚠️ Purchase directive '{user_query}' requires human authorization. "
            f"Review it in the Approval Center."
        )


def handle_approval_action(req_id: str, auth_token: str, confirmed: bool = True) -> None:
    """Authorizes and executes a pending approval request."""
    if not confirmed:
        st.session_state.approval_alert = "⚠️ Confirmation required: please check the confirmation checkbox before approving."
        return
    ok, msg, res = approval_center.approve_request(
        request_id=req_id,
        wallet=wallet,
        marketplace=marketplace,
        auth_token=auth_token.strip(),
    )
    if ok and res:
        st.session_state.approval_alert = (
            f"✅ Payment Approved & Executed! TxID: {res.transaction_id} | "
            f"Amount: ${res.amount:.2f} | Remaining Balance: ${res.balance:.2f}"
        )
    else:
        st.session_state.approval_alert = f"❌ Authorization Denied / Failed: {msg}"


def handle_rejection_action(req_id: str, reason: str = "Declined by human reviewer.", confirmed: bool = True) -> None:
    """Rejects a pending approval request safely with $0 deduction."""
    if not confirmed:
        st.session_state.approval_alert = "⚠️ Confirmation required: please check the confirmation checkbox before rejecting."
        return
    ok, msg = approval_center.reject_request(
        request_id=req_id,
        wallet=wallet,
        reason=reason,
    )
    st.session_state.approval_alert = f"🛑 Request Rejected: {msg}"


def handle_reset_all() -> None:
    """Resets wallet, marketplace, approvals, and transaction logs."""
    wallet.reset()
    marketplace.reset_catalog()
    approval_center.clear()
    st.session_state.last_agent_result = None
    st.session_state.approval_alert = "🔄 Wallet & Marketplace reset to $100.00 pristine state."


def handle_reset_rate_limiter() -> None:
    """Clears rate limiter window."""
    wallet.reset_rate_limiter()
    st.session_state.approval_alert = "⏱️ Rate limiter rolling window reset."


def handle_unlock_wallet() -> None:
    """Unlocks wallet."""
    wallet.unlock()
    st.session_state.approval_alert = "🔓 Wallet successfully unlocked."


def handle_toggle_availability(product_id: str) -> None:
    """Toggles product in-stock availability for testing."""
    prod = marketplace.get_product(product_id)
    if prod:
        marketplace.set_availability(product_id, not prod.availability)


# =============================================================================
# 4. SIDEBAR NAVIGATION & SYSTEM CONTROLS
# =============================================================================

with st.sidebar:
    st.markdown(
        """
        <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 8px;">
            <span style="font-size: 1.8rem;">🛡️</span>
            <div>
                <div style="font-size: 1.15rem; font-weight: 800; color: #FFFFFF;">SafeAgent Wallet</div>
                <div style="font-size: 0.72rem; color: #60A5FA; font-weight: 600;">Stripe Agent Security v2.0</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    pending_cnt = approval_center.get_pending_count()
    approval_nav_label = f"🛡️ Approval Center ({pending_cnt})" if pending_cnt > 0 else "🛡️ Approval Center"

    nav_selection = st.radio(
        "Navigation",
        [
            "📊 Dashboard",
            "🛒 Marketplace",
            approval_nav_label,
            "📋 Transaction History",
            "⚙️ Security Settings",
        ],
        label_visibility="collapsed",
    )

    st.divider()

    # Diagnostics Meter
    st.markdown("#### 📡 System Status")
    status_text = "🔴 LOCKED" if wallet.is_locked else "🟢 ACTIVE"
    st.markdown(f"**Wallet State:** `{status_text}`")
    st.markdown(f"**Pending Approvals:** `{pending_cnt}` requests")
    current_requests = wallet._rate_limiter.get_request_count()
    st.markdown(f"**Rate Limit:** `{current_requests} / {config.RATE_LIMIT_MAX_REQUESTS}` in 60s")
    failed_attempts = wallet.invalid_auth_attempts
    st.markdown(f"**Failed Auth:** `{failed_attempts} / {config.MAX_INVALID_AUTH_ATTEMPTS}` attempts")

    st.divider()

    st.markdown("#### ⚙️ Developer Shortcuts")
    col_s1, col_s2 = st.columns(2)
    with col_s1:
        st.button("🔄 Reset All", on_click=handle_reset_all, width="stretch", help="Reset balance and history")
    with col_s2:
        st.button("⏱️ Reset Rate", on_click=handle_reset_rate_limiter, width="stretch", help="Clear rate limit window")

    if wallet.is_locked:
        st.warning("⚠️ Wallet is locked.")
        st.button("🔓 Admin Unlock", on_click=handle_unlock_wallet, type="primary", width="stretch")


# =============================================================================
# 5. HEADER & WALLET OVERVIEW CARDS (PROMINENT FINTECH METRICS)
# =============================================================================

h_col1, h_col2 = st.columns([3, 1])
with h_col1:
    st.title("SafeAgent Wallet")
    st.markdown("##### Secure AI-powered payment wallet • Problem Statement #7: Stripe Agents That Can Pay")

with h_col2:
    st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
    st.markdown(
        """
        <div style="background: rgba(59, 130, 246, 0.12); border: 1px solid rgba(59, 130, 246, 0.35); border-radius: 10px; padding: 10px 14px; text-align: center;">
            <span style="color: #60A5FA; font-size: 0.8rem; font-weight: 800;">🟡 SIMULATED WALLET</span><br>
            <span style="color: #94A3B8; font-size: 0.72rem;">CommitCon Sandbox • No Real Funds</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.write("")

# Wallet Overview Cards (Live values from SafeAgentWallet)
col_m1, col_m2, col_m3, col_m4 = st.columns(4)

with col_m1:
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-label">Available Balance</div>
            <div class="metric-value" style="color: #10B981;">${wallet.balance:.2f}</div>
            <div class="metric-subtext">Initial starting: ${wallet._initial_balance:.2f}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with col_m2:
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-label">Total Spent</div>
            <div class="metric-value" style="color: #F59E0B;">${wallet.total_spent:.2f}</div>
            <div class="metric-subtext">Cumulative spending</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with col_m3:
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-label">Remaining Spending Limit</div>
            <div class="metric-value" style="color: #38BDF8;">${wallet.remaining_spending_limit:.2f}</div>
            <div class="metric-subtext">Lifetime limit: ${wallet.spending_limit:.2f}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with col_m4:
    stat_color = "#EF4444" if wallet.is_locked else "#34D399"
    stat_lbl = "LOCKED" if wallet.is_locked else "ACTIVE"
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-label">Wallet Status</div>
            <div class="metric-value" style="color: {stat_color};">{stat_lbl}</div>
            <div class="metric-subtext">Failed auth: {wallet.invalid_auth_attempts} / {config.MAX_INVALID_AUTH_ATTEMPTS}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.write("")

# Action Alert Feedback Banner
if st.session_state.approval_alert:
    st.info(st.session_state.approval_alert)
    st.session_state.approval_alert = None


# =============================================================================
# 6. VIEW: HUMAN APPROVAL CENTER (SECTION D - CORE REQUIREMENT)
# =============================================================================

if "Approval Center" in nav_selection:
    st.markdown("## 🛡️ Human Approval Center")
    st.markdown(
        "Authorize or reject autonomous agent transactions that strictly exceed the "
        f"**${config.AUTO_PAYMENT_THRESHOLD:.2f}** automatic payment policy."
    )

    pending_list = approval_center.get_pending_requests()

    if not pending_list:
        st.markdown(
            """
            <div class="empty-state-box">
                <div class="empty-state-icon">✅</div>
                <div class="empty-state-title">No pending approvals. Your wallet is up to date.</div>
                <div class="empty-state-desc">
                    When the Buyer Agent initiates a purchase exceeding $10.00, it will appear here for your review and authorization.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.caption("💡 **Quick Test Tip:** Go to the Dashboard or Marketplace and click **Buy Bluetooth Headphones ($15.00)** to generate a pending approval.")
    else:
        st.markdown(f"**Pending Authorizations ({len(pending_list)}):**")

        for req in pending_list:
            safe_pname = html.escape(req.product_name)
            safe_sname = html.escape(req.seller_name)
            safe_bagent = html.escape(req.buyer_agent)
            safe_reqid = html.escape(req.request_id)
            safe_desc = html.escape(req.description)
            safe_reason = html.escape(req.reason)

            desc_html = (
                f"<div style='font-size: 0.88rem; color: #94A3B8; margin-bottom: 12px;'><b>Description:</b> {safe_desc}</div>"
                if safe_desc
                else ""
            )

            st.markdown(
                f"""
                <div class="approval-card">
                    <div class="approval-header">
                        <div class="approval-title">
                            <span>{req.image_icon}</span>
                            <span>{safe_pname}</span>
                            <span class="badge-pending">{req.status}</span>
                        </div>
                        <div class="approval-amount">${req.amount:.2f}</div>
                    </div>
                    {desc_html}
                    <div class="approval-meta-grid">
                        <div>
                            <div class="meta-item-label">Request ID</div>
                            <div class="meta-item-value"><code>{safe_reqid}</code></div>
                        </div>
                        <div>
                            <div class="meta-item-label">Amount</div>
                            <div class="meta-item-value" style="color: #38BDF8;">${req.amount:.2f}</div>
                        </div>
                        <div>
                            <div class="meta-item-label">Status</div>
                            <div class="meta-item-value"><span class="badge-pending">{req.status}</span></div>
                        </div>
                        <div>
                            <div class="meta-item-label">Timestamp</div>
                            <div class="meta-item-value">🕒 {req.timestamp}</div>
                        </div>
                        <div>
                            <div class="meta-item-label">Buyer Agent</div>
                            <div class="meta-item-value">🤖 {safe_bagent}</div>
                        </div>
                        <div>
                            <div class="meta-item-label">Merchant / Seller</div>
                            <div class="meta-item-value">🏪 {safe_sname}</div>
                        </div>
                    </div>
                    <div class="approval-reason-box">
                        <b>Authorization Policy:</b> {safe_reason}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # Interactive Authorization Control
            col_act1, col_act2, col_act3 = st.columns([2, 1, 1])

            with col_act1:
                token_val = st.text_input(
                    "Human Authorization Token / PIN:",
                    value=config.DEFAULT_AUTH_TOKEN,
                    key=f"token_{req.request_id}",
                    help="Default valid token: COMMITCON-SECURE-2026. Change to test invalid authorization rejection.",
                )
                confirm_auth = st.checkbox(
                    "I confirm authorization decision for this transaction",
                    value=True,
                    key=f"chk_conf_{req.request_id}",
                    help="Safety confirmation requirement",
                )

            with col_act2:
                st.write("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                st.button(
                    "✅ APPROVE",
                    key=f"btn_appr_{req.request_id}",
                    on_click=handle_approval_action,
                    args=(req.request_id, token_val, confirm_auth),
                    type="primary",
                    width="stretch",
                    disabled=wallet.is_locked,
                    help="Authorizes payment through SafeAgentWallet after security checks.",
                )

            with col_act3:
                st.write("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                st.button(
                    "❌ REJECT",
                    key=f"btn_rej_{req.request_id}",
                    on_click=handle_rejection_action,
                    args=(req.request_id, "Declined by human reviewer.", confirm_auth),
                    width="stretch",
                    help="Rejects the request. Deducts $0 from the wallet.",
                )

            st.write("")


# =============================================================================
# 7. VIEW: DASHBOARD (OVERVIEW & AUTONOMOUS BUYER AGENT)
# =============================================================================

elif "Dashboard" in nav_selection:
    st.markdown("## 📊 Autonomous Agent Operations")

    # Alert if approvals pending
    p_cnt = approval_center.get_pending_count()
    if p_cnt > 0:
        st.warning(f"⚠️ You have **{p_cnt} pending payment authorization(s)** waiting in the Human Approval Center.")

    st.markdown(
        """
        <div style="background: rgba(19, 26, 43, 0.7); border: 1px solid rgba(59, 130, 246, 0.2); border-radius: 12px; padding: 20px; margin-bottom: 24px;">
            <h4 style="margin: 0 0 6px 0; color: #F8FAFC;">🤖 Buyer Agent Directive Terminal</h4>
            <span style="font-size: 0.88rem; color: #94A3B8;">
                Instruct the autonomous Buyer Agent to search the marketplace, negotiate with Seller Agents, and route payments through SafeAgentWallet.
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    d_col1, d_col2 = st.columns([3, 1])
    with d_col1:
        agent_input = st.text_input(
            "Enter purchase directive:",
            value="Buy Bluetooth Headphones",
            placeholder="e.g. Buy Bluetooth Headphones, Buy USB-C Cable...",
            key="dash_prompt_input",
        )
    with d_col2:
        st.write("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        st.button(
            "🚀 Execute Directive",
            on_click=handle_agent_purchase,
            args=(agent_input,),
            type="primary",
            width="stretch",
            disabled=wallet.is_locked,
        )

    st.markdown("**Quick Test Scenarios:**")
    q1, q2, q3, q4 = st.columns(4)
    with q1:
        st.button("⚡ Cable ($4.50 - Auto)", on_click=handle_agent_purchase, args=("Buy USB-C Cable",), width="stretch")
    with q2:
        st.button("⚡ Mouse ($9.00 - Auto)", on_click=handle_agent_purchase, args=("Buy Wireless Mouse",), width="stretch")
    with q3:
        st.button("👤 Headphones ($15.00 - Approval)", on_click=handle_agent_purchase, args=("Buy Bluetooth Headphones",), width="stretch")
    with q4:
        st.button("❓ Invalid Product", on_click=handle_agent_purchase, args=("Buy Mechanical Keyboard",), width="stretch")

    st.write("")

    # Display Last Agent Result & Activity Trace
    if st.session_state.last_agent_result:
        res: PurchaseFlowResult = st.session_state.last_agent_result
        safe_msg = html.escape(res.summary_message)

        if res.success:
            st.markdown(
                f"""
                <div style="background: rgba(16, 185, 129, 0.12); border: 1px solid #10B981; border-radius: 10px; padding: 14px 18px; margin-bottom: 16px;">
                    <span style="font-size: 1.1rem; font-weight: 700; color: #34D399;">✅ Purchase Completed Successfully</span>
                    <div style="font-size: 0.9rem; color: #E2E8F0; margin-top: 4px;">{safe_msg}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        elif res.status == "AWAITING_APPROVAL":
            st.markdown(
                f"""
                <div style="background: rgba(245, 158, 11, 0.12); border: 1px solid #F59E0B; border-radius: 10px; padding: 14px 18px; margin-bottom: 16px;">
                    <span style="font-size: 1.1rem; font-weight: 700; color: #FBBF24;">⏸️ Queued in Human Approval Center</span>
                    <div style="font-size: 0.9rem; color: #FEF3C7; margin-top: 4px;">{safe_msg}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"""
                <div style="background: rgba(239, 68, 68, 0.12); border: 1px solid #EF4444; border-radius: 10px; padding: 14px 18px; margin-bottom: 16px;">
                    <span style="font-size: 1.1rem; font-weight: 700; color: #F87171;">❌ Purchase Rejected / Halted</span>
                    <div style="font-size: 0.9rem; color: #FECACA; margin-top: 4px;">{safe_msg}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.markdown("#### 📡 Agent Trace Log")
        for step in res.trace:
            agent_color = "#38BDF8"
            if "Seller" in step.agent:
                agent_color = "#A78BFA"
            elif "Wallet" in step.agent:
                agent_color = "#34D399" if "SUCCESS" in step.action else "#F87171"

            st.markdown(
                f"""
                <div class="trace-card">
                    <div class="trace-header">
                        <span class="trace-agent" style="color: {agent_color};">● {html.escape(step.agent)}</span>
                        <span class="trace-time">{step.timestamp}</span>
                    </div>
                    <div class="trace-action">{html.escape(step.action)}</div>
                    <div class="trace-details">{html.escape(step.details)}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


# =============================================================================
# 8. VIEW: MARKETPLACE (SECTION C)
# =============================================================================

elif "Marketplace" in nav_selection:
    st.markdown("## 🛒 Simulated Marketplace")
    st.caption("CommitCon initial catalog connected to three independent Seller Agents.")

    m_products = marketplace.get_all_products()
    m_cols = st.columns(3)

    for idx, prod in enumerate(m_products):
        seller_obj = sellers.get(prod.seller_id)
        s_name = seller_obj.name if seller_obj else prod.seller_id

        icon = "🎧" if "Headphones" in prod.name else ("🖱️" if "Mouse" in prod.name else "🔌")

        with m_cols[idx % 3]:
            if not prod.availability:
                b_badge = "<span class='badge-outofstock'>Out of Stock</span>"
            elif prod.price <= config.AUTO_PAYMENT_THRESHOLD:
                b_badge = "<span class='badge-auto'>⚡ Automatic (&le; $10)</span>"
            else:
                b_badge = "<span class='badge-pending'>👤 Approval Required (&gt; $10)</span>"

            st.markdown(
                f"""
                <div class="product-box">
                    <div>
                        <div class="product-icon">{icon}</div>
                        {b_badge}
                        <div class="product-title">{html.escape(prod.name)}</div>
                        <div class="product-seller">Seller: <b>{html.escape(s_name)}</b></div>
                        <div class="product-desc">{html.escape(prod.description)}</div>
                    </div>
                    <div>
                        <div class="product-price">${prod.price:.2f}</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            p_col1, p_col2 = st.columns([2, 1])
            with p_col1:
                st.button(
                    f"Buy via Agent",
                    key=f"mp_buy_{prod.product_id}",
                    on_click=handle_agent_purchase,
                    args=(f"Buy {prod.name}",),
                    width="stretch",
                    disabled=wallet.is_locked or not prod.availability,
                )
            with p_col2:
                t_label = "Mark OOS" if prod.availability else "Restock"
                st.button(
                    t_label,
                    key=f"mp_oos_{prod.product_id}",
                    on_click=handle_toggle_availability,
                    args=(prod.product_id,),
                    width="stretch",
                    help="Toggle in-stock status",
                )


# =============================================================================
# 9. VIEW: TRANSACTION HISTORY (SECTION E)
# =============================================================================

elif "Transaction History" in nav_selection:
    st.markdown("## 📋 Transaction History & Security Audit Ledger")
    st.caption("Live, immutable audit ledger persisted directly to data/transactions.json.")

    history = wallet.get_transaction_history()

    # Gather any active pending requests
    pending_list = approval_center.get_pending_requests()

    if not history and not pending_list:
        st.markdown(
            """
            <div class="empty-state-box">
                <div class="empty-state-icon">📋</div>
                <div class="empty-state-title">No Transactions Recorded</div>
                <div class="empty-state-desc">Transactions initiated by the Buyer Agent or approved by humans will be recorded here.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        # Filter options
        f_col1, f_col2 = st.columns([1, 3])
        with f_col1:
            filter_status = st.selectbox(
                "Filter Status",
                ["All", "APPROVED", "REJECTED", "PENDING", "FAILED"],
                key="tx_filter",
            )

        formatted_rows = []

        # Include pending requests first when filter allows
        if filter_status in ("All", "PENDING"):
            for req in pending_list:
                formatted_rows.append(
                    {
                        "Transaction ID": req.order_id or req.request_id,
                        "Product": f"{req.product_name} ({req.seller_name})",
                        "Amount": f"${float(req.amount):.2f}",
                        "Date and time": req.timestamp[:19],
                        "Status": "🟡 PENDING",
                        "Approval/rejection outcome": "Awaiting human authorization in Approval Center",
                        "Balance After": f"${float(wallet.balance):.2f}",
                    }
                )

        for tx in reversed(history):
            raw_status = tx.get("status", "")
            is_success = raw_status == config.STATUS_SUCCESS
            reason_lower = tx.get("reason", "").lower()

            if is_success:
                status_cat = "APPROVED"
                status_badge = "🟢 APPROVED"
            elif "declined" in reason_lower or "human reviewer" in reason_lower or "rejected by human" in reason_lower:
                status_cat = "REJECTED"
                status_badge = "🔴 REJECTED"
            else:
                status_cat = "FAILED"
                status_badge = "⚠️ FAILED"

            if filter_status != "All" and filter_status != status_cat:
                continue

            formatted_rows.append(
                {
                    "Transaction ID": tx.get("transaction_id", ""),
                    "Product": tx.get("recipient", ""),
                    "Amount": f"${float(tx.get('amount', 0)):.2f}",
                    "Date and time": tx.get("timestamp", "")[:19].replace("T", " "),
                    "Status": status_badge,
                    "Approval/rejection outcome": tx.get("reason", ""),
                    "Balance After": f"${float(tx.get('balance_after', 0)):.2f}",
                }
            )

        if not formatted_rows:
            st.info(f"No transactions found matching filter '{filter_status}'.")
        else:
            st.dataframe(
                formatted_rows,
                width="stretch",
                hide_index=True,
            )


# =============================================================================
# 10. VIEW: SECURITY SETTINGS & RULES (SECTION F)
# =============================================================================

elif "Security Settings" in nav_selection:
    st.markdown("## ⚙️ Security Rules & Policies")
    st.caption("Live security configuration loaded directly from config.py and SafeAgentWallet.")

    rule_c1, rule_c2 = st.columns(2)
    with rule_c1:
        st.markdown(
            f"""
            <div style="background: #141A24; border-left: 3px solid #3B82F6; padding: 14px 16px; border-radius: 0 8px 8px 0; margin-bottom: 12px;">
                <b style="color: #60A5FA;">1. Initial Virtual Balance:</b><br>
                <code>${config.INITIAL_BALANCE:.2f}</code> starting virtual funds in wallet.
            </div>
            <div style="background: #141A24; border-left: 3px solid #3B82F6; padding: 14px 16px; border-radius: 0 8px 8px 0; margin-bottom: 12px;">
                <b style="color: #60A5FA;">2. Lifetime Spending Limit:</b><br>
                <code>${config.LIFETIME_SPENDING_LIMIT:.2f}</code> maximum cumulative spending allowance across all transactions.
            </div>
            <div style="background: #141A24; border-left: 3px solid #3B82F6; padding: 14px 16px; border-radius: 0 8px 8px 0; margin-bottom: 12px;">
                <b style="color: #60A5FA;">3. Automatic Payment Threshold:</b><br>
                Payments up to and including <code>${config.AUTO_PAYMENT_THRESHOLD:.2f}</code> execute automatically without approval.
            </div>
            """,
            unsafe_allow_html=True,
        )
    with rule_c2:
        st.markdown(
            f"""
            <div style="background: #141A24; border-left: 3px solid #3B82F6; padding: 14px 16px; border-radius: 0 8px 8px 0; margin-bottom: 12px;">
                <b style="color: #60A5FA;">4. Human Approval Requirement:</b><br>
                Payments strictly above <code>${config.AUTO_PAYMENT_THRESHOLD:.2f}</code> require explicit human review and authorization.
            </div>
            <div style="background: #141A24; border-left: 3px solid #3B82F6; padding: 14px 16px; border-radius: 0 8px 8px 0; margin-bottom: 12px;">
                <b style="color: #60A5FA;">5. Rate Limiting Protection:</b><br>
                Maximum <code>{config.RATE_LIMIT_MAX_REQUESTS} requests per rolling {int(config.RATE_LIMIT_WINDOW_SECONDS)} seconds</code> (rejected requests count too).
            </div>
            <div style="background: #141A24; border-left: 3px solid #3B82F6; padding: 14px 16px; border-radius: 0 8px 8px 0; margin-bottom: 12px;">
                <b style="color: #60A5FA;">6. Anti-Tamper Lockout:</b><br>
                Wallet automatically locks after <code>{config.MAX_INVALID_AUTH_ATTEMPTS} invalid authorization attempts</code>.
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.write("")
    st.markdown("#### 🧪 Manual Security Injection Tester")
    st.caption("Inject custom transaction payloads to test boundaries directly against the wallet:")

    t_col1, t_col2 = st.columns(2)
    with t_col1:
        inj_recip = st.text_input("Recipient", value="Test Merchant", key="inj_rec")
        inj_amt_str = st.text_input("Amount ($)", value="15.00", key="inj_amt")
    with t_col2:
        inj_appr = st.selectbox("Human Approval Flag", ["None", "Approved (True)", "Rejected (False)"], key="inj_app")
        inj_tok = st.text_input("Token", value=config.DEFAULT_AUTH_TOKEN, key="inj_tk")

    if st.button("Inject Payment Directly to Wallet", width="stretch"):
        try:
            amt = Decimal(inj_amt_str.strip())
            appr_flag = True if "Approved" in inj_appr else (False if "Rejected" in inj_appr else None)
            res = wallet.execute_payment(
                amount=amt,
                recipient=inj_recip,
                human_approved=appr_flag,
                auth_token=inj_tok if appr_flag else None,
            )
            if res.success:
                st.success(f"Payment Succeeded! TxID: {res.transaction_id} | Balance: ${res.balance:.2f}")
            else:
                st.error(f"Payment Rejected: {res.reason}")
        except Exception as e:
            st.error(f"Error executing injection: {e}")
