"""
app.py - SafeAgent Wallet Streamlit Dashboard
CommitCon Hackathon - Hours 4–7: Streamlit Dashboard Implementation

Connects directly to SafeAgentWallet in wallet.py without modifying backend logic.
Preserves wallet state across reruns via st.session_state.
"""

from decimal import Decimal
import html
from typing import Any, Dict, List

import streamlit as st

import config
from wallet import PaymentResult, SafeAgentWallet

# =============================================================================
# 1. PAGE CONFIGURATION & CUSTOM STYLES
# =============================================================================

st.set_page_config(
    page_title="SafeAgent Wallet",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for fintech dashboard aesthetics
st.markdown(
    """
    <style>
    /* Metric Card Styling */
    .metric-card {
        background: #131722;
        border: 1px solid #232936;
        border-radius: 12px;
        padding: 18px 20px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.2);
    }
    .metric-label {
        font-size: 0.85rem;
        color: #8E9BAE;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 6px;
    }
    .metric-value {
        font-size: 1.85rem;
        font-weight: 700;
        color: #FFFFFF;
        line-height: 1.2;
    }
    .metric-subtext {
        font-size: 0.8rem;
        color: #64748B;
        margin-top: 6px;
    }
    
    /* Product Card Styling */
    .product-box {
        background: #181E2A;
        border: 1px solid #283347;
        border-radius: 14px;
        padding: 22px;
        min-height: 220px;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        margin-bottom: 10px;
        transition: transform 0.15s ease, border-color 0.15s ease;
    }
    .product-box:hover {
        border-color: #3B82F6;
        transform: translateY(-2px);
    }
    .product-icon {
        font-size: 2.2rem;
        margin-bottom: 10px;
    }
    .product-title {
        font-size: 1.15rem;
        font-weight: 700;
        color: #F8FAFC;
        margin-bottom: 6px;
    }
    .product-desc {
        font-size: 0.85rem;
        color: #94A3B8;
        min-height: 48px;
        margin-bottom: 12px;
    }
    .product-price {
        font-size: 1.45rem;
        font-weight: 800;
        color: #38BDF8;
        margin-bottom: 6px;
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
        margin-bottom: 12px;
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
        margin-bottom: 12px;
    }
    .badge-limit {
        display: inline-block;
        background: rgba(239, 68, 68, 0.15);
        color: #F87171;
        border: 1px solid rgba(239, 68, 68, 0.3);
        border-radius: 9999px;
        padding: 3px 10px;
        font-size: 0.72rem;
        font-weight: 600;
        margin-bottom: 12px;
    }
    
    /* Security rules card */
    .rule-pill {
        background: #141A24;
        border-left: 3px solid #3B82F6;
        padding: 10px 14px;
        border-radius: 0 8px 8px 0;
        margin-bottom: 8px;
        font-size: 0.88rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# =============================================================================
# 2. WALLET INITIALIZATION USING STREAMLIT SESSION STATE
# =============================================================================
# Initialize the SafeAgentWallet instance once using st.session_state.
# This preserves the exact same wallet object across Streamlit reruns.

if "wallet" not in st.session_state:
    st.session_state.wallet = SafeAgentWallet(load_existing=True)

if "last_result" not in st.session_state:
    st.session_state.last_result = None

if "pending_approval" not in st.session_state:
    st.session_state.pending_approval = None

# Reference the persistent wallet object
wallet: SafeAgentWallet = st.session_state.wallet


# =============================================================================
# 3. INTERACTION CALLBACK HANDLERS
# =============================================================================
# Using callbacks ensures wallet operations execute before the page renders,
# guaranteeing all balances, logs, and indicators are immediately synchronized.


def on_purchase_click(product: Dict[str, Any]) -> None:
    """Triggered when a user clicks Buy on a marketplace product."""
    price = product["price"]
    name = product["name"]

    # Payments strictly exceeding $10 require human approval
    if wallet.requires_human_approval(price):
        st.session_state.pending_approval = {
            "name": name,
            "price": price,
            "id": product["id"],
        }
        st.session_state.last_result = None
    else:
        # Automatic payment (<= $10.00)
        res = wallet.execute_payment(amount=price, recipient=name)
        st.session_state.last_result = res
        st.session_state.pending_approval = None


def on_approve_click(pending: Dict[str, Any], token: str) -> None:
    """Triggered when human reviewer approves a payment."""
    res = wallet.execute_payment(
        amount=pending["price"],
        recipient=pending["name"],
        human_approved=True,
        auth_token=token.strip(),
    )
    st.session_state.last_result = res
    st.session_state.pending_approval = None


def on_reject_click(pending: Dict[str, Any]) -> None:
    """Triggered when human reviewer normally rejects a payment (does not lock wallet)."""
    res = wallet.execute_payment(
        amount=pending["price"],
        recipient=pending["name"],
        human_approved=False,
    )
    st.session_state.last_result = res
    st.session_state.pending_approval = None


def on_cancel_approval() -> None:
    """Dismisses the pending approval prompt."""
    st.session_state.pending_approval = None


def on_reset_wallet() -> None:
    """Resets the wallet to $100 balance, $0 spent, and clears transactions."""
    wallet.reset()
    st.session_state.last_result = None
    st.session_state.pending_approval = None


def on_reset_rate_limiter() -> None:
    """Clears timestamps in the rolling rate limiter."""
    wallet.reset_rate_limiter()


def on_unlock_wallet() -> None:
    """Unlocks the wallet after lockouts."""
    wallet.unlock()


def on_custom_payment(amount_str: str, recipient: str, approval_choice: str, token: str) -> None:
    """Executes a custom payment from the developer sidebar."""
    try:
        amt = Decimal(amount_str.strip())
    except Exception as e:
        st.session_state.last_result = PaymentResult(
            success=False,
            transaction_id="err_format",
            amount=Decimal("0.00"),
            recipient=recipient,
            status=config.STATUS_REJECTED,
            reason=f"Invalid decimal format: {e}",
            balance=wallet.balance,
            total_spent=wallet.total_spent,
            remaining_spending_limit=wallet.remaining_spending_limit,
            requires_human_approval=False,
            human_approved=None,
            timestamp="",
        )
        return

    approved_val = None
    if approval_choice == "Approved (True)":
        approved_val = True
    elif approval_choice == "Rejected (False)":
        approved_val = False

    res = wallet.execute_payment(
        amount=amt,
        recipient=recipient,
        human_approved=approved_val,
        auth_token=token if approved_val else None,
    )
    st.session_state.last_result = res


# =============================================================================
# 4. SIDEBAR: SECURITY CONTROLS & DIAGNOSTICS
# =============================================================================

with st.sidebar:
    st.markdown("### 🛡️ SafeAgent Security")
    st.caption("CommitCon Hackathon • AI Payment Guard")

    # Real-time Status Indicators
    status_text = "🔴 LOCKED" if wallet.is_locked else "🟢 ACTIVE"
    st.markdown(f"**Wallet State:** `{status_text}`")

    # Rate Limiter Window Stats
    current_requests = wallet._rate_limiter.get_request_count()
    st.markdown(f"**Rate Limit:** `{current_requests} / {config.RATE_LIMIT_MAX_REQUESTS}` requests in 60s")

    # Invalid Auth Attempts Counter
    failed_attempts = wallet.invalid_auth_attempts
    st.markdown(f"**Failed Auth Attempts:** `{failed_attempts} / {config.MAX_INVALID_AUTH_ATTEMPTS}`")

    st.divider()

    st.markdown("#### ⚙️ Developer & Demo Controls")
    st.caption("Quick actions to test edge cases or reset wallet state:")

    col_rst1, col_rst2 = st.columns(2)
    with col_rst1:
        st.button(
            "🔄 Reset All",
            on_click=on_reset_wallet,
            width="stretch",
            help="Reset wallet balance to $100 and clear history",
        )

    with col_rst2:
        st.button(
            "⏱️ Reset Rate",
            on_click=on_reset_rate_limiter,
            width="stretch",
            help="Clear rolling rate limit window",
        )

    if wallet.is_locked:
        st.warning("⚠️ Wallet is locked due to 3 invalid auth attempts.")
        st.button(
            "🔓 Admin Unlock",
            on_click=on_unlock_wallet,
            type="primary",
            width="stretch",
        )

    st.divider()

    # Manual Custom Transaction Tester
    with st.expander("🧪 Custom Transaction Tester", expanded=False):
        st.caption("Test edge cases (e.g. over-balance, negative amounts, or duplicate IDs):")
        custom_recipient = st.text_input("Recipient", value="Custom Vendor", key="custom_recip")
        custom_amount_str = st.text_input("Amount ($)", value="12.50", key="custom_amt")
        custom_approved = st.selectbox(
            "Human Approval",
            ["None", "Approved (True)", "Rejected (False)"],
            key="custom_appr",
        )
        custom_token = st.text_input("Auth Token", value=config.DEFAULT_AUTH_TOKEN, key="custom_tok")

        st.button(
            "Execute Custom Payment",
            on_click=on_custom_payment,
            args=(custom_amount_str, custom_recipient, custom_approved, custom_token),
            width="stretch",
        )


# =============================================================================
# 5. DASHBOARD HEADER
# =============================================================================

header_col1, header_col2 = st.columns([3, 1])
with header_col1:
    st.title("SafeAgent Wallet")
    st.markdown("##### Secure AI-powered payment wallet")

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
# 6. WALLET OVERVIEW (ACTUAL WALLET STATE)
# =============================================================================

st.markdown("### 💼 Wallet Overview")

# Metrics row using actual wallet properties (not hardcoded)
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
            <div class="rule-pill">
                <b>1. Starting Balance:</b> <code>$100.00</code> starting virtual wallet balance.
            </div>
            <div class="rule-pill">
                <b>2. Lifetime Spending Limit:</b> Maximum <code>$80.00</code> total spending allowance.
            </div>
            <div class="rule-pill">
                <b>3. Automatic Payment Threshold:</b> Payments up to and including <code>$10.00</code> are automatic, subject to security checks.
            </div>
            """,
            unsafe_allow_html=True,
        )
    with r_col2:
        st.markdown(
            f"""
            <div class="rule-pill">
                <b>4. Human Approval:</b> Payments strictly above <code>$10.00</code> require human approval.
            </div>
            <div class="rule-pill">
                <b>5. Rate Limiting:</b> Maximum <code>3 payment requests per 60 seconds</code> (rejected requests count too).
            </div>
            <div class="rule-pill">
                <b>6. Lockout Protection:</b> Wallet locks after <code>3 invalid authorization attempts</code>.
            </div>
            """,
            unsafe_allow_html=True,
        )

st.write("")


# =============================================================================
# 8. TRANSACTION FEEDBACK BANNER (LAST EXECUTION)
# =============================================================================

if st.session_state.last_result is not None:
    res: PaymentResult = st.session_state.last_result
    safe_reason = html.escape(res.reason)
    safe_recip = html.escape(res.recipient)
    safe_txid = html.escape(res.transaction_id)

    if res.success:
        st.markdown(
            f"""
            <div style="background: rgba(16, 185, 129, 0.12); border: 1px solid #10B981; border-radius: 10px; padding: 14px 18px; margin-bottom: 20px;">
                <span style="font-size: 1.1rem; font-weight: 700; color: #34D399;">✅ Payment Successful</span> — 
                <b>${res.amount:.2f}</b> paid to <b>{safe_recip}</b>
                <div style="font-size: 0.85rem; color: #94A3B8; margin-top: 4px;">
                    TxID: <code>{safe_txid}</code> • Balance: <b>${res.balance:.2f}</b> • Reason: {safe_reason}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"""
            <div style="background: rgba(239, 68, 68, 0.12); border: 1px solid #EF4444; border-radius: 10px; padding: 14px 18px; margin-bottom: 20px;">
                <span style="font-size: 1.1rem; font-weight: 700; color: #F87171;">❌ Payment Rejected</span> — 
                Attempted <b>${res.amount:.2f}</b> to <b>{safe_recip}</b>
                <div style="font-size: 0.85rem; color: #FECACA; margin-top: 4px;">
                    <b>Reason:</b> {safe_reason}
                </div>
                <div style="font-size: 0.78rem; color: #94A3B8; margin-top: 2px;">
                    TxID: <code>{safe_txid}</code> • Current Balance: <b>${res.balance:.2f}</b>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


# =============================================================================
# 9. HUMAN APPROVAL DIALOG / ACTION CARD
# =============================================================================

if st.session_state.pending_approval is not None:
    pending = st.session_state.pending_approval
    p_name = html.escape(pending["name"])
    p_price = pending["price"]

    st.markdown(
        f"""
        <div style="background: #1C1917; border: 2px solid #F59E0B; border-radius: 12px; padding: 20px; margin-bottom: 25px;">
            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
                <span style="font-size: 1.2rem; font-weight: 800; color: #FBBF24;">⚠️ Human Approval Required</span>
                <span style="background: rgba(245, 158, 11, 0.2); color: #FBBF24; padding: 3px 10px; border-radius: 6px; font-weight: 700; font-size: 0.8rem;">Amount &gt; $10.00</span>
            </div>
            <p style="color: #D6D3D1; font-size: 0.95rem; margin-bottom: 12px;">
                A payment of <b>${p_price:.2f}</b> for <b>{p_name}</b> exceeds the automatic threshold of $10.00.
                Please review and approve or reject this transaction.
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
            help="Default expected token: COMMITCON-SECURE-2026. Modify to test invalid authorization attempts.",
            key="approval_auth_token_field",
        )

    with appr_col2:
        st.write("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        st.button(
            "✅ Approve Payment",
            on_click=on_approve_click,
            args=(pending, auth_input),
            type="primary",
            width="stretch",
        )

    with appr_col3:
        st.write("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        st.button(
            "❌ Reject Payment",
            on_click=on_reject_click,
            args=(pending,),
            width="stretch",
            help="Normal human rejection (does NOT count as an invalid authorization attempt)",
        )

    st.button("Dismiss / Cancel", on_click=on_cancel_approval)
    st.write("")


# =============================================================================
# 10. SIMULATED MARKETPLACE
# =============================================================================

st.markdown("### 🛒 Marketplace")
st.caption("Fictional products demonstrating automatic execution, human approval, and limit rejections.")

# Curated catalog of fictional products
PRODUCTS: List[Dict[str, Any]] = [
    {
        "id": "prod_1",
        "icon": "⚡",
        "name": "API Token Pack (1K Calls)",
        "desc": "Simulated developer tokens for high-speed model completions.",
        "price": Decimal("4.50"),
        "tier": "auto",
        "badge_text": "⚡ Automatic (≤ $10)",
    },
    {
        "id": "prod_2",
        "icon": "🚀",
        "name": "Quick Compute Boost (1 Hr)",
        "desc": "Short-burst compute node allocation for background jobs.",
        "price": Decimal("8.00"),
        "tier": "auto",
        "badge_text": "⚡ Automatic (≤ $10)",
    },
    {
        "id": "prod_3",
        "icon": "🔍",
        "name": "Code Review Agent Tool",
        "desc": "Exact $10.00 boundary test item.",
        "price": Decimal("10.00"),
        "tier": "auto",
        "badge_text": "⚡ Automatic (Exact $10 Limit)",
    },
    {
        "id": "prod_4",
        "icon": "🗄️",
        "name": "Vector DB Cloud Node (Monthly)",
        "desc": "Dedicated server node. Requires human authorization.",
        "price": Decimal("15.00"),
        "tier": "approval",
        "badge_text": "👤 Human Approval (> $10)",
    },
    {
        "id": "prod_5",
        "icon": "🧠",
        "name": "GPU Inference Slice (4 Hrs)",
        "desc": "High-memory GPU cluster time. Requires human authorization.",
        "price": Decimal("25.00"),
        "tier": "approval",
        "badge_text": "👤 Human Approval (> $10)",
    },
    {
        "id": "prod_6",
        "icon": "🏢",
        "name": "Enterprise Agent Workspace",
        "desc": "Organization workspace license with full audit logging.",
        "price": Decimal("50.00"),
        "tier": "approval",
        "badge_text": "👤 Human Approval (> $10)",
    },
    {
        "id": "prod_7",
        "icon": "🛑",
        "name": "Ultra HPC Cluster Package",
        "desc": "Over-budget test item ($85.00) to demonstrate $80 limit rejection.",
        "price": Decimal("85.00"),
        "tier": "limit",
        "badge_text": "🛑 Exceeds $80 Lifetime Limit",
    },
]

# Display products in a clean 3-column responsive grid
num_cols = 3
for row_idx in range(0, len(PRODUCTS), num_cols):
    cols = st.columns(num_cols)
    for col_idx, product in enumerate(PRODUCTS[row_idx : row_idx + num_cols]):
        with cols[col_idx]:
            # Badge selection based on product tier
            if product["tier"] == "auto":
                badge_html = f"<span class='badge-auto'>{product['badge_text']}</span>"
            elif product["tier"] == "approval":
                badge_html = f"<span class='badge-approval'>{product['badge_text']}</span>"
            else:
                badge_html = f"<span class='badge-limit'>{product['badge_text']}</span>"

            st.markdown(
                f"""
                <div class="product-box">
                    <div>
                        <div class="product-icon">{product['icon']}</div>
                        {badge_html}
                        <div class="product-title">{html.escape(product['name'])}</div>
                        <div class="product-desc">{html.escape(product['desc'])}</div>
                    </div>
                    <div>
                        <div class="product-price">${product['price']:.2f}</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # Buy button uses on_click callback
            st.button(
                f"🛒 Buy for ${product['price']:.2f}",
                key=f"buy_btn_{product['id']}",
                on_click=on_purchase_click,
                args=(product,),
                width="stretch",
                disabled=wallet.is_locked,
            )

st.write("")
st.divider()


# =============================================================================
# 11. TRANSACTION AUDIT LOG & HISTORY
# =============================================================================

st.markdown("### 📋 Live Transaction Audit Ledger")
st.caption("All transactions are persisted to data/transactions.json.")

history = wallet.get_transaction_history()

if not history:
    st.info("No transactions recorded yet. Purchase an item from the marketplace above to generate records.")
else:
    # Display transactions in reverse chronological order (newest first)
    formatted_rows = []
    for tx in reversed(history):
        status_icon = "🟢 SUCCESS" if tx.get("status") == config.STATUS_SUCCESS else "🔴 REJECTED"
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
