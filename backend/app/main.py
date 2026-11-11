from datetime import datetime, timezone, timedelta
from decimal import Decimal
from uuid import uuid4
import hashlib
import hmac
import base64
from fastapi import FastAPI, Depends, Header, HTTPException, Request
import httpx
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from nacl.signing import VerifyKey
from nacl.exceptions import BadSignatureError
from .db import Base, engine, get_db
from .models import User, Equipment, UserEquipment, RewardLedger, Purchase, WalletChallenge, DepositTransaction, DepositIntent, FarmingPosition, ReferralProfile, ReferralEdge, PartnerCommission, DailyMiningClaim, MiningPoolState
from .auth import verify_telegram_init_data
from .config import settings

app = FastAPI(title="Zer0Life Mining API", version="0.19.0")
app.add_middleware(CORSMiddleware, allow_origins=[settings.frontend_origin], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
async def startup():
    Base.metadata.create_all(bind=engine)
    # Singleton row serializes reward issuance across all users and app replicas.
    with Session(engine) as startup_db:
        if startup_db.get(MiningPoolState, 1) is None:
            startup_db.add(MiningPoolState(id=1, issued_rewards_zrl=0))
            try:
                startup_db.commit()
            except IntegrityError:
                startup_db.rollback()
    # Register this service's own Telegram bot webhook. This token must belong only to @Zer0lifeMining_bot.
    if settings.bot_token:
        webhook_secret = hashlib.sha256(settings.bot_token.encode()).hexdigest()
        async with httpx.AsyncClient(timeout=15) as client:
            webhook_response = await client.post(
                f"https://api.telegram.org/bot{settings.bot_token}/setWebhook",
                json={
                    "url": "https://zer0life-mining-api.onrender.com/telegram/webhook",
                    "secret_token": webhook_secret,
                    "allowed_updates": ["message"],
                    "drop_pending_updates": False
                }
            )
            webhook_result = webhook_response.json()
            print(f"Mining Telegram webhook setup: ok={webhook_result.get('ok', False)} description={webhook_result.get('description', '')}")

    # This separate Mining API must never change shared bot configuration.

@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    if not settings.bot_token:
        raise HTTPException(503, "Telegram bot is not configured")
    expected = hashlib.sha256(settings.bot_token.encode()).hexdigest()
    supplied = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(403, "Invalid Telegram webhook secret")
    update = await request.json()
    message = update.get("message") or {}
    print(f"Telegram webhook received: update_id={update.get('update_id')} has_message={bool(message)}")
    chat = message.get("chat") or {}
    message_text = (message.get("text") or "").strip()
    chat_id = chat.get("id")
    parts = message_text.split()
    command = parts[0].split("@")[0] if parts else ""
    referral_code = parts[1].strip().upper() if command == "/start" and len(parts) > 1 else ""
    if chat_id and command in {"/start", "/help"}:
        welcome = (
            "Welcome to Zer0Life Mining!\\n\\n"
            "Open the Mini App to enter the virtual mining game. "
            "Rewards are in-game only; real ZRL payouts are currently disabled."
        )
        async with httpx.AsyncClient(timeout=10) as client:
            send_response = await client.post(
                f"https://api.telegram.org/bot{settings.bot_token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": welcome,
                    "reply_markup": {"inline_keyboard": [[
                        {"text": "Open Mining", "web_app": {"url": settings.mini_app_url + (("&" if "?" in settings.mini_app_url else "?") + "ref=" + referral_code if referral_code else "")}}
                    ]]}
                }
            )
            send_result = send_response.json()
            print(f"Telegram welcome send: http={send_response.status_code} ok={send_result.get('ok', False)} description={send_result.get('description', '')}")
    return {"ok": True}


def current_user(authorization: str = Header(default=""), db: Session = Depends(get_db)):
    if not authorization.startswith("tma "):
        raise HTTPException(401, "Telegram initData required")
    data = verify_telegram_init_data(authorization[4:])
    user = db.get(User, int(data["id"]))
    if user is None:
        user = User(telegram_id=int(data["id"]), username=data.get("username"))
        db.add(user); db.commit(); db.refresh(user)
    elif user.username != data.get("username"):
        user.username = data.get("username"); db.commit()
    return user

def admin_user(user: User = Depends(current_user)):
    allowed = {int(x.strip()) for x in settings.admin_telegram_ids.split(",") if x.strip().isdigit()}
    if user.telegram_id not in allowed:
        raise HTTPException(403, "Admin access required")
    return user

def lock_reward_pool(db: Session):
    state = db.scalar(select(MiningPoolState).where(MiningPoolState.id == 1).with_for_update())
    if state is None:
        state = MiningPoolState(id=1, issued_rewards_zrl=0)
        db.add(state)
        db.flush()
    return state

def reward_pool_usage(db: Session) -> Decimal:
    issued = db.scalar(select(func.coalesce(func.sum(RewardLedger.amount_zrl), 0)).where(
        RewardLedger.kind.in_(("accrual", "farming_claim_internal", "farming_maturity_reward")),
        RewardLedger.amount_zrl > 0
    )) or 0
    partner = db.scalar(select(func.coalesce(func.sum(PartnerCommission.amount_zrl), 0))) or 0
    return Decimal(str(issued)) + Decimal(str(partner))

