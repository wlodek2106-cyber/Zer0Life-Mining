from datetime import datetime, timezone
from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, LargeBinary, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

def utcnow():
    return datetime.now(timezone.utc)

class User(Base):
    __tablename__ = "users"
    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String(64))
    wallet_address: Mapped[str | None] = mapped_column(String(64), unique=True)
    internal_balance_zrl: Mapped[float] = mapped_column(Numeric(24, 9), default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class Equipment(Base):
    __tablename__ = "equipment"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(64))
    price_zrl: Mapped[float] = mapped_column(Numeric(24, 9))
    hashrate: Mapped[float] = mapped_column(Numeric(18, 6))
    reward_per_day: Mapped[float] = mapped_column(Numeric(24, 9))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

class UserEquipment(Base):
    __tablename__ = "user_equipment"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(ForeignKey("users.telegram_id"), index=True)
    equipment_id: Mapped[int] = mapped_column(ForeignKey("equipment.id"))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    purchased_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_accrued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class RewardLedger(Base):
    __tablename__ = "reward_ledger"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(ForeignKey("users.telegram_id"), index=True)
    amount_zrl: Mapped[float] = mapped_column(Numeric(24, 9))
    kind: Mapped[str] = mapped_column(String(24))
    idempotency_key: Mapped[str] = mapped_column(String(96), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class Purchase(Base):
    __tablename__ = "purchases"
    __table_args__ = (UniqueConstraint("telegram_id", "idempotency_key"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(ForeignKey("users.telegram_id"), index=True)
    equipment_id: Mapped[int] = mapped_column(ForeignKey("equipment.id"))
    amount_zrl: Mapped[float] = mapped_column(Numeric(24, 9))
    idempotency_key: Mapped[str] = mapped_column(String(96))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class WalletChallenge(Base):
    __tablename__ = "wallet_challenges"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(ForeignKey("users.telegram_id"), index=True)
    wallet_address: Mapped[str] = mapped_column(String(64))
    nonce: Mapped[str] = mapped_column(String(96), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used: Mapped[bool] = mapped_column(Boolean, default=False)

class MiningPoolState(Base):
    __tablename__ = "mining_pool_state"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    issued_rewards_zrl: Mapped[float] = mapped_column(Numeric(24, 9), default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

class DailyMiningReport(Base):
    __tablename__ = "daily_mining_reports"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_date: Mapped[str] = mapped_column(String(10), unique=True, index=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    recipients_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(24), default="sent")

class MiningPoolAlertEvent(Base):
    __tablename__ = "mining_pool_alert_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alert_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    alert_type: Mapped[str] = mapped_column(String(24))
    threshold_percent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    recipients_count: Mapped[int] = mapped_column(Integer, default=0)

class MiningSnapshot(Base):
    __tablename__ = "mining_snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(ForeignKey("users.telegram_id"), index=True)
    hashrate: Mapped[float] = mapped_column(Numeric(18, 6))
    active_miners: Mapped[int] = mapped_column(Integer)
    estimated_reward_per_day: Mapped[float] = mapped_column(Numeric(24, 9))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class DepositTransaction(Base):
    __tablename__ = "deposit_transactions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    signature: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    telegram_id: Mapped[int] = mapped_column(ForeignKey("users.telegram_id"), index=True)
    source_wallet: Mapped[str | None] = mapped_column(String(64), nullable=True)
    amount_zrl: Mapped[float] = mapped_column(Numeric(24, 9))
    token_mint: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), default="credited")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DepositIntent(Base):
    __tablename__ = "deposit_intents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(ForeignKey("users.telegram_id"), index=True)
    memo_code: Mapped[str] = mapped_column(String(96), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class FarmingPosition(Base):
    __tablename__ = "farming_positions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(ForeignKey("users.telegram_id"), index=True)
    principal_zrl: Mapped[float] = mapped_column(Numeric(24, 9))
    claimed_reward_zrl: Mapped[float] = mapped_column(Numeric(24, 9), default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class ReferralProfile(Base):
    __tablename__ = "referral_profiles"
    telegram_id: Mapped[int] = mapped_column(ForeignKey("users.telegram_id"), primary_key=True)
    referral_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class ReferralEdge(Base):
    __tablename__ = "referral_edges"
    telegram_id: Mapped[int] = mapped_column(ForeignKey("users.telegram_id"), primary_key=True)
    referrer_telegram_id: Mapped[int] = mapped_column(ForeignKey("users.telegram_id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class PartnerCommission(Base):
    __tablename__ = "partner_commissions"
    __table_args__ = (UniqueConstraint("beneficiary_telegram_id", "source_claim_key", "level"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    beneficiary_telegram_id: Mapped[int] = mapped_column(ForeignKey("users.telegram_id"), index=True)
    source_telegram_id: Mapped[int] = mapped_column(ForeignKey("users.telegram_id"), index=True)
    level: Mapped[int] = mapped_column(Integer)
    amount_zrl: Mapped[float] = mapped_column(Numeric(24, 9))
    source_claim_key: Mapped[str] = mapped_column(String(96), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class DailyMiningClaim(Base):
    __tablename__ = "daily_mining_claims"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(ForeignKey("users.telegram_id"), index=True)
    claim_date: Mapped[str] = mapped_column(String(10))
    amount_zrl: Mapped[float] = mapped_column(Numeric(24, 9))
    idempotency_key: Mapped[str] = mapped_column(String(96), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class UserAvatar(Base):
    __tablename__ = "user_avatars"
    telegram_id: Mapped[int] = mapped_column(ForeignKey("users.telegram_id"), primary_key=True)
    content_type: Mapped[str] = mapped_column(String(32))
    image_data: Mapped[bytes] = mapped_column(LargeBinary)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
