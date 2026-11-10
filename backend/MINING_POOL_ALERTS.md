# Zer0Life Mining Pool alerts

The backend supports opt-in one-time Telegram alerts to configured admin Telegram IDs.

Environment:
- `MINING_POOL_ALERTS_ENABLED=false` (default; set true to activate)
- `MINING_POOL_ALERT_POLL_SECONDS=120`
- `MINING_POOL_ALERT_THRESHOLDS=25,50,75,90,100`
- `MINING_POOL_LOW_REMAINING_ZRL=5000000`
- Existing `BOT_TOKEN` and `ADMIN_TELEGRAM_IDS` supply the bot and recipients.

Alerts:
- Emission milestones at configured percentages of the 70,000,000 ZRL mining-rewards allocation.
- Low remaining balance when the unissued allocation falls to or below the configured ZRL threshold.
- Each alert key is persisted in `mining_pool_alert_events` to avoid repeat notifications after a successful send.
- Admin-only history/setting endpoint: `GET /api/admin/mining-pool-alerts`.

Important operational limitations:
- Alerts are disabled by default and require a valid bot token plus admins who have started the bot.
- The worker currently assumes a single backend process. Multiple replicas can race and send duplicate notifications; use a DB advisory lock or external scheduler before scaling.
- Delivery is at-least-once around a process crash between Telegram delivery and DB commit.
- Alert thresholds are evaluated against internal virtual accrual accounting, not on-chain locked tokens.
- This is not a real-time blockchain monitor and does not enable payouts.
- Existing databases require migrations for the new `mining_pool_alert_events` table. `create_all` creates missing tables, but production should use Alembic migrations.