def accrue(db: Session, user: User):
    rows = db.execute(select(UserEquipment, Equipment).join(Equipment, Equipment.id == UserEquipment.equipment_id).where(UserEquipment.telegram_id == user.telegram_id)).all()
    now = datetime.now(timezone.utc); earned = Decimal("0")
    for owned, item in rows:
        last = owned.last_accrued_at
        if last.tzinfo is None: last = last.replace(tzinfo=timezone.utc)
        minutes = max(0, int((now-last).total_seconds() // 60))
        if minutes:
            earned += Decimal(str(item.reward_per_day)) * Decimal(minutes) / Decimal(1440)
            owned.last_accrued_at = last + timedelta(minutes=minutes)
    if earned > 0:
        lock_reward_pool(db)
        remaining = max(Decimal("0"), Decimal(str(settings.mining_rewards_allocation_zrl)) - reward_pool_usage(db))
        earned = min(earned, remaining)
        if earned > 0:
            key = f"accrual:{user.telegram_id}:{uuid4().hex}"
            user.internal_balance_zrl = Decimal(str(user.internal_balance_zrl)) + earned
            db.add(RewardLedger(telegram_id=user.telegram_id, amount_zrl=earned, kind="accrual", idempotency_key=key))
        db.commit()
    return earned

@app.get("/health")
def health(): return {"ok": True, "service": "zer0life-mining-api", "version": "0.19.0"}

@app.get("/api/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    accrue(db, user)
    return {"telegram_id": user.telegram_id, "username": user.username, "wallet_address": user.wallet_address, "balance_zrl": str(user.internal_balance_zrl)}

@app.get("/api/mining/status")
def mining_status(user: User = Depends(current_user), db: Session = Depends(get_db)):
    accrue(db, user)
    rows = db.execute(select(UserEquipment, Equipment).join(Equipment, Equipment.id == UserEquipment.equipment_id).where(UserEquipment.telegram_id == user.telegram_id)).all()
    hashrate = sum(float(item.hashrate) * owned.quantity for owned, item in rows)
    daily = sum(float(item.reward_per_day) * owned.quantity for owned, item in rows)
    return {"hashrate": hashrate, "estimated_reward_per_day": daily, "active_miners": sum(owned.quantity for owned, item in rows), "balance_zrl": str(user.internal_balance_zrl), "mode": "virtual_game", "real_mining": False, "on_chain_payouts_enabled": False}

def decode_solana_address(address: str) -> bytes:
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    number = 0
    try:
        for char in address:
            number = number * 58 + alphabet.index(char)
    except ValueError:
        raise HTTPException(400, "Invalid Solana wallet address")
    raw = number.to_bytes((number.bit_length() + 7) // 8, "big") if number else b""
    leading_zeroes = len(address) - len(address.lstrip("1"))
    decoded = bytes(leading_zeroes) + raw
    if len(decoded) != 32:
        raise HTTPException(400, "Invalid Solana public key")
    return decoded

@app.post("/api/wallet/challenge")
def wallet_challenge(payload: dict, user: User = Depends(current_user), db: Session = Depends(get_db)):
    address = str(payload.get("wallet_address", "")).strip()
    decode_solana_address(address)
    now = datetime.now(timezone.utc)
    nonce = uuid4().hex
    expires = now + timedelta(minutes=5)
    message = (
        "Zer0Life Mining wallet verification\\n"
        f"Telegram ID: {user.telegram_id}\\n"
        f"Wallet: {address}\\n"
        f"Nonce: {nonce}\\n"
        f"Expires: {expires.isoformat()}"
    )
    db.add(WalletChallenge(telegram_id=user.telegram_id, wallet_address=address, nonce=nonce, expires_at=expires, used=False))
    db.commit()
    return {"message": message, "nonce": nonce, "expires_at": expires.isoformat()}

@app.post("/api/wallet/verify")
def wallet_verify(payload: dict, user: User = Depends(current_user), db: Session = Depends(get_db)):
    address = str(payload.get("wallet_address", "")).strip()
    nonce = str(payload.get("nonce", "")).strip()
    signature_text = str(payload.get("signature", "")).strip()
    if not address or not nonce or not signature_text:
        raise HTTPException(400, "Wallet address, nonce and signature are required")
    public_key = decode_solana_address(address)
    challenge = db.scalar(
        select(WalletChallenge)
        .where(WalletChallenge.telegram_id == user.telegram_id, WalletChallenge.wallet_address == address, WalletChallenge.nonce == nonce)
        .with_for_update()
    )
    if challenge is None or challenge.used:
        raise HTTPException(400, "Wallet challenge is invalid or already used")
    now = datetime.now(timezone.utc)
    expires = challenge.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires <= now:
        raise HTTPException(400, "Wallet challenge expired. Please try again.")
    message = (
        "Zer0Life Mining wallet verification\\n"
        f"Telegram ID: {user.telegram_id}\\n"
        f"Wallet: {address}\\n"
        f"Nonce: {nonce}\\n"
        f"Expires: {expires.isoformat()}"
    )
    try:
        signature = base64.b64decode(signature_text, validate=True)
        VerifyKey(public_key).verify(message.encode("utf-8"), signature)
    except (ValueError, BadSignatureError):
        raise HTTPException(400, "Wallet signature verification failed")
    existing = db.scalar(select(User).where(User.wallet_address == address, User.telegram_id != user.telegram_id))
    if existing is not None:
        raise HTTPException(409, "This wallet is already linked to another account")
    user.wallet_address = address
    challenge.used = True
    db.commit()
    return {"ok": True, "wallet_address": address, "message": "Wallet ownership verified and linked."}

@app.get("/api/deposits/details")
def deposit_details(user: User = Depends(current_user)):
    if not settings.treasury_wallet_address.strip():
        raise HTTPException(503, "Treasury wallet is not configured")
    return {"treasury_address": settings.treasury_wallet_address, "token_mint": settings.zrl_token_mint,
            "network": "Solana", "memo_required": False, "automatic_credit": False}


@app.post("/api/deposits/verify")
async def verify_deposit(payload: dict, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """
    Verify a user-submitted Solana transaction signature and credit only the
    finalized net incoming balance of the configured ZRL mint to Treasury.
    """
    signature = str(payload.get("signature", "")).strip()
    if len(signature) < 80 or len(signature) > 100:
        raise HTTPException(400, "Invalid Solana transaction signature")
    treasury = settings.treasury_wallet_address.strip()
    mint = settings.zrl_token_mint.strip()
    if not treasury:
        raise HTTPException(503, "Treasury wallet is not configured")
    decode_solana_address(treasury)
    decode_solana_address(mint)

    existing = db.scalar(select(DepositTransaction).where(DepositTransaction.signature == signature))
    if existing:
        if existing.telegram_id == user.telegram_id:
            return {"ok": True, "already_credited": True, "amount_zrl": str(existing.amount_zrl)}
        raise HTTPException(409, "This transaction has already been credited to another account")

    payload_rpc = {
        "jsonrpc": "2.0", "id": 1, "method": "getTransaction",
        "params": [signature, {"encoding": "jsonParsed", "commitment": "finalized", "maxSupportedTransactionVersion": 0}]
    }
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(settings.rpc_url, json=payload_rpc)
            response.raise_for_status()
            result = response.json()
    except Exception:
        raise HTTPException(502, "Solana RPC is temporarily unavailable")
    if result.get("error"):
        raise HTTPException(502, "Solana RPC could not verify this transaction")
    tx = result.get("result")
    if not tx:
        raise HTTPException(409, "Transaction is not finalized yet. Try again shortly.")
    meta = tx.get("meta") or {}
    if meta.get("err") is not None:
        raise HTTPException(400, "Solana transaction failed")
    if tx.get("slot") is None:
        raise HTTPException(400, "Transaction has no confirmed slot")

    pre = meta.get("preTokenBalances") or []
    post = meta.get("postTokenBalances") or []
    pre_by_account = {}
    post_by_account = {}
    source_wallets = set()
    for item in pre:
        if item.get("mint") == mint:
            pre_by_account[item.get("accountIndex")] = int(item.get("uiTokenAmount", {}).get("amount", "0"))
            owner = item.get("owner")
            if owner and owner != treasury:
                source_wallets.add(owner)
    for item in post:
        if item.get("mint") == mint:
            post_by_account[item.get("accountIndex")] = int(item.get("uiTokenAmount", {}).get("amount", "0"))
            owner = item.get("owner")
            if owner and owner != treasury:
                source_wallets.add(owner)

    treasury_indices = set()
    for item in pre + post:
        if item.get("mint") == mint and item.get("owner") == treasury:
            treasury_indices.add(item.get("accountIndex"))
    if not treasury_indices:
        raise HTTPException(400, "Transaction does not involve the configured Treasury ZRL token account")
    delta_raw = sum(post_by_account.get(i, 0) - pre_by_account.get(i, 0) for i in treasury_indices)
    if delta_raw <= 0:
        raise HTTPException(400, "No incoming ZRL transfer to Treasury was found")
    amount = Decimal(delta_raw) / (Decimal(10) ** int(settings.zrl_token_decimals))
    if amount <= 0:
        raise HTTPException(400, "Deposit amount must be positive")

    # Memo-free shared-Treasury flow: identify the on-chain source from token
    # balance deltas. The authenticated Telegram account submitting this
    # signature receives the internal credit; signature uniqueness prevents reuse.
    owner_pre = {}
    owner_post = {}
    for item in pre:
        if item.get("mint") == mint and item.get("owner") and item.get("owner") != treasury:
            owner_pre[item["owner"]] = owner_pre.get(item["owner"], 0) + int(item.get("uiTokenAmount", {}).get("amount", "0"))
    for item in post:
        if item.get("mint") == mint and item.get("owner") and item.get("owner") != treasury:
            owner_post[item["owner"]] = owner_post.get(item["owner"], 0) + int(item.get("uiTokenAmount", {}).get("amount", "0"))
    source_candidates = [
        (owner_post.get(owner, 0) - owner_pre.get(owner, 0), owner)
        for owner in set(owner_pre) | set(owner_post)
        if owner_post.get(owner, 0) - owner_pre.get(owner, 0) < 0
    ]
    if not source_candidates:
        raise HTTPException(400, "No outgoing ZRL token balance was found in this transaction")
    source_delta, source_wallet = min(source_candidates)
    if -source_delta < delta_raw:
        raise HTTPException(400, "Outgoing ZRL amount does not cover the Treasury deposit")

    # Security: a shared Treasury signature is not proof that the caller owns
    # the source wallet. Only credit deposits from the wallet verified and
    # linked to this Telegram account. This prevents claiming another user's tx.
    linked_wallet = (user.wallet_address or "").strip()
    if not linked_wallet:
        raise HTTPException(403, "Link and verify your Solana wallet before claiming a Treasury deposit")
    if not hmac.compare_digest(linked_wallet, source_wallet):
        raise HTTPException(403, "Deposit source wallet does not match your verified wallet")

    ledger_key = "deposit:" + signature
    try:
        deposit = DepositTransaction(
            signature=signature, telegram_id=user.telegram_id, source_wallet=source_wallet,
            amount_zrl=amount, token_mint=mint, status="credited"
        )
        db.add(deposit)
        user.internal_balance_zrl = Decimal(str(user.internal_balance_zrl)) + amount
        db.add(RewardLedger(
            telegram_id=user.telegram_id, amount_zrl=amount, kind="deposit",
            idempotency_key=ledger_key
        ))
        db.commit()
    except Exception:
        db.rollback()
        existing = db.scalar(select(DepositTransaction).where(DepositTransaction.signature == signature))
        if existing and existing.telegram_id == user.telegram_id:
            return {"ok": True, "already_credited": True, "amount_zrl": str(existing.amount_zrl)}
        raise HTTPException(409, "This transaction may already have been processed")
    return {
        "ok": True, "already_credited": False, "amount_zrl": str(amount),
        "balance_zrl": str(user.internal_balance_zrl), "signature": signature,
        "explorer_url": "https://solscan.io/tx/" + signature
    }


@app.get("/api/equipment")
def equipment(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return [{"id": x.id, "code": x.code, "name": x.name, "price_zrl": str(x.price_zrl), "hashrate": str(x.hashrate), "reward_per_day": str(x.reward_per_day)} for x in db.scalars(select(Equipment).where(Equipment.enabled == True)).all()]

@app.post("/api/equipment/{equipment_id}/buy")
def buy(equipment_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    item = db.get(Equipment, equipment_id)
    if not item or not item.enabled: raise HTTPException(404, "Equipment unavailable")
    # Demo purchase only: no token or SOL is charged.
    db.add(UserEquipment(telegram_id=user.telegram_id, equipment_id=item.id, quantity=1))
    db.add(Purchase(telegram_id=user.telegram_id, equipment_id=item.id, amount_zrl=0, idempotency_key=uuid4().hex))
    db.commit()
    return {"ok": True, "demo": True, "message": "Demo equipment added; no payment was taken."}

@app.post("/api/rewards/claim")
def claim(user: User = Depends(current_user), db: Session = Depends(get_db)):
    accrue(db, user)
    amount = Decimal(str(user.internal_balance_zrl))
    if amount <= 0: raise HTTPException(400, "No internal rewards available")
    user.internal_balance_zrl = 0
    db.add(RewardLedger(telegram_id=user.telegram_id, amount_zrl=amount, kind="claim_internal", idempotency_key=f"claim:{user.telegram_id}:{uuid4().hex}"))
    db.commit()
    return {"claimed_zrl": str(amount), "on_chain_transfer": False, "note": "Internal game ledger only; no blockchain transfer."}

@app.get("/api/mining/stats")
def stats(period: str = "day", user: User = Depends(current_user), db: Session = Depends(get_db)):
    if period not in {"day","week","month"}: raise HTTPException(400, "period must be day, week, or month")
    since = datetime.now(timezone.utc) - timedelta(days={"day":1,"week":7,"month":30}[period])
    rows = db.scalars(select(RewardLedger).where(RewardLedger.telegram_id == user.telegram_id, RewardLedger.created_at >= since).order_by(RewardLedger.created_at.desc()).limit(100)).all()
    return {"period": period, "rewards": [{"amount_zrl": str(x.amount_zrl), "kind": x.kind, "created_at": x.created_at.isoformat()} for x in rows]}

@app.get("/api/admin/treasury/status")
async def treasury_status(admin: User = Depends(admin_user)):
    """Read-only Treasury monitor. This endpoint never signs or sends transactions."""
    address = settings.treasury_wallet_address.strip()
    if not address:
        return {"configured": False, "on_chain_payouts_enabled": False}
    decode_solana_address(address)
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getTokenAccountsByOwner",
        "params": [
            address,
            {"mint": settings.zrl_token_mint},
            {"encoding": "jsonParsed", "commitment": settings.solana_commitment}
        ]
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(settings.rpc_url, json=payload)
            response.raise_for_status()
            data = response.json()
        if data.get("error"):
            raise HTTPException(502, "Solana RPC returned an error")
        accounts = data.get("result", {}).get("value", [])
        raw_total = Decimal("0")
        for account in accounts:
            info = account.get("account", {}).get("data", {}).get("parsed", {}).get("info", {})
            amount = info.get("tokenAmount", {}).get("amount", "0")
            raw_total += Decimal(str(amount))
        divisor = Decimal(10) ** int(settings.zrl_token_decimals)
        return {
            "configured": True,
            "network": settings.mining_network,
            "treasury_wallet_address": address,
            "token_mint": settings.zrl_token_mint,
            "token_accounts": len(accounts),
            "confirmed_balance_zrl": str(raw_total / divisor),
            "commitment": settings.solana_commitment,
            "on_chain_payouts_enabled": False,
            "mode": "read_only"
        }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(502, "Unable to read Treasury balance from Solana RPC")


@app.get("/api/admin/partner-dashboard")
def admin_partner_dashboard(admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    # The partner commission ledger is a liability/sub-ledger inside the 70m
    # rewards allocation. It must never be added a second time to issued rewards.
    total = db.scalar(select(func.coalesce(func.sum(PartnerCommission.amount_zrl), 0))) or 0
    total_rows = db.scalar(select(func.count()).select_from(PartnerCommission)) or 0
    partners = db.scalar(select(func.count(func.distinct(PartnerCommission.beneficiary_telegram_id)))) or 0
    by_level = []
    for level in range(1, 4):
        amount = db.scalar(select(func.coalesce(func.sum(PartnerCommission.amount_zrl), 0)).where(PartnerCommission.level == level)) or 0
        count = db.scalar(select(func.count()).select_from(PartnerCommission).where(PartnerCommission.level == level)) or 0
        by_level.append({"level": level, "rate": str(PARTNER_RATES[level] * 100) + "%", "pending_zrl": str(Decimal(str(amount))), "entries": count})
    recent = db.scalars(select(PartnerCommission).order_by(PartnerCommission.created_at.desc()).limit(100)).all()
    issued_kinds = ("accrual", "farming_claim_internal", "farming_maturity_reward")
    issued = db.scalar(select(func.coalesce(func.sum(RewardLedger.amount_zrl), 0)).where(
        RewardLedger.kind.in_(issued_kinds), RewardLedger.amount_zrl > 0
    )) or 0
    total_cap = Decimal(str(settings.mining_pool_total_zrl))
    rewards_cap = Decimal(str(settings.mining_rewards_allocation_zrl))
    reserve = Decimal(str(settings.mining_future_reserve_zrl))
    bonus = Decimal(str(settings.mining_bonus_allocation_zrl))
    issued = Decimal(str(issued))
    partner_pending = Decimal(str(total))
    return {
        "supply_cap_zrl": str(total_cap),
        "rewards_allocation_zrl": str(rewards_cap),
        "future_reserve_zrl": str(reserve),
        "bonus_allocation_zrl": str(bonus),
        "configured_allocations_total_zrl": str(rewards_cap + reserve + bonus),
        "issued_rewards_zrl": str(issued),
        "rewards_remaining_zrl": str(max(Decimal("0"), rewards_cap - issued - partner_pending)),
        "allocation_config_valid": rewards_cap + reserve + bonus == total_cap,
        "partner_commissions_included_in_rewards": True,
        "partner_commissions_pending_zrl": str(partner_pending),
        "total_pending_zrl": str(Decimal(str(total))),
        "commission_entries": total_rows,
        "unique_partners": partners,
        "by_level": by_level,
        "recent": [{
            "beneficiary_telegram_id": row.beneficiary_telegram_id,
            "source_telegram_id": row.source_telegram_id,
            "level": row.level,
            "amount_zrl": str(row.amount_zrl),
            "created_at": row.created_at.isoformat(),
            "status": "pending"
        } for row in recent],
        "payouts_enabled": False,
        "accounting_note": "Partner commissions are a sub-ledger within the rewards allocation and are not added to issued rewards a second time."
    }

@app.get("/api/admin/overview")
def admin_overview(admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    return {"users": db.scalar(select(func.count()).select_from(User)) or 0, "equipment": db.scalar(select(func.count()).select_from(Equipment)) or 0, "virtual_rewards": str(db.scalar(select(func.coalesce(func.sum(RewardLedger.amount_zrl),0)).where(RewardLedger.kind=="accrual")) or 0), "on_chain_payouts_enabled": False}


# Farming and community features. All amounts are internal ledger entries; on-chain payouts remain disabled.
from zoneinfo import ZoneInfo
WARSAW = ZoneInfo("Europe/Warsaw")
MONTH_WEIGHTS = [12,11,10,9,8,7,6,5,4,3,2,1]
MONTH_WEIGHT_SUM = Decimal("78")
PARTNER_RATES = {1: Decimal("0.05"), 2: Decimal("0.02"), 3: Decimal("0.01")}

def farming_reward_due(position: FarmingPosition, now: datetime) -> Decimal:
    start = position.started_at.replace(tzinfo=timezone.utc) if position.started_at.tzinfo is None else position.started_at
    end = position.ends_at.replace(tzinfo=timezone.utc) if position.ends_at.tzinfo is None else position.ends_at
    now = min(now, end)
    if now <= start:
        return Decimal("0")
    principal = Decimal(str(position.principal_zrl))
    total_reward = principal * Decimal("1.55")
    elapsed_days = Decimal(str((now - start).total_seconds())) / Decimal("86400")
    duration_days = Decimal(str((end - start).total_seconds())) / Decimal("86400")
    reward = Decimal("0")
    for month in range(12):
        month_start = Decimal(month * 365) / Decimal(12)
        month_end = Decimal((month + 1) * 365) / Decimal(12)
        if month_start >= duration_days:
            break
        segment_end = min(month_end, duration_days)
        days = max(Decimal("0"), min(elapsed_days, segment_end) - month_start)
        if days:
            monthly_budget = total_reward * Decimal(MONTH_WEIGHTS[month]) / MONTH_WEIGHT_SUM
            reward += monthly_budget * days / (month_end - month_start)
    return max(Decimal("0"), reward - Decimal(str(position.claimed_reward_zrl)))

@app.post("/api/farming/positions")
def create_farming_position(payload: dict, user: User = Depends(current_user), db: Session = Depends(get_db)):
    amount = Decimal(str(payload.get("amount_zrl", "0")))
    duration_months = int(payload.get("duration_months", 12))
    if duration_months not in {1, 3, 6, 9, 12}:
        raise HTTPException(400, "Choose a Farming package: 1, 3, 6, 9 or 12 months")
    # Serialize balance-changing actions for this user to prevent concurrent
    # opens from spending the same internal balance twice.
    locked_user = db.scalar(select(User).where(User.telegram_id == user.telegram_id).with_for_update())
    if locked_user is None:
        raise HTTPException(401, "User account not found")
    if amount <= 0 or amount > Decimal(str(locked_user.internal_balance_zrl)):
        raise HTTPException(400, "Invalid amount or insufficient available balance")
    now = datetime.now(timezone.utc)
    user = locked_user
    user.internal_balance_zrl = Decimal(str(user.internal_balance_zrl)) - amount
    position = FarmingPosition(telegram_id=user.telegram_id, principal_zrl=amount, claimed_reward_zrl=0,
        started_at=now, ends_at=now + timedelta(days=365 * duration_months / 12), status="active")
    db.add(position)
    db.add(RewardLedger(telegram_id=user.telegram_id, amount_zrl=-amount, kind="farming_lock", idempotency_key="farm-lock:"+uuid4().hex))
    db.commit(); db.refresh(position)
    return {"ok": True, "position_id": position.id, "principal_zrl": str(amount), "ends_at": position.ends_at.isoformat(), "duration_months": duration_months, "scheduled_reward_rate": str((Decimal("1.55") * sum(MONTH_WEIGHTS[:duration_months]) / MONTH_WEIGHT_SUM * 100).quantize(Decimal("0.01"))) + "%"}

@app.get("/api/farming/positions")
def farming_positions(user: User = Depends(current_user), db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    rows = db.scalars(select(FarmingPosition).where(FarmingPosition.telegram_id == user.telegram_id).order_by(FarmingPosition.created_at.desc())).all()
    return [{"id": p.id, "principal_zrl": str(p.principal_zrl), "pending_reward_zrl": str(farming_reward_due(p, now)),
        "claimed_reward_zrl": str(p.claimed_reward_zrl), "started_at": p.started_at.isoformat(), "ends_at": p.ends_at.isoformat(), "status": p.status} for p in rows]

@app.get("/api/referrals/me")
def referrals_me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    profile = db.get(ReferralProfile, user.telegram_id)
    if profile is None:
        profile = ReferralProfile(telegram_id=user.telegram_id, referral_code=hashlib.sha256(str(user.telegram_id).encode()).hexdigest()[:10].upper())
        db.add(profile); db.commit()
    levels = []
    parent_ids = [user.telegram_id]
    for level in range(1, 4):
        children = db.scalars(select(ReferralEdge.telegram_id).where(ReferralEdge.referrer_telegram_id.in_(parent_ids))).all() if parent_ids else []
        levels.append({"level": level, "count": len(children), "rate": str(PARTNER_RATES[level] * 100) + "%"})
        parent_ids = list(children)
    commissions = db.scalar(select(func.coalesce(func.sum(PartnerCommission.amount_zrl), 0)).where(PartnerCommission.beneficiary_telegram_id == user.telegram_id)) or 0
    commission_by_level = []
    for level in range(1, 4):
        level_total = db.scalar(select(func.coalesce(func.sum(PartnerCommission.amount_zrl), 0)).where(
            PartnerCommission.beneficiary_telegram_id == user.telegram_id,
            PartnerCommission.level == level
        )) or 0
        level_total = Decimal(str(level_total))
        commission_by_level.append({
            "level": level,
            "rate": str(PARTNER_RATES[level] * 100) + "%",
            "pending_zrl": str(level_total)
        })
    return {
        "referral_code": profile.referral_code,
        "referral_link": "https://t.me/Zer0lifeMining_bot?start=" + profile.referral_code,
        "levels": levels,
        "partner_earnings_zrl": str(Decimal(str(commissions))),
        "partner_earnings_pending_zrl": str(Decimal(str(commissions))),
        "commission_by_level": commission_by_level,
        "partner_payouts_enabled": False
    }

@app.get("/api/referrals/commissions")
def referral_commissions(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(PartnerCommission)
        .where(PartnerCommission.beneficiary_telegram_id == user.telegram_id)
        .order_by(PartnerCommission.created_at.desc())
        .limit(100)
    ).all()
    return {
        "items": [{
            "id": row.id,
            "level": row.level,
            "amount_zrl": str(row.amount_zrl),
            "created_at": row.created_at.isoformat(),
            "status": "pending"
        } for row in rows],
        "payouts_enabled": False
    }

@app.post("/api/referrals/bind")
def bind_referral(payload: dict, user: User = Depends(current_user), db: Session = Depends(get_db)):
    code = str(payload.get("referral_code", "")).strip().upper()
    profile = db.scalar(select(ReferralProfile).where(ReferralProfile.referral_code == code))
    if not profile or profile.telegram_id == user.telegram_id:
        raise HTTPException(400, "Invalid referral code")
    if db.get(ReferralEdge, user.telegram_id):
        raise HTTPException(409, "Referrer is already set and cannot be changed")
    ancestor_id = profile.telegram_id
    visited = set()
    while ancestor_id and ancestor_id not in visited:
        if ancestor_id == user.telegram_id:
            raise HTTPException(400, "Referral would create a cycle")
        visited.add(ancestor_id)
        parent = db.get(ReferralEdge, ancestor_id)
        ancestor_id = parent.referrer_telegram_id if parent else None
    db.add(ReferralEdge(telegram_id=user.telegram_id, referrer_telegram_id=profile.telegram_id))
    db.commit()
    return {"ok": True}

@app.get("/api/leaderboard")
def leaderboard(user: User = Depends(current_user), db: Session = Depends(get_db)):
    users = db.scalars(select(User)).all()
    children = {}
    for edge in db.scalars(select(ReferralEdge)).all():
        children.setdefault(edge.referrer_telegram_id, []).append(edge.telegram_id)
    rows = []
    for member in users:
        direct_ids = children.get(member.telegram_id, [])
        team_ids, frontier = set(), list(direct_ids)
        while frontier:
            child_id = frontier.pop()
            if child_id == member.telegram_id or child_id in team_ids:
                continue
            team_ids.add(child_id)
            frontier.extend(children.get(child_id, []))
        volume = db.scalar(select(func.coalesce(func.sum(FarmingPosition.principal_zrl), 0)).where(
            FarmingPosition.telegram_id.in_(team_ids), FarmingPosition.status == "active"
        )) if team_ids else 0
        volume = Decimal(str(volume or 0))
        direct = len(direct_ids)
        rank = "Diamond" if direct >= 50 and volume >= 1000000 else "Platinum" if direct >= 25 and volume >= 500000 else "Gold" if direct >= 10 and volume >= 100000 else "Silver" if direct >= 5 and volume >= 25000 else "Bronze"
        rows.append({"username": member.username or "Member", "rank": rank, "team_volume_zrl": str(volume), "direct_referrals": direct})
    order = {"Diamond": 5, "Platinum": 4, "Gold": 3, "Silver": 2, "Bronze": 1}
    rows.sort(key=lambda row: (order[row["rank"]], Decimal(row["team_volume_zrl"]), row["direct_referrals"]), reverse=True)
    return {"leaderboard": rows[:100], "rank_thresholds_status": "provisional"}

@app.post("/api/farming/claim")
def claim_farming(user: User = Depends(current_user), db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    # Serialize all daily claims for one account; the unique idempotency key
    # remains the final database-level guard against duplicate submissions.
    locked_user = db.scalar(select(User).where(User.telegram_id == user.telegram_id).with_for_update())
    if locked_user is None:
        raise HTTPException(401, "User account not found")
    user = locked_user
    local_now = now.astimezone(WARSAW)
    if (local_now.hour, local_now.minute) < (20, 0):
        raise HTTPException(403, "Daily Farming claim opens at 20:00 Europe/Warsaw")
    claim_date = local_now.date().isoformat()
    if db.scalar(select(DailyMiningClaim).where(DailyMiningClaim.telegram_id == user.telegram_id, DailyMiningClaim.claim_date == claim_date)):
        raise HTTPException(409, "Today's Farming rewards have already been claimed")
    positions = db.scalars(select(FarmingPosition).where(FarmingPosition.telegram_id == user.telegram_id, FarmingPosition.status == "active").with_for_update()).all()
    requested_amount = sum((farming_reward_due(p, now) for p in positions), Decimal("0"))
    if requested_amount <= 0:
        raise HTTPException(400, "No Farming rewards available")
    pool_state = lock_reward_pool(db)
    referrers = []
    referrer_id = user.telegram_id
    for level in range(1, 4):
        edge = db.get(ReferralEdge, referrer_id)
        if edge is None:
            break
        referrers.append((level, edge.referrer_telegram_id))
        referrer_id = edge.referrer_telegram_id
    commission_rate = sum((PARTNER_RATES[level] for level, _ in referrers), Decimal("0"))
    pool_remaining = max(Decimal("0"), Decimal(str(settings.mining_rewards_allocation_zrl)) - reward_pool_usage(db))
    amount = min(requested_amount, pool_remaining / (Decimal("1") + commission_rate))
    if amount <= 0:
        raise HTTPException(409, "The shared 70m ZRL rewards pool has been exhausted")
    matured_principal = Decimal("0")
    amount_left = amount
    for p in positions:
        due = farming_reward_due(p, now)
        paid = min(due, amount_left)
        if paid > 0:
            p.claimed_reward_zrl = Decimal(str(p.claimed_reward_zrl)) + paid
            amount_left -= paid
        if (p.ends_at.replace(tzinfo=timezone.utc) if p.ends_at.tzinfo is None else p.ends_at) <= now:
            p.status = "completed"
            principal = Decimal(str(p.principal_zrl))
            matured_principal += principal
            db.add(RewardLedger(telegram_id=user.telegram_id, amount_zrl=principal, kind="farming_principal_return", idempotency_key=f"farming-release:{p.id}"))
    if matured_principal:
        user.internal_balance_zrl = Decimal(str(user.internal_balance_zrl)) + matured_principal
    key = f"farming-claim:{user.telegram_id}:{claim_date}"
    user.internal_balance_zrl = Decimal(str(user.internal_balance_zrl)) + amount
    db.add(DailyMiningClaim(telegram_id=user.telegram_id, claim_date=claim_date, amount_zrl=amount, idempotency_key=key))
    db.add(RewardLedger(telegram_id=user.telegram_id, amount_zrl=amount, kind="farming_claim_internal", idempotency_key=key))
    for level, beneficiary_id in referrers:
        commission_amount = (amount * PARTNER_RATES[level]).quantize(Decimal("0.000000001"))
        if commission_amount > 0:
            db.add(PartnerCommission(beneficiary_telegram_id=beneficiary_id, source_telegram_id=user.telegram_id,
                level=level, amount_zrl=commission_amount, source_claim_key=key))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Today's Farming rewards have already been claimed")
    return {"ok": True, "claimed_zrl": str(amount), "partner_commissions_recorded": True,
            "partner_commissions_pending": True, "on_chain_transfer": False, "claim_date": claim_date}

@app.post("/api/farming/release")
def release_matured_farming(user: User = Depends(current_user), db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    # Use the same account-level lock as open/claim so release cannot race
    # with another balance mutation for this Telegram account.
    locked_user = db.scalar(select(User).where(User.telegram_id == user.telegram_id).with_for_update())
    if locked_user is None:
        raise HTTPException(401, "User account not found")
    user = locked_user
    positions = db.scalars(select(FarmingPosition).where(
        FarmingPosition.telegram_id == user.telegram_id,
        FarmingPosition.status == "active"
    ).with_for_update()).all()
    released = Decimal("0")
    maturity_rewards = Decimal("0")
    released_ids = []
    pool_state = lock_reward_pool(db)
    pool_remaining = max(Decimal("0"), Decimal(str(settings.mining_rewards_allocation_zrl)) - reward_pool_usage(db))
    for position in positions:
        end = position.ends_at.replace(tzinfo=timezone.utc) if position.ends_at.tzinfo is None else position.ends_at
        if end > now:
            continue
        principal = Decimal(str(position.principal_zrl))
        referrers = []
        referrer_id = user.telegram_id
        for level in range(1, 4):
            edge = db.get(ReferralEdge, referrer_id)
            if edge is None:
                break
            referrers.append((level, edge.referrer_telegram_id))
            referrer_id = edge.referrer_telegram_id
        commission_rate = sum((PARTNER_RATES[level] for level, _ in referrers), Decimal("0"))
        final_reward = min(farming_reward_due(position, now), pool_remaining / (Decimal("1") + commission_rate))
        pool_remaining -= final_reward * (Decimal("1") + commission_rate)
        position.claimed_reward_zrl = Decimal(str(position.claimed_reward_zrl)) + final_reward
        position.status = "completed"
        released += principal
        maturity_rewards += final_reward
        released_ids.append(position.id)
        db.add(RewardLedger(
            telegram_id=user.telegram_id,
            amount_zrl=principal,
            kind="farming_principal_return",
            idempotency_key=f"farming-release:{position.id}"
        ))
        if final_reward > 0:
            maturity_key = f"farming-maturity:{position.id}"
            db.add(RewardLedger(
                telegram_id=user.telegram_id,
                amount_zrl=final_reward,
                kind="farming_maturity_reward",
                idempotency_key=maturity_key
            ))
            for level, beneficiary_id in referrers:
                commission_amount = (final_reward * PARTNER_RATES[level]).quantize(Decimal("0.000000001"))
                if commission_amount > 0:
                    db.add(PartnerCommission(beneficiary_telegram_id=beneficiary_id,
                        source_telegram_id=user.telegram_id, level=level,
                        amount_zrl=commission_amount, source_claim_key=maturity_key))
    if not released_ids:
        raise HTTPException(400, "No matured Farming principal is available to release")
    user.internal_balance_zrl = Decimal(str(user.internal_balance_zrl)) + released + maturity_rewards
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Matured Farming positions have already been released")
    return {"ok": True, "released_principal_zrl": str(released),
            "maturity_reward_zrl": str(maturity_rewards), "position_ids": released_ids,
            "partner_commissions_pending": True, "on_chain_transfer": False}
