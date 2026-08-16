"""
============================================
СХЕМЫ ДАННЫХ (PYDANTIC)
============================================
Схемы описывают ФОРМАТ данных:
- Что приходит в запросе (Request)
- Что уходит в ответе (Response)

Pydantic автоматически проверяет данные.
Если клиент пришлёт device_id как число
вместо строки — сервер вернёт ошибку 422.

Это как контракт между клиентом и сервером:
"Я жду от тебя вот такие данные, не другие."
"""

from pydantic import BaseModel
from typing import Optional
from datetime import datetime


# ============================================
# ЗАПРОСЫ (то что ПРИХОДИТ на сервер)
# ============================================

class RegisterRequest(BaseModel):
    """
    Регистрация нового устройства.
    Клиент присылает свой device_id.

    Пример JSON:
    {"device_id": "abc123def456"}
    """
    device_id: str


class CreatePaymentRequest(BaseModel):
    """
    Запрос на создание платежа.
    Клиент говорит: "Я хочу купить тариф month"

    Пример JSON:
    {"device_id": "abc123def456", "plan": "month"}
    """
    device_id: str
    plan: str  # week / month / half_year / year / forever


class ConfirmPaymentRequest(BaseModel):
    """
    Подтверждение платежа от админки.
    Админка парсит пуш от Сбера и присылает сумму.

    Пример JSON:
    {"amount": 149.03, "admin_key": "secret123"}
    """
    amount: float
    admin_key: str


class PromoRequest(BaseModel):
    """
    Активация промокода.
    Клиент вводит промокод в приложении.

    Пример JSON:
    {"device_id": "abc123def456", "code": "AXELUS-OWNER-001"}
    """
    device_id: str
    code: str


class ActivateTrialRequest(BaseModel):
    """
    Активация пробного периода.

    Пример JSON:
    {"device_id": "abc123def456"}
    """
    device_id: str


# ============================================
# ОТВЕТЫ (то что УХОДИТ с сервера)
# ============================================

class SubscriptionResponse(BaseModel):
    """
    Статус подписки пользователя.
    Клиент получает это при проверке подписки.

    Пример JSON:
    {
        "is_active": true,
        "days_left": 28,
        "is_trial": false,
        "plan": "month",
        "expires_at": "2024-02-15T10:30:00"
    }
    """
    is_active: bool
    days_left: int
    is_trial: bool
    plan: Optional[str] = None
    expires_at: Optional[datetime] = None


class PaymentResponse(BaseModel):
    """
    Информация о созданном платеже.
    Клиент получает уникальную сумму для оплаты.

    Пример JSON:
    {
        "unique_amount": 149.03,
        "plan": "month",
        "plan_name": "Месяц",
        "duration_days": 30,
        "expires_in_minutes": 20,
        "message": "Переведите 149.03 ₽ на номер..."
    }
    """
    unique_amount: float
    plan: str
    plan_name: str
    duration_days: int
    expires_in_minutes: int
    message: str


class PaymentStatusResponse(BaseModel):
    """
    Статус конкретного платежа.
    Клиент проверяет: "Мой платёж уже подтвердили?"

    Пример JSON:
    {
        "status": "confirmed",
        "unique_amount": 149.03,
        "plan": "month"
    }
    """
    status: str  # pending / confirmed / expired
    unique_amount: float
    plan: str


class MessageResponse(BaseModel):
    """
    Простое сообщение.
    Используется для ответов типа "Успешно!"

    Пример JSON:
    {"message": "Промокод активирован", "success": true}
    """
    message: str
    success: bool