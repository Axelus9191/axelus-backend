from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta
import secrets
import string

from app.models import Payment, Subscription


PLANS_DAYS = {
    "1_month": 30,
    "3_months": 90,
    "1_year": 365,
    "forever": 36500
}


def generate_access_key() -> str:
    """Генерирует ключ типа AXL-XXXX-XXXX-XXXX"""
    chars = string.ascii_uppercase + string.digits
    parts = []
    for _ in range(3):
        part = ''.join(secrets.choice(chars) for _ in range(4))
        parts.append(part)
    return "AXL-" + "-".join(parts)


async def activate_payment(
    payment_amount: float,
    db: AsyncSession
) -> dict:
    """
    Ищет платёж по сумме и активирует подписку.
    """

    # Ищем ожидающий платёж с такой суммой
    result = await db.execute(
        select(Payment).where(
            Payment.amount == payment_amount,
            Payment.status == "pending"
        )
    )
    payment = result.scalar_one_or_none()

    if payment is None:
        return {
            "success": False,
            "error": f"Платёж на сумму {payment_amount} не найден"
        }

    # Помечаем как оплаченный
    payment.status = "paid"
    payment.paid_at = datetime.utcnow()

    # Считаем срок
    days = PLANS_DAYS.get(payment.plan, 30)
    expires_at = datetime.utcnow() + timedelta(days=days)

    # Генерируем ключ
    access_key = generate_access_key()

    # Создаём подписку
    subscription = Subscription(
        user_id=payment.user_id,
        access_key=access_key,
        expires_at=expires_at,
        is_active=True
    )
    db.add(subscription)

    await db.commit()

    return {
        "success": True,
        "payment_id": payment.id,
        "user_id": payment.user_id,
        "access_key": access_key,
        "expires_at": expires_at.isoformat(),
        "plan": payment.plan
    }