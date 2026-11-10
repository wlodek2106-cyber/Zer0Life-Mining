# Zer0Life Mining Pool — accounting policy

Approved allocation:
- Total pool: 100,000,000 ZRL
- Mining rewards: 70,000,000 ZRL
- Future seasons reserve: 20,000,000 ZRL
- Activity and achievement bonuses: 10,000,000 ZRL
- Planned distribution period: 36 months

## Atomic accrual control

The MVP now maintains a singleton `mining_pool_state` row. Each reward accrual first reserves capacity with a conditional SQL UPDATE:
`issued_rewards_zrl + requested_amount <= mining_rewards_allocation_zrl`.
The database applies this condition atomically, so concurrent workers cannot push the counter beyond the configured mining-rewards allocation. Reward ledger entries are written in the same database transaction as the counter update.

## Important limitations

- This is internal virtual accounting, not an on-chain token allocation.
- No ZRL has been transferred, locked, escrowed, or reserved on Solana by this code.
- No on-chain payouts are enabled.
- The 20M future-season reserve and 10M bonus allocation are informational and not yet claimable.
- Existing databases still need a proper Alembic migration for previously added columns/tables. `create_all` creates missing tables but does not alter existing tables.
- Run integration/concurrency tests against the actual production database engine before launch. SQLite has different locking behavior from PostgreSQL; use PostgreSQL in production.
