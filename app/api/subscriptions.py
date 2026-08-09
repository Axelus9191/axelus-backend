from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from datetime import datetime, timedelta
import secrets
import string

from app.database import get_db
from app.models import User, Payment, Subscription

router = APIRouter(prefix="/api/subscriptions", tags=["subscriptions"])

# Длительность пробного периода в днях
TRIAL_DAYS = 3


# ============================================
# АКТИВАЦИЯ КЛЮЧА ВРУЧНУЮ
# ============================================

class ActivateKeyRequest(BaseModel):
    device_id: str
    access_key: str


class ActivateKeyResponse(BaseModel):
    success: bool
    expires_at: str | None = None
    plan: str | None = None
    message: str | None = None


@router.post("/activate", response_model=ActivateKeyResponse)
async def activate_key_by_user(
    request: ActivateKeyRequest,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Subscription).where(
            Subscription.access_key == request.access_key,
            Subscription.is_active == True
        )
    )
    subscription = result.scalar_one_or_none()

    if subscription is None:
        return ActivateKeyResponse(
            success=False,
            message="Ключ не найден или неактивен"
        )

    if subscription.expires_at < datetime.utcnow():
        return ActivateKeyResponse(
            success=False,
            message="Срок действия ключа истёк"
        )

    user_result = await db.execute(
        select(User).where(User.id == subscription.user_id)
    )
    user = user_result.scalar_one_or_none()

    if user and user.device_id != request.device_id:
        user.device_id = request.device_id
        await db.commit()

    payment_result = await db.execute(
        select(Payment).where(Payment.user_id == subscription.user_id)
    )
    payment = payment_result.scalar_one_or_none()

    return ActivateKeyResponse(
        success=True,
        expires_at=subscription.expires_at.isoformat(),
        plan=payment.plan if payment else "trial",
        message="Ключ активирован"
    )


# ============================================
# СТАТУС ПОДПИСКИ + АВТОСОЗДАНИЕ ПРОБНОГО ПЕРИОДА
# ============================================

class SubscriptionStatusResponse(BaseModel):
    is_active: bool
    expires_at: str | None = None
    days_left: int = 0
    plan: str | None = None
    access_key: str | None = None
    is_trial: bool = False


@router.get("/status/{device_id}", response_model=SubscriptionStatusResponse)
async def get_subscription_status(
    device_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Возвращает статус подписки.
    Если пользователь новый — автоматически создаёт пробный период на 3 дня.
    """

    # Находим пользователя
    user_result = await db.execute(
        select(User).where(User.device_id == device_id)
    )
    user = user_result.scalar_one_or_none()

    # Если пользователь НОВЫЙ — создаём его + пробный период
    if user is None:
        user = User(device_id=device_id)
        db.add(user)
        await db.commit()
        await db.refresh(user)

        # Создаём пробную подписку на 3 дня
        trial_key = generate_access_key()
        trial_expires = datetime.utcnow() + timedelta(days=TRIAL_DAYS)

        trial_subscription = Subscription(
            user_id=user.id,
            access_key=trial_key,
            expires_at=trial_expires,
            is_active=True
        )
        db.add(trial_subscription)
        await db.commit()

        return SubscriptionStatusResponse(
            is_active=True,
            expires_at=trial_expires.isoformat(),
            days_left=TRIAL_DAYS,
            plan="trial",
            access_key=trial_key,
            is_trial=True
        )

    # Ищем активную подписку
    sub_result = await db.execute(
        select(Subscription).where(
            Subscription.user_id == user.id,
            Subscription.is_active == True
        ).order_by(Subscription.expires_at.desc())
    )
    subscription = sub_result.scalar_one_or_none()

    if subscription is None:
        return SubscriptionStatusResponse(is_active=False)

    now = datetime.utcnow()
    if subscription.expires_at < now:
        return SubscriptionStatusResponse(is_active=False)

    days_left = max(0, (subscription.expires_at - now).days)

    # Ищем оплату (если была)
    payment_result = await db.execute(
        select(Payment).where(
            Payment.user_id == user.id,
            Payment.status == "paid"
        ).order_by(Payment.created_at.desc())
    )
    payment = payment_result.scalar_one_or_none()

    is_trial = payment is None  # Если оплат не было — значит триал

    return SubscriptionStatusResponse(
        is_active=True,
        expires_at=subscription.expires_at.isoformat(),
        days_left=days_left,
        plan=payment.plan if payment else "trial",
        access_key=subscription.access_key,
        is_trial=is_trial
    )


# ============================================
# Утилита
# ============================================

def generate_access_key() -> str:
    chars = string.ascii_uppercase + string.digits
    parts = []
    for _ in range(3):
        part = ''.join(secrets.choice(chars) for _ in range(4))
        parts.append(part)
    return "AXL-" + "-".join(parts)