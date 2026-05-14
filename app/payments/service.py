import hashlib
import hmac
import logging
import os
from datetime import datetime, timezone

import razorpay

from app.db import supabase
from app.services.tier_service import tier_service

logger = logging.getLogger(__name__)

PLAN_AMOUNTS = {
    "monthly": 74900,
    "yearly": 624900,
}
CURRENCY = "INR"


def _client() -> razorpay.Client:
    key_id = os.getenv("RAZORPAY_KEY_ID")
    key_secret = os.getenv("RAZORPAY_KEY_SECRET")
    if not key_id or not key_secret:
        raise RuntimeError("Razorpay credentials not configured")
    return razorpay.Client(auth=(key_id, key_secret))


def create_order(plan: str, user_id: str) -> dict:
    if plan not in PLAN_AMOUNTS:
        raise ValueError(f"Invalid plan: {plan}")

    amount = PLAN_AMOUNTS[plan]
    order = _client().order.create({
        "amount": amount,
        "currency": CURRENCY,
        "notes": {"user_id": user_id, "plan": plan},
    })
    return order


def verify_signature(order_id: str, payment_id: str, signature: str) -> bool:
    secret = os.getenv("RAZORPAY_KEY_SECRET")
    if not secret:
        raise RuntimeError("Razorpay credentials not configured")

    message = f"{order_id}|{payment_id}"
    expected = hmac.new(
        secret.encode(),
        message.encode(),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


async def activate_subscription(
    user_id: str,
    plan: str,
    payment_id: str,
    order_id: str,
) -> None:
    now_iso = datetime.now(timezone.utc).isoformat()

    supabase.table("users").update(
        {"subscription_tier": "paid"}
    ).eq("id", user_id).execute()

    supabase.table("subscriptions").insert({
        "user_id": user_id,
        "plan": plan,
        "payment_id": payment_id,
        "order_id": order_id,
        "status": "active",
        "created_at": now_iso,
    }).execute()

    await tier_service.invalidate(user_id)
