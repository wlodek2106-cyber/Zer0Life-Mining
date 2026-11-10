# Daily Zer0Life Mining reports

The backend includes an opt-in UTC daily Telegram summary.
Configuration:
- `DAILY_REPORT_ENABLED=false` by default
- `DAILY_REPORT_HOUR_UTC=20`
- `DAILY_REPORT_POLL_SECONDS=60`
- Existing `BOT_TOKEN` and `ADMIN_TELEGRAM_IDS` are used as the bot credential and recipients.

When enabled, the worker sends registered users, users with equipment, today's virtual accruals and internal claims, total rewards issued, remaining rewards allocation, and the disabled on-chain payout status. A `daily_mining_reports` row prevents the same date being sent again after a successful send.

Admins can preview the current report with `GET /api/admin/daily-report`.

Operational caveats:
- This lightweight worker assumes one backend process/replica. Multiple replicas can race and send duplicate reports; use a distributed scheduler/DB advisory lock before horizontal scaling.
- All report dates and delivery hour are UTC.
- Telegram delivery requires the bot to be able to message each configured admin chat. Admins generally need to start the bot first.
- Failed sends are retried on the next poll; logs/alerting should be added for production.
- A successful Telegram send is recorded after sending. A crash between send and DB commit can cause a duplicate on retry.
- This report is an operational summary, not an accounting audit.
