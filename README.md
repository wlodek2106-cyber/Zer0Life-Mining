# Zer0Life Mining — Telegram Mini App

Standalone Telegram Mini App for a virtual ZRL mining game.

## Important product and safety notes

- Hashrate and mining rewards are game mechanics. This app does **not** perform proof-of-work mining and does not mine SOL, BTC, or other coins.
- Rewards accrue as pending in-app ZRL amounts. Internal claims update the app's ledger only.
- On-chain payouts are disabled. No private keys or seed phrases are collected or stored.
- Phantom wallet linking proves wallet control through a one-time signed message; it does not authorize transfers.
- ZRL mint and token parameters were supplied by the project owner and must be independently verified before production use.
- This repository is a development scaffold, not a security-audited production service.

## Stack

- Frontend: React, TypeScript, Vite, Telegram WebApp SDK
- Backend: FastAPI, SQLAlchemy, PostgreSQL
- Telegram authentication: WebApp initData HMAC validation
- Solana: read-only RPC balance, mint and transaction-history lookups; wallet-link signature verification

## Repository layout

- `backend/` — FastAPI service and API documentation
- `frontend/` — Telegram Mini App interface
- `.env.example` — environment variable template

## Local development

1. Copy `.env.example` to `backend/.env` and configure secrets locally.
2. Install backend dependencies: `pip install -r backend/requirements.txt`.
3. Start the API from `backend/`: `uvicorn app.main:app --reload`.
4. Install frontend dependencies: `cd frontend && npm install`.
5. Start the frontend: `npm run dev`.
6. Configure the HTTPS Mini App URL in BotFather after deployment.

## Production checklist

- Apply database migrations before deploying to an existing database. SQLAlchemy `create_all` does not alter existing tables.
- Configure a reliable Solana RPC provider, rate limits, caching and monitoring.
- Set `ADMIN_TELEGRAM_IDS` server-side; never expose admin IDs in frontend variables.
- Configure Telegram bot token as a server-side secret in Render.
- Configure the public treasury wallet address only after independently verifying it.
- Add automated tests, audit logs, backups, privacy policy and terms.
- Use a distributed scheduler/locking mechanism if running multiple backend replicas; the current in-process report/alert workers assume a single process.
- Do not enable on-chain payouts until treasury controls, multisig policy, payout worker, reconciliation and legal review are complete.

## Deployment

The frontend and backend should be deployed as separate Render services, with a PostgreSQL database. Configure all secrets through Render environment variables, never by committing them to Git.
