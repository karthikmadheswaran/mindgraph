import os
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth import get_current_user
from app.payments import service

router = APIRouter()


class CreateOrderRequest(BaseModel):
    plan: Literal["monthly", "yearly"]


class VerifyRequest(BaseModel):
    order_id: str
    payment_id: str
    signature: str


@router.post("/create-order")
async def create_order_endpoint(
    body: CreateOrderRequest,
    user_id: str = Depends(get_current_user),
):
    try:
        order = service.create_order(body.plan, user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "order_id": order["id"],
        "amount": order["amount"],
        "currency": order.get("currency", "INR"),
        "key_id": os.getenv("RAZORPAY_KEY_ID"),
    }


@router.post("/verify")
async def verify_endpoint(
    body: VerifyRequest,
    user_id: str = Depends(get_current_user),
):
    if not service.verify_signature(body.order_id, body.payment_id, body.signature):
        raise HTTPException(status_code=400, detail="Invalid payment signature")

    order = service._client().order.fetch(body.order_id)
    plan = (order.get("notes") or {}).get("plan")
    if plan not in service.PLAN_AMOUNTS:
        raise HTTPException(status_code=400, detail="Order missing plan metadata")

    await service.activate_subscription(user_id, plan, body.payment_id, body.order_id)
    return {"success": True, "plan": plan}
