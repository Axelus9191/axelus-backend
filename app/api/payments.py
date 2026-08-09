from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from datetime import datetime
import random

from app.database import get_db
from app.models import User, Payment, Subscription
from app.services.activator import activate_payment

router = APIRouter(prefix="/api/payments", tags=["payments"])


# ============================================
# Тарифы
# ============================================
PLANS = {
    "1_month": {"price": 149, "days": 30},
    "3_months": {"price": 349, "days": 90},
    "1_year": {"price": 999, "days": 365},
    "forever": {"price": 1999, "days": 36500}
}

# Секретный токен админа
ADMIN_TOKEN = "your-super-secret-admin-token-12345"


# ============================================
# СОЗДАНИЕ ПЛАТЕЖА
# ============================================

class CreatePaymentRequest(BaseModel):
    device_id: str
    plan: str


class CreatePaymentResponse(BaseModel):
    payment_id: int
    amount: float
    phone: str
    bank: str
    plan: str
    expires_in_minutes: int


@router.post("/create", response_model=CreatePaymentResponse)
async def create_payment(
    request: CreatePaymentRequest,
    db: AsyncSession = Depends(get_db)
):
    if request.plan not in PLANS:
        raise HTTPException(
            status_code=400,
            detail=f"Неизвестный тариф: {request.plan}"
        )

    plan_info = PLANS[request.plan]
    base_price = plan_info["price"]

    result = await db.execute(
        select(User).where(User.device_id == request.device_id)
    )
    user = result.scalar_one_or_none()

    if user is None:
        user = User(device_id=request.device_id)
        db.add(user)
        await db.commit()
        await db.refresh(user)

    unique_kopecks = random.randint(1, 99)
    amount = float(f"{base_price}.{unique_kopecks:02d}")

    payment = Payment(
        user_id=user.id,
        amount=amount,
        plan=request.plan,
        status="pending"
    )
    db.add(payment)
    await db.commit()
    await db.refresh(payment)

    return CreatePaymentResponse(
        payment_id=payment.id,
        amount=amount,
        phone="+7 (999) 123-45-67",
        bank="Сбербанк / Тинькофф",
        plan=request.plan,
        expires_in_minutes=30
    )


# ============================================
# ПРОВЕРКА СТАТУСА ПЛАТЕЖА
# ============================================

class PaymentStatusResponse(BaseModel):
    payment_id: int
    status: str
    amount: float
    access_key: str | None = None


@router.get("/status/{payment_id}", response_model=PaymentStatusResponse)
async def check_payment_status(
    payment_id: int,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Payment).where(Payment.id == payment_id)
    )
    payment = result.scalar_one_or_none()

    if payment is None:
        raise HTTPException(status_code=404, detail="Платёж не найден")

    access_key = None
    if payment.status == "paid":
        sub_result = await db.execute(
            select(Subscription).where(
                Subscription.user_id == payment.user_id,
                Subscription.is_active == True
            )
        )
        subscription = sub_result.scalar_one_or_none()
        if subscription:
            access_key = subscription.access_key

    return PaymentStatusResponse(
        payment_id=payment.id,
        status=payment.status,
        amount=payment.amount,
        access_key=access_key
    )


# ============================================
# АКТИВАЦИЯ ПЛАТЕЖА АДМИНОМ (по сумме)
# ============================================

class ActivatePaymentRequest(BaseModel):
    amount: float
    secret_token: str


@router.post("/activate")
async def activate_payment_endpoint(
    request: ActivatePaymentRequest,
    db: AsyncSession = Depends(get_db)
):
    if request.secret_token != ADMIN_TOKEN:
        raise HTTPException(
            status_code=403,
            detail="Неверный токен"
        )

    result = await activate_payment(request.amount, db)

    if not result["success"]:
        raise HTTPException(
            status_code=404,
            detail=result["error"]
        )

    return result