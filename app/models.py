from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean
from datetime import datetime
from app.database import Base


# ============================================
# Пользователи
# ============================================
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)


# ============================================
# Платежи
# ============================================
class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    amount = Column(Float, nullable=False)
    status = Column(String, default="pending")
    plan = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    paid_at = Column(DateTime, nullable=True)


# ============================================
# Подписки
# ============================================
class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    access_key = Column(String, unique=True, index=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    is_active = Column(Boolean, default=True)


# ============================================
# Промокоды
# ============================================
class PromoCode(Base):
    __tablename__ = "promo_codes"

    id = Column(Integer, primary_key=True, index=True)

    # Сам код (например "AXELUS-FRIEND")
    code = Column(String, unique=True, index=True, nullable=False)

    # Тип промокода
    # ONE_TIME    - одноразовый
    # REUSABLE    - многоразовый с лимитом
    # UNLIMITED   - безлимитный
    promo_type = Column(String, nullable=False)

    # На сколько дней активирует подписку
    # 0 = навсегда (36500 дней = 100 лет)
    days = Column(Integer, nullable=False)

    # Максимум использований
    # None = безлимит
    max_uses = Column(Integer, nullable=True)

    # Текущее количество использований
    current_uses = Column(Integer, default=0)

    # Активен ли промокод (можно отключить)
    is_active = Column(Boolean, default=True)

    # Дата создания
    created_at = Column(DateTime, default=datetime.utcnow)

    # Дата окончания действия промокода (не подписки!)
    # После этой даты промокод нельзя активировать
    # None = никогда не истекает
    expires_at = Column(DateTime, nullable=True)


# ============================================
# История использования промокодов
# ============================================
class PromoUsage(Base):
    __tablename__ = "promo_usages"

    id = Column(Integer, primary_key=True, index=True)
    promo_code_id = Column(Integer, index=True)
    user_id = Column(Integer, index=True)
    used_at = Column(DateTime, default=datetime.utcnow)