from datetime import datetime, timezone, timedelta
from decimal import Decimal
from uuid import uuid4
import hashlib
import hmac
from fastapi import FastAPI, Depends, Header, HTTPException, Request
import httpx
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from .db import Base, engine, get_db
from .models import User, Equipment, UserEquipment, RewardLedger, Purchase
from .auth import verify_telegram_init_data
from .config import settings

app = FastAPI(title="Zer0Life Mining API", version="0.19.0")
app.add_middleware(CORSMiddleware, allow_origins=[settings.frontend_origin], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
async def startup():
    Base.metadata.create_all(bind=engine)
    # Telegram menu and webhook are owned by the existing Run 2.0 service.
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

@app.get("/api/admin/overview")
def admin_overview(admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    return {"users": db.scalar(select(func.count()).select_from(User)) or 0, "equipment": db.scalar(select(func.count()).select_from(Equipment)) or 0, "virtual_rewards": str(db.scalar(select(func.coalesce(func.sum(RewardLedger.amount_zrl),0)).where(RewardLedger.kind=="accrual")) or 0), "on_chain_payouts_enabled": False}
