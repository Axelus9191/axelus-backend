"""
МОДЕЛИ БАЗЫ ДАННЫХ (ФИНАЛЬНАЯ ВЕРСИЯ С РЕФЕРАЛКОЙ)
Каждый класс здесь = одна таблица в базе данных.
SQLAlchemy автоматически создаст эти таблицы
при первом запуске сервера.
Если таблицы уже есть — добавятся только новые колонки.
"""
from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Boolean,
    DateTime
)
from app.database import Base


class User(Base):
    """
    ============================================
    ТАБЛИЦА ПОЛЬЗОВАТЕЛЕЙ
    ============================================
    Каждое устройство = один пользователь.
    Мы идентифицируем пользователя по device_id —
    это уникальный ID который генерируется на телефоне
    при первом запуске приложения.
    
    Добавлены поля для реферальной системы:
    - referral_count: сколько друзей уже привел
    - referred_by: device_id друга, который пригласил
    """
    __tablename__ = "users"

    # Уникальный числовой ID (автоматически увеличивается)
    id = Column(Integer, primary_key=True, index=True)

    # ID устройства — генерируется на телефоне
    # unique=True — не может быть двух одинаковых
    # index=True — быстрый поиск по этому полю
    device_id = Column(String, unique=True, index=True, nullable=False)

    # Когда пользователь зарегистрировался
    created_at = Column(DateTime, default=datetime.utcnow)

    # До какой даты активна подписка
    # Если None — подписки нет
    # Если дата в будущем — подписка активна
    # Если дата в прошлом — подписка истекла
    subscription_until = Column(DateTime, nullable=True)

    # Использовал ли пробный период (3 дня)
    # Пробный период даётся ОДИН раз на устройство
    trial_used = Column(Boolean, default=False)

    # === НОВЫЕ ПОЛЯ ДЛЯ РЕФЕРАЛЬНОЙ СИСТЕМЫ ===
    # Сколько друзей этот пользователь уже пригласил
    referral_count = Column(Integer, default=0, nullable=False)
    
    # Device ID того, кто пригласил этого пользователя
    # Если None — пришел сам или по прямой ссылке без ref
    referred_by = Column(String, nullable=True, index=True) 
    # ==========================================


class Payment(Base):
    """
    ============================================
    ТАБЛИЦА ПЛАТЕЖЕЙ
    ============================================
    Когда пользователь хочет купить подписку,
    создаётся запись с уникальной суммой.

    Статусы платежа:
    - pending   = ждём оплату
    - confirmed = оплата подтверждена админкой
    - expired   = время ожидания вышло (20 минут)
    """
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)

    # Кто платит
    device_id = Column(String, index=True, nullable=False)

    # Какой тариф выбрал (week / month / half_year / year / forever)
    plan = Column(String, nullable=False)

    # Базовая цена тарифа (например 149)
    base_amount = Column(Float, nullable=False)

    # Уникальная сумма с копейками (например 149.03)
    # По этой сумме мы находим кто заплатил
    unique_amount = Column(Float, unique=False, nullable=False)

    # На сколько дней активируется подписка
    duration_days = Column(Integer, nullable=False)

    # Статус платежа: pending / confirmed / expired
    status = Column(String, default="pending")

    # Когда создан платёж
    created_at = Column(DateTime, default=datetime.utcnow)

    # До какого времени ждём оплату (created_at + 20 минут)
    expires_at = Column(DateTime, nullable=False)

    # Когда платёж подтверждён (заполняется админкой)
    confirmed_at = Column(DateTime, nullable=True)


class PromoActivation(Base):
    """
    ============================================
    ТАБЛИЦА АКТИВИРОВАННЫХ ПРОМОКОДОВ
    ============================================
    Когда кто-то вводит промокод, создаётся запись.
    Это нужно чтобы один промокод нельзя было
    использовать дважды.
    
    Для реферальных наград используется поле is_used:
    - False: награда выдана, но ещё не активирована
    - True: награда активирована и больше недоступна
    """
    __tablename__ = "promo_activations"

    id = Column(Integer, primary_key=True, index=True)

    # Какой промокод был использован
    code = Column(String, unique=True, index=True, nullable=False)

    # Кто его использовал (или кому выдана награда)
    device_id = Column(String, nullable=False)

    # Когда создана запись (выдана или активирована)
    activated_at = Column(DateTime, default=datetime.utcnow)
    
    # Флаг использования для реферальных наград
    # Обычные промокоды всегда True (создаются при активации)
    # Реферальные коды сначала False (при выдаче), потом True (при активации)
    is_used = Column(Boolean, default=True, nullable=False)
