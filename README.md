# SafeAgent-Wallet

# Project Overview

SafeAgent Wallet is a simulated AI-agent payment system designed to demonstrate secure and controlled autonomous payments.

The system allows an AI agent to initiate purchases using a virtual wallet containing an initial balance of $100.

However, the agent cannot freely spend money. The system applies security rules, transaction validation and human approval before protected payments are executed.

## Main Objective

Our objective is to demonstrate how AI agents can make payments safely without giving them unrestricted control over financial transactions.

## Core Features

1. **Virtual Wallet:** A simulated wallet with an initial balance of $100.
2. **AI Agent:** Initiates purchase requests.
3. **Buy Buttons:** Allows users to simulate purchases.
4. **Human Approval:** Requires human authorization for protected transactions.
5. **Insufficient Balance Protection:** Rejects purchases exceeding the available balance.
6. **Transaction History:** Records transaction details and outcomes.
7. **Security Validation:** Prevents unauthorized or invalid transactions.

## Technology Stack

- Python
- Streamlit
- Antigravity (AI-assisted development)
- GitHub

## Project Scope

This is a hackathon prototype using simulated funds. It does not connect to real bank accounts or process real payments.

## Security Metrics

Our system will be evaluated using the following security metrics:

| Metric | Target |
|---|---|
| Initial Wallet Balance | $100 |
| Unauthorized Payments | 0 |
| Negative Wallet Balance | Not allowed |
| Insufficient Balance Transactions | 100% rejected |
| Protected Transactions | Human approval required |
| Transaction Logging | Every transaction recorded |
| Approval Verification | Only authorized approval accepted |

## Security Rules

1. Never allow spending beyond the available wallet balance.
2. Never execute a protected transaction without human approval.
3. Reject unauthorized payment requests.
4. Record successful and rejected transactions.
5. Prevent duplicate transaction execution.
6. Maintain an accurate wallet balance after every successful payment.

## Success Criteria

SafeAgent Wallet will be considered successful when it can demonstrate:

- Successful simulated purchases.
- Rejection of insufficient-balance purchases.
- Prevention of unauthorized payments.
- Human approval before protected transactions.
- Accurate transaction history and wallet balance.

