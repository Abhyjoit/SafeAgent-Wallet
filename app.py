"""
app.py - SafeAgent Wallet & Multi-Agent Marketplace Dashboard
CommitCon Hackathon - Hours 7–10: Multi-Agent Marketplace Integration

Features:
- Buyer Agent: Ingests user directives, searches marketplace, contacts sellers, forwards payments.
- 3 Seller Agents: CableCraft (USB-C), ErgoGear (Mouse), SoundWave (Headphones).
- Marketplace: 3 core products ($4.50, $9.00, $15.00) with stock availability controls.
- SafeAgentWallet: Multi-layered security rules, rate limiting, and human approval enforcement.
- Visual Agent Trace: Real-time step-by-step communication logging.
"""

from decimal import Decimal
import html
from typing import Any, Dict, List, Optional

import streamlit as st

from buyer_agent import BuyerAgent
import config
from marketplace import Marketplace, Product
from purchase import AgentTraceStep, PurchaseFlowResult
from seller_agent import SellerAgent, create_default_sellers
from wallet import PaymentResult, SafeAgentWallet

# =============================================================================
# 1. PAGE CONFIGURATION & STYLES
# =============================================================================

st.set_page_config(
    page_title="SafeAgent Wallet - Multi-Agent Marketplace",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    /* Metric Cards */
    .metric-card {
        background: #131722;
        border: 1px solid #232936;
        border-radius: 12px;
        padding: 16px 18px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.2);
    }
    .metric-label {
        font-size: 0.8rem;
        color: #8E9BAE;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 4px;
    }
    .metric-value {
        font-size: 1.75rem;
        font-weight: 700;
        color: #FFFFFF;
        line-height: 1.2;
    }
    .metric-subtext {
        font-size: 0.78rem;
        color: #64748B;
        margin-top: 4px;
    }
    
    /* Product Cards */
    .product-box {
        background: #181E2A;
        border: 1px solid #283347;
        border-radius: 14px;
        padding: 20px;
        min-height: 230px;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        margin-bottom: 12px;
        transition: transform 0.15s ease, border-color 0.15s ease;
    }
    .product-box:hover {
        border-color: #3B82F6;
        transform: translateY(-2px);
    }
    .product-icon {
        font-size: 2.2rem;
        margin-bottom: 8px;
    }
    .product-title {
        font-size: 1.15rem;
        font-weight: 700;
        color: #F8FAFC;
        margin-bottom: 4px;
    }
    .product-desc {
        font-size: 0.84rem;
        color: #94A3B8;
        min-height: 42px;
        margin-bottom: 10px;
    }
    .product-price {
        font-size: 1.4rem;
        font-weight: 800;
        color: #38BDF8;
        margin-bottom: 6px;
    }
    .product-seller {
        font-size: 0.78rem;
        color: #A5B4FC;
        margin-bottom: 8px;
    }
    .badge-auto {
        display: inline-block;
        background: rgba(16, 185, 129, 0.15);
        color: #34D399;
        border: 1px solid rgba(16, 185, 129, 0.3);
        border-radius: 9999px;
        padding: 3px 10px;
        font-size: 0.72rem;
        font-weight: 600;
        margin-bottom: 10px;
    }
    .badge-approval {
        display: inline-block;
        background: rgba(245, 158, 11, 0.15);
        color: #FBBF24;
        border: 1px solid rgba(245, 158, 11, 0.3);
        border-radius: 9999px;
        padding: 3px 10px;
        font-size: 0.72rem;
        font-weight: 600;
        margin-bottom: 10px;
    }
    .badge-outofstock {
        display: inline-block;
        background: rgba(239, 68, 68, 0.15);
        color: #F87171;
        border: 1px solid rgba(239, 68, 68, 0.3);
        border-radius: 9999px;
        padding: 3px 10px;
        font-size: 0.72rem;
        font-weight: 600;
        margin-bottom: 10px;
    }
    
    /* Trace Step Container */
    .trace-card {
        background: #141A24;
        border: 1px solid #283347;
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
        color: #60A5FA;
    }
    .trace-time {
        font-size: 0.75rem;
        color: #64748B;
    }
    .trace-action {
        font-size: 0.82rem;
        font-weight: 600;
        color: #E2E8F0;
        margin-bottom: 4px;
    }
    .trace-details {
        font-size: 0.82rem;
        color: #94A3B8;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# =============================================================================
# 2. SESSION STATE: WALLET & MULTI-AGENT SYSTEM INITIALIZATION
# =============================================================================
# Preserves the same Wallet, Marketplace, Sellers, and Buyer Agent instances
# across all Streamlit script runs.

if "wallet" not in st.session_state:
    st.session_state.wallet = SafeAgentWallet(load_existing=True)

if "marketplace" not in st.session_state:
    st.session_state.marketplace = Marketplace()

if "sellers" not in st.session_state:
    st.session_state.sellers = create_default_sellers()

if "buyer_agent" not in st.session_state:
    st.session_state.buyer_agent = BuyerAgent(
        marketplace=st.session_state.marketplace,
        wallet=st.session_state.wallet,
        sellers=st.session_state.sellers,
    )

if "last_agent_result" not in st.session_state:
    st.session_state.last_agent_result = None

if "pending_agent_approval" not in st.session_state:
    st.session_state.pending_agent_approval = None

# Active references
wallet: SafeAgentWallet = st.session_state.wallet
marketplace: Marketplace = st.session_state.marketplace
sellers: Dict[str, SellerAgent] = st.session_state.sellers
buyer_agent: BuyerAgent = st.session_state.buyer_agent


# =============================================================================
# 3. INTERACTION CALLBACK HANDLERS
# =============================================================================


def handle_agent_purchase(user_query: str) -> None:
    """Executes a purchase request through the Buyer Agent."""
    if not user_query or not user_query.strip():
        return

    res: PurchaseFlowResult = buyer_agent.execute_purchase(user_query.strip())
    st.session_state.last_agent_result = res

    if res.status == "AWAITING_APPROVAL":
        st.session_state.pending_agent_approval = {
            "query": user_query.strip(),
            "product_name": res.product.name if res.product else "Unknown",
            "price": res.product.price if res.product else Decimal("0.00"),
            "order_id": res.order_id,
        }
    else:
        st.session_state.pending_agent_approval = None


def handle_agent_approval(token: str) -> None:
    """Provides human approval token for a pending payment exceeding $10."""
    pending = st.session_state.pending_agent_approval
    if not pending:
        return

    res: PurchaseFlowResult = buyer_agent.execute_purchase(
        user_request=pending["query"],
        human_approved=True,
        auth_token=token.strip(),
    )
    st.session_state.last_agent_result = res
    st.session_state.pending_agent_approval = None


def handle_agent_rejection() -> None:
    """Provides normal human rejection for a pending payment (does not lock wallet)."""
    pending = st.session_state.pending_agent_approval
    if not pending:
        return

    res: PurchaseFlowResult = buyer_agent.execute_purchase(
        user_request=pending["query"],
        human_approved=False,
    )
    st.session_state.last_agent_result = res
    st.session_state.pending_agent_approval = None


def handle_cancel_approval() -> None:
    """Cancels pending approval prompt."""
    st.session_state.pending_agent_approval = None


def handle_reset_all() -> None:
    """Resets wallet and marketplace to pristine state."""
    wallet.reset()
    marketplace.reset_catalog()
    st.session_state.last_agent_result = None
    st.session_state.pending_agent_approval = None


def handle_reset_rate_limiter() -> None:
    """Clears rate limiter window."""
    wallet.reset_rate_limiter()


def handle_unlock_wallet() -> None:
    """Unlocks wallet."""
    wallet.unlock()


def handle_toggle_availability(product_id: str) -> None:
    """Toggles product in-stock availability for testing scenario 4."""
    prod = marketplace.get_product(product_id)
    if prod:
        marketplace.set_availability(product_id, not prod.availability)


# =============================================================================
# 4. SIDEBAR: AGENT & SECURITY DIAGNOSTICS
# =============================================================================

with st.sidebar:
    st.markdown("### 🛡️ SafeAgent Security")
    st.caption("CommitCon Hackathon • AI Payment Guard")

    # Status Indicators
    status_text = "🔴 LOCKED" if wallet.is_locked else "🟢 ACTIVE"
    st.markdown(f"**Wallet State:** `{status_text}`")

    # Rate Limiting Tracker
    current_requests = wallet._rate_limiter.get_request_count()
    st.markdown(
        f"**Rate Limit:** `{current_requests} / {config.RATE_LIMIT_MAX_REQUESTS}` in 60s"
    )

    # Failed Auth Attempts
    failed_attempts = wallet.invalid_auth_attempts
    st.markdown(
        f"**Failed Auth Attempts:** `{failed_attempts} / {config.MAX_INVALID_AUTH_ATTEMPTS}`"
    )

    st.divider()

    st.markdown("#### 🤖 Active Seller Agents")
    for s in sellers.values():
        p = marketplace.get_product(s.product_id)
        stock_status = "In Stock" if (p and p.availability) else "OUT OF STOCK"
        st.markdown(f"- **{s.name}** (`{s.seller_id}`): {stock_status}")

    st.divider()

    st.markdown("#### ⚙️ Developer Controls")
    col_rst1, col_rst2 = st.columns(2)
    with col_rst1:
        st.button(
            "🔄 Reset All",
            on_click=handle_reset_all,
            width="stretch",
            help="Reset wallet to $100 and reset catalog",
        )

    with col_rst2:
        st.button(
            "⏱️ Reset Rate",
            on_click=handle_reset_rate_limiter,
            width="stretch",
            help="Clear rolling rate limit timestamps",
        )

    if wallet.is_locked:
        st.warning("⚠️ Wallet is locked due to 3 invalid auth attempts.")
        st.button(
            "🔓 Admin Unlock",
            on_click=handle_unlock_wallet,
            type="primary",
            width="stretch",
        )


# =============================================================================
# 5. DASHBOARD HEADER
# =============================================================================

header_col1, header_col2 = st.columns([3, 1])
with header_col1:
    st.title("SafeAgent Wallet")
    st.markdown("##### Secure AI-powered payment wallet • Multi-Agent Marketplace")

with header_col2:
    st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
    st.markdown(
        """
        <div style="background: rgba(59, 130, 246, 0.1); border: 1px solid rgba(59, 130, 246, 0.3); border-radius: 8px; padding: 8px 12px; text-align: center;">
            <span style="color: #60A5FA; font-size: 0.8rem; font-weight: 700;">🟡 SIMULATED WALLET</span><br>
            <span style="color: #94A3B8; font-size: 0.75rem;">Demo Environment • No Real Funds</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.write("")


# =============================================================================
# 6. WALLET OVERVIEW (REAL-TIME STATE)
# =============================================================================

st.markdown("### 💼 Wallet Overview")

col1, col2, col3, col4 = st.columns(4)

with col1:
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

with col2:
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

with col3:
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

with col4:
    status_label = "LOCKED" if wallet.is_locked else "ACTIVE"
    status_style = "color: #EF4444;" if wallet.is_locked else "color: #34D399;"
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-label">Wallet Status</div>
            <div class="metric-value" style="{status_style}">{status_label}</div>
            <div class="metric-subtext">Failed auth: {wallet.invalid_auth_attempts} / {config.MAX_INVALID_AUTH_ATTEMPTS}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.write("")


# =============================================================================
# 7. SPENDING RULES SECTION
# =============================================================================

with st.expander("📜 Spending Rules & Security Policies", expanded=False):
    r_col1, r_col2 = st.columns(2)
    with r_col1:
        st.markdown(
            """
            <div style="background: #141A24; border-left: 3px solid #3B82F6; padding: 10px 14px; border-radius: 0 8px 8px 0; margin-bottom: 8px; font-size: 0.88rem;">
                <b>1. Starting Balance:</b> <code>$100.00</code> initial virtual funds.
            </div>
            <div style="background: #141A24; border-left: 3px solid #3B82F6; padding: 10px 14px; border-radius: 0 8px 8px 0; margin-bottom: 8px; font-size: 0.88rem;">
                <b>2. Lifetime Spending Limit:</b> Maximum <code>$80.00</code> total spending allowance.
            </div>
            <div style="background: #141A24; border-left: 3px solid #3B82F6; padding: 10px 14px; border-radius: 0 8px 8px 0; margin-bottom: 8px; font-size: 0.88rem;">
                <b>3. Automatic Payment Threshold:</b> Payments up to and including <code>$10.00</code> execute automatically without approval.
            </div>
            """,
            unsafe_allow_html=True,
        )
    with r_col2:
        st.markdown(
            f"""
            <div style="background: #141A24; border-left: 3px solid #3B82F6; padding: 10px 14px; border-radius: 0 8px 8px 0; margin-bottom: 8px; font-size: 0.88rem;">
                <b>4. Human Approval:</b> Payments strictly above <code>$10.00</code> require human approval.
            </div>
            <div style="background: #141A24; border-left: 3px solid #3B82F6; padding: 10px 14px; border-radius: 0 8px 8px 0; margin-bottom: 8px; font-size: 0.88rem;">
                <b>5. Rate Limiting:</b> Maximum <code>3 payment requests per 60 seconds</code> (rejected requests count too).
            </div>
            <div style="background: #141A24; border-left: 3px solid #3B82F6; padding: 10px 14px; border-radius: 0 8px 8px 0; margin-bottom: 8px; font-size: 0.88rem;">
                <b>6. Anti-Tamper Lockout:</b> Wallet locks after <code>3 invalid authorization attempts</code>.
            </div>
            """,
            unsafe_allow_html=True,
        )

st.write("")


# =============================================================================
# 8. PART 6: BUYER AGENT INTERACTION INTERFACE
# =============================================================================

st.markdown("### 🤖 Autonomous Buyer Agent")
st.caption(
    "Instruct the Buyer Agent to autonomously search the marketplace, negotiate with Seller Agents, and route payments through SafeAgentWallet."
)

agent_col1, agent_col2 = st.columns([3, 1])

with agent_col1:
    user_prompt = st.text_input(
        "Enter purchase instruction:",
        value="Buy Bluetooth Headphones",
        placeholder="e.g. Buy Bluetooth Headphones, Buy USB-C Cable, Buy Wireless Mouse...",
        key="agent_prompt_input",
    )

with agent_col2:
    st.write("<div style='height: 28px;'></div>", unsafe_allow_html=True)
    st.button(
        "🚀 Submit to Buyer Agent",
        on_click=handle_agent_purchase,
        args=(user_prompt,),
        type="primary",
        width="stretch",
        disabled=wallet.is_locked,
    )

# Quick demonstration sample buttons
st.markdown("**Quick Test Scenarios:**")
q_col1, q_col2, q_col3, q_col4 = st.columns(4)
with q_col1:
    st.button(
        "⚡ Cable ($4.50 - Auto)",
        on_click=handle_agent_purchase,
        args=("Buy USB-C Cable",),
        width="stretch",
    )
with q_col2:
    st.button(
        "⚡ Mouse ($9.00 - Auto)",
        on_click=handle_agent_purchase,
        args=("Buy Wireless Mouse",),
        width="stretch",
    )
with q_col3:
    st.button(
        "👤 Headphones ($15.00 - Approval)",
        on_click=handle_agent_purchase,
        args=("Buy Bluetooth Headphones",),
        width="stretch",
    )
with q_col4:
    st.button(
        "❓ Unknown Product",
        on_click=handle_agent_purchase,
        args=("Buy Laptop Stand",),
        width="stretch",
    )

st.write("")


# =============================================================================
# 9. HUMAN APPROVAL DIALOG (IF TRIGGERED BY AGENT)
# =============================================================================

if st.session_state.pending_agent_approval is not None:
    pending = st.session_state.pending_agent_approval
    p_name = html.escape(pending["product_name"])
    p_price = pending["price"]

    st.markdown(
        f"""
        <div style="background: #1C1917; border: 2px solid #F59E0B; border-radius: 12px; padding: 20px; margin-bottom: 25px;">
            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
                <span style="font-size: 1.2rem; font-weight: 800; color: #FBBF24;">⚠️ Human Approval Required</span>
                <span style="background: rgba(245, 158, 11, 0.2); color: #FBBF24; padding: 3px 10px; border-radius: 6px; font-weight: 700; font-size: 0.8rem;">Amount &gt; $10.00</span>
            </div>
            <p style="color: #D6D3D1; font-size: 0.95rem; margin-bottom: 12px;">
                The Buyer Agent requested to purchase <b>{p_name}</b> for <b>${p_price:.2f}</b>. 
                Because it exceeds the $10.00 automatic threshold, human authorization is required.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    appr_col1, appr_col2, appr_col3 = st.columns([2, 1, 1])

    with appr_col1:
        auth_input = st.text_input(
            "Authorization Token / PIN:",
            value=config.DEFAULT_AUTH_TOKEN,
            help="Expected default token: COMMITCON-SECURE-2026. Modify to test invalid authorization attempts.",
            key="agent_approval_token_input",
        )

    with appr_col2:
        st.write("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        st.button(
            "✅ Approve Payment",
            on_click=handle_agent_approval,
            args=(auth_input,),
            type="primary",
            width="stretch",
        )

    with appr_col3:
        st.write("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        st.button(
            "❌ Reject Payment",
            on_click=handle_agent_rejection,
            width="stretch",
            help="Normal human rejection (does NOT count as invalid authorization attempt)",
        )

    st.button("Dismiss / Cancel", on_click=handle_cancel_approval)
    st.write("")


# =============================================================================
# 10. MULTI-AGENT INTERACTION TRACE & RESULT DISPLAY
# =============================================================================

if st.session_state.last_agent_result is not None:
    agent_res: PurchaseFlowResult = st.session_state.last_agent_result

    # Final Result Banner
    safe_summary = html.escape(agent_res.summary_message)
    if agent_res.success:
        st.markdown(
            f"""
            <div style="background: rgba(16, 185, 129, 0.12); border: 1px solid #10B981; border-radius: 10px; padding: 14px 18px; margin-bottom: 20px;">
                <span style="font-size: 1.1rem; font-weight: 700; color: #34D399;">✅ Purchase Complete</span>
                <div style="font-size: 0.9rem; color: #E2E8F0; margin-top: 4px;">{safe_summary}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    elif agent_res.status == "AWAITING_APPROVAL":
        st.markdown(
            f"""
            <div style="background: rgba(245, 158, 11, 0.12); border: 1px solid #F59E0B; border-radius: 10px; padding: 14px 18px; margin-bottom: 20px;">
                <span style="font-size: 1.1rem; font-weight: 700; color: #FBBF24;">⏸️ Purchase Paused for Approval</span>
                <div style="font-size: 0.9rem; color: #FEF3C7; margin-top: 4px;">{safe_summary}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"""
            <div style="background: rgba(239, 68, 68, 0.12); border: 1px solid #EF4444; border-radius: 10px; padding: 14px 18px; margin-bottom: 20px;">
                <span style="font-size: 1.1rem; font-weight: 700; color: #F87171;">❌ Purchase Rejected / Failed</span>
                <div style="font-size: 0.9rem; color: #FECACA; margin-top: 4px;">{safe_summary}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Agent Activity Trace
    st.markdown("#### 📡 Multi-Agent Communication Trace")
    st.caption("Live communication sequence between Buyer Agent, Seller Agents, and SafeAgentWallet:")

    for step in agent_res.trace:
        step_agent = html.escape(step.agent)
        step_action = html.escape(step.action)
        step_details = html.escape(step.details)

        badge_color = "#38BDF8"
        if "Seller" in step.agent:
            badge_color = "#A78BFA"
        elif "Wallet" in step.agent:
            badge_color = "#34D399" if "SUCCESS" in step.action else "#F87171"

        st.markdown(
            f"""
            <div class="trace-card">
                <div class="trace-header">
                    <span class="trace-agent" style="color: {badge_color};">● {step_agent}</span>
                    <span class="trace-time">{step.timestamp}</span>
                </div>
                <div class="trace-action">{step_action}</div>
                <div class="trace-details">{step_details}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.write("")


# =============================================================================
# 11. PART 3: MARKETPLACE PRODUCTS
# =============================================================================

st.markdown("### 🛒 Marketplace Products")
st.caption("Initial CommitCon catalog represented by dedicated Seller Agents.")

prods = marketplace.get_all_products()
cols = st.columns(3)

for idx, product in enumerate(prods):
    seller_inst = sellers.get(product.seller_id)
    seller_name = seller_inst.name if seller_inst else product.seller_id

    icon = "🔌"
    if "Mouse" in product.name:
        icon = "🖱️"
    elif "Headphones" in product.name:
        icon = "🎧"

    with cols[idx % 3]:
        if not product.availability:
            badge_html = "<span class='badge-outofstock'>Out of Stock</span>"
        elif product.price <= Decimal("10.00"):
            badge_html = "<span class='badge-auto'>⚡ Automatic (&le; $10)</span>"
        else:
            badge_html = "<span class='badge-approval'>👤 Approval Required (&gt; $10)</span>"

        st.markdown(
            f"""
            <div class="product-box">
                <div>
                    <div class="product-icon">{icon}</div>
                    {badge_html}
                    <div class="product-title">{html.escape(product.name)}</div>
                    <div class="product-seller">Merchant: <b>{html.escape(seller_name)}</b></div>
                    <div class="product-desc">{html.escape(product.description)}</div>
                </div>
                <div>
                    <div class="product-price">${product.price:.2f}</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        btn_col1, btn_col2 = st.columns([2, 1])
        with btn_col1:
            st.button(
                f"Buy via Agent",
                key=f"prod_buy_{product.product_id}",
                on_click=handle_agent_purchase,
                args=(f"Buy {product.name}",),
                width="stretch",
                disabled=wallet.is_locked or not product.availability,
            )
        with btn_col2:
            toggle_label = "Mark OOS" if product.availability else "Restock"
            st.button(
                toggle_label,
                key=f"prod_toggle_{product.product_id}",
                on_click=handle_toggle_availability,
                args=(product.product_id,),
                width="stretch",
                help="Toggle in-stock status for testing out-of-stock handling",
            )

st.write("")
st.divider()


# =============================================================================
# 12. TRANSACTION AUDIT LOG & HISTORY
# =============================================================================

st.markdown("### 📋 SafeAgent Live Transaction Ledger")
st.caption("All transactions are cryptographically recorded and persisted to data/transactions.json.")

history = wallet.get_transaction_history()

if not history:
    st.info("No transactions recorded yet. Ask the Buyer Agent to make a purchase above.")
else:
    formatted_rows = []
    for tx in reversed(history):
        status_icon = (
            "🟢 SUCCESS" if tx.get("status") == config.STATUS_SUCCESS else "🔴 REJECTED"
        )
        formatted_rows.append(
            {
                "Timestamp (UTC)": tx.get("timestamp", "")[:19].replace("T", " "),
                "Transaction ID": tx.get("transaction_id", ""),
                "Recipient": tx.get("recipient", ""),
                "Amount ($)": f"${float(tx.get('amount', 0)):.2f}",
                "Status": status_icon,
                "Reason / Notes": tx.get("reason", ""),
                "Balance After": f"${float(tx.get('balance_after', 0)):.2f}",
                "Approval Req?": "Yes" if tx.get("requires_human_approval") else "No",
            }
        )

    st.dataframe(
        formatted_rows,
        width="stretch",
        hide_index=True,
    )
