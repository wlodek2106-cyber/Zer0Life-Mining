# Zer0Life Mining analytics

## Personal statistics
`GET /api/mining/stats?period=day|week|month` returns the authenticated user's:
- total virtual rewards accrued in the selected rolling window
- internal claims recorded in that window
- current in-app balance
- daily accrual totals
- up to 30 recent reward-ledger entries

The frontend displays this on Overview and Mining tabs. Periods are rolling 1-, 7-, and 30-day windows, with timestamps stored/reported in UTC and displayed in the device locale.

## Admin leaderboard
`GET /api/admin/mining/leaderboard?period=day|week|month|all&limit=20` is admin-only and returns Telegram IDs, usernames and virtual rewards accrued. It is not exposed as a public leaderboard.

## Caveats
- All figures are internal virtual ledger figures; they do not represent on-chain payments or guaranteed token claims.
- Admin leaderboard includes Telegram identifiers and is intentionally access-controlled.
- No frontend production build or end-to-end database tests were run in this environment. Install dependencies and test against the target PostgreSQL database before deployment.
- Existing DB migrations are still required for the prior v14-v16 schema additions.
