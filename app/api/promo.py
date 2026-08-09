from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from datetime import datetime, timedelta
import secrets
import string

from app.database import get_db
from app.models import User, PromoCode, PromoUsage, Subscription

router = APIRouter(prefix="/api/promo", tags=["promo"])

# Секретный токен для админских операций
ADMIN_TOKEN = "your-super-secret-admin-token-12345"


# ============================================
# Активация промокода (пользователь)
# ============================================

class ActivatePromoRequest(BaseModel):
    device_id: str
    code: str


class ActivatePromoResponse(BaseModel):
    success: bool
    message: str
    access_key: str | None = None
    days: int = 0
    expires_at: str | None = None


@router.post("/activate", response_model=ActivatePromoResponse)
async def activate_promo(
    request: ActivatePromoRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Пользователь активирует промокод в приложении.
    """

    # Нормализуем код (в верхний регистр, убираем пробелы)
    code = request.code.strip().upper()

    # Ищем промокод
    result = await db.execute(
        select(PromoCode).where(PromoCode.code == code)
    )
    promo = result.scalar_one_or_none()

    if promo is None:
        return ActivatePromoResponse(
            success=False,
            message="Промокод не найден"
        )

    if not promo.is_active:
        return ActivatePromoResponse(
            success=False,
            message="Промокод отключён"
        )

    # Проверяем срок действия промокода
    if promo.expires_at and promo.expires_at < datetime.utcnow():
        return ActivatePromoResponse(
            success=False,
            message="Срок действия промокода истёк"
        )

    # Проверяем лимит использований
    if promo.max_uses is not None and promo.current_uses >= promo.max_uses:
        return ActivatePromoResponse(
            success=False,
            message="Лимит использований промокода исчерпан"
        )

    # Находим или создаём пользователя
    user_result = await db.execute(
        select(User).where(User.device_id == request.device_id)
    )
    user = user_result.scalar_one_or_none()

    if user is None:
        user = User(device_id=request.device_id)
        db.add(user)
        await db.commit()
        await db.refresh(user)

    # Проверяем — использовал ли этот пользователь уже данный промокод
    usage_result = await db.execute(
        select(PromoUsage).where(
            PromoUsage.promo_code_id == promo.id,
            PromoUsage.user_id == user.id
        )
    )
    existing_usage = usage_result.scalar_one_or_none()

    if existing_usage is not None:
        return ActivatePromoResponse(
            success=False,
            message="Вы уже использовали этот промокод"
        )

    # Для одноразовых — проверяем что вообще никто не использовал
    if promo.promo_type == "ONE_TIME" and promo.current_uses > 0:
        return ActivatePromoResponse(
            success=False,
            message="Промокод уже использован"
        )

    # Вычисляем срок подписки
    days = promo.days if promo.days > 0 else 36500  # 100 лет = навсегда
    expires_at = datetime.utcnow() + timedelta(days=days)

    # Генерируем ключ доступа
    access_key = generate_access_key()

    # Создаём подписку
    subscription = Subscription(
        user_id=user.id,
        access_key=access_key,
        expires_at=expires_at,
        is_active=True
    )
    db.add(subscription)

    # Помечаем использование
    usage = PromoUsage(
        promo_code_id=promo.id,
        user_id=user.id
    )
    db.add(usage)

    # Увеличиваем счётчик
    promo.current_uses += 1

    await db.commit()

    days_text = "навсегда" if promo.days == 0 else f"на {promo.days} дней"

    return ActivatePromoResponse(
        success=True,
        message=f"Промокод активирован {days_text}!",
        access_key=access_key,
        days=days,
        expires_at=expires_at.isoformat()
    )


# ============================================
# Создание промокода (админ)
# ============================================

class CreatePromoRequest(BaseModel):
    secret_token: str
    code: str                    # "AXELUS-FRIEND"
    promo_type: str              # "ONE_TIME" / "REUSABLE" / "UNLIMITED"
    days: int                    # 30, 365, 0 (навсегда)
    max_uses: int | None = None  # None = безлимит


@router.post("/create")
async def create_promo(
    request: CreatePromoRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Создание промокода (только для админа).
    """

    if request.secret_token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Неверный токен")

    # Проверяем что кода ещё нет
    result = await db.execute(
        select(PromoCode).where(PromoCode.code == request.code.upper())
    )
    existing = result.scalar_one_or_none()

    if existing is not None:
        raise HTTPException(status_code=400, detail="Такой промокод уже существует")

    # Создаём
    promo = PromoCode(
        code=request.code.upper(),
        promo_type=request.promo_type,
        days=request.days,
        max_uses=request.max_uses,
        current_uses=0,
        is_active=True
    )
    db.add(promo)
    await db.commit()
    await db.refresh(promo)

    return {
        "success": True,
        "id": promo.id,
        "code": promo.code,
        "promo_type": promo.promo_type,
        "days": promo.days,
        "max_uses": promo.max_uses
    }


# ============================================
# Список промокодов (админ)
# ============================================

@router.get("/list")
async def list_promos(
    secret_token: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Список всех промокодов.
    """

    if secret_token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Неверный токен")

    result = await db.execute(select(PromoCode))
    promos = result.scalars().all()

    return [
        {
            "id": p.id,
            "code": p.code,
            "promo_type": p.promo_type,
            "days": p.days,
            "max_uses": p.max_uses,
            "current_uses": p.current_uses,
            "is_active": p.is_active,
            "created_at": p.created_at.isoformat() if p.created_at else None
        }
        for p in promos
    ]


# ============================================
# Отключить промокод (админ)
# ============================================

@router.post("/deactivate/{promo_id}")
async def deactivate_promo(
    promo_id: int,
    secret_token: str,
    db: AsyncSession = Depends(get_db)
):
    if secret_token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Неверный токен")

    result = await db.execute(
        select(PromoCode).where(PromoCode.id == promo_id)
    )
    promo = result.scalar_one_or_none()

    if promo is None:
        raise HTTPException(status_code=404, detail="Промокод не найден")

    promo.is_active = False
    await db.commit()

    return {"success": True, "message": f"Промокод {promo.code} отключён"}


# ============================================
# Утилита: генерация ключа
# ============================================

def generate_access_key() -> str:
    chars = string.ascii_uppercase + string.digits
    parts = []
    for _ in range(3):
        part = ''.join(secrets.choice(chars) for _ in range(4))
        parts.append(part)
    return "AXL-" + "-".join(parts)