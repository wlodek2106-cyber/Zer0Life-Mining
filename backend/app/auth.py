import hashlib, hmac, json, time
from urllib.parse import parse_qsl
from fastapi import HTTPException
from .config import settings

def verify_telegram_init_data(init_data: str) -> dict:
    if not init_data or not settings.bot_token:
        raise HTTPException(401, "Telegram authentication required")
    pairs = parse_qsl(init_data, keep_blank_values=True)
    data = dict(pairs)
    if len(data) != len(pairs):
        raise HTTPException(401, "Duplicate Telegram auth fields")
    received_hash = data.pop("hash", "")
    if not received_hash:
        raise HTTPException(401, "Missing Telegram signature")
    check = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    secret = hmac.new(b"WebAppData", settings.bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received_hash):
        raise HTTPException(401, "Invalid Telegram signature")
    try:
        auth_date = int(data["auth_date"])
        user = json.loads(data["user"])
    except (KeyError, ValueError, TypeError):
        raise HTTPException(401, "Malformed Telegram auth data")
    now = int(time.time())
    if auth_date > now + 60 or now - auth_date > settings.init_data_max_age_seconds:
        raise HTTPException(401, "Telegram session expired")
    if not isinstance(user, dict) or int(user.get("id", 0)) <= 0:
        raise HTTPException(401, "Invalid Telegram user")
    return user
