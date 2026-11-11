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
from nacl.signing import VerifyKey
from nacl.exceptions import BadSignatureError
from .db import Base, engine, get_db
from .models import User, Equipment, UserEquipment, RewardLedger, Purchase, WalletChallenge, DepositTransaction, DepositIntent
from .auth import verify_telegram_init_data
from .config import settings

app = FastAPI(title="Zer0Life Mining API", version="0.19.0")
app.add_middleware(CORSMiddleware, allow_origins=[settings.frontend_origin], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
async def startup():
    Base.metadata.create_all(bind=engine)
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
    command = message_text.split()[0].split("@")[0] if message_text else ""
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
                        {"text": "Open Mining", "web_app": {"url": settings.mini_app_url}}
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

    # Memo-free deposits: require a real outgoing ZRL balance delta from the
    # user's previously verified Phantom wallet in this same transaction.
    source_wallet = user.wallet_address
    if not source_wallet:
        raise HTTPException(400, "Connect and verify your Phantom wallet before depositing")
    owner_pre = {}
    owner_post = {}
    for item in pre:
        if item.get("mint") == mint and item.get("owner"):
            owner_pre[item["owner"]] = owner_pre.get(item["owner"], 0) + int(item.get("uiTokenAmount", {}).get("amount", "0"))
    for item in post:
        if item.get("mint") == mint and item.get("owner"):
            owner_post[item["owner"]] = owner_post.get(item["owner"], 0) + int(item.get("uiTokenAmount", {}).get("amount", "0"))
    source_delta = owner_post.get(source_wallet, 0) - owner_pre.get(source_wallet, 0)
    if source_delta >= 0:
        raise HTTPException(400, "No outgoing ZRL transfer from your verified Phantom wallet was found")
    if -source_delta < delta_raw:
        raise HTTPException(400, "The verified wallet's outgoing ZRL amount does not match the Treasury deposit")

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


@app.get("/api/admin/overview")
def admin_overview(admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    return {"users": db.scalar(select(func.count()).select_from(User)) or 0, "equipment": db.scalar(select(func.count()).select_from(Equipment)) or 0, "virtual_rewards": str(db.scalar(select(func.coalesce(func.sum(RewardLedger.amount_zrl),0)).where(RewardLedger.kind=="accrual")) or 0), "on_chain_payouts_enabled": False}
