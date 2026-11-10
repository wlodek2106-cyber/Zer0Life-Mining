from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    bot_token: str
    database_url: str
    frontend_origin: str = "http://localhost:5173"
    init_data_max_age_seconds: int = 86400
    zrl_token_name: str = "Zer0Life Labs"
    zrl_token_symbol: str = "ZRL"
    zrl_token_mint: str = "GPJjF6w38TYrNFUSkZSctW1dSoZSiu8CSFjgygjdtzuo"
    zrl_token_decimals: int = 6
    mining_network: str = "solana"
    solana_rpc_url: str = "https://api.mainnet-beta.solana.com"
    solana_commitment: str = "confirmed"
    treasury_wallet_address: str = ""
    treasury_min_zrl_alert: float = 100000.0
    mining_pool_total_zrl: float = 100000000.0
    mining_rewards_allocation_zrl: float = 70000000.0
    mining_future_reserve_zrl: float = 20000000.0
    mining_bonus_allocation_zrl: float = 10000000.0
    mining_pool_distribution_months: int = 36
    on_chain_payouts_enabled: bool = False
    daily_report_enabled: bool = False
    daily_report_hour_utc: int = 20
    daily_report_poll_seconds: int = 60
    mining_pool_alerts_enabled: bool = False
    mining_pool_alert_poll_seconds: int = 120
    mining_pool_alert_thresholds: str = "25,50,75,90,100"
    mining_pool_low_remaining_zrl: float = 5000000.0
    admin_telegram_ids: str = ""
    model_config = SettingsConfigDict(env_file="../.env", extra="ignore")

settings = Settings()
