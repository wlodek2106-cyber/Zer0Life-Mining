# Virtual reward accounting

- Rewards accrue in whole-minute intervals at `equipment.reward_per_day / 1440`.
- `GET /api/mining/rewards` writes newly calculated virtual accruals to the reward ledger.
- `POST /api/mining/claim` moves pending virtual rewards into an in-app balance only.
- No SPL token transfer is created; no redemption or token-value guarantee is implied.
- Existing databases need a migration for `users.internal_balance_zrl` and `user_equipment.last_accrued_at`.
- Production requires concurrency tests, Alembic migrations, rate limits and audit logging.
