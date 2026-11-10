# Zer0Life Mining performance and levels

- `GET /api/mining/performance?period=day|week|month` records and returns a user-specific hashrate/equipment/reward-rate snapshot.
- Snapshots are recorded at most once every 15 minutes per user when the endpoint is requested.
- The frontend shows a hashrate history bar chart and current estimated virtual daily reward.
- `GET /api/mining/level` returns a level based on combined equipment hashrate:
  - Novice: 0 TH/s
  - Apprentice: 5 TH/s
  - Operator: 15 TH/s
  - Specialist: 35 TH/s
  - Expert: 75 TH/s
  - Elite: 150 TH/s
  - Legend: 300 TH/s

Limitations:
- Snapshot collection is request-driven, not a background sampler. If users do not open the app or refresh this endpoint, no intermediate snapshots are recorded.
- The graph is a basic in-app visualization, not a chart of actual blockchain mining.
- Levels are based only on virtual equipment hashrate and do not increase rewards or create on-chain rights.
- Existing databases need a migration for `mining_snapshots`.
- Backend Python syntax was checked. Frontend dependencies are not installed in this workspace, so a production build and end-to-end tests have not been run.
