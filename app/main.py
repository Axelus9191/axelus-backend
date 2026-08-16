"""
============================================
ГЛАВНЫЙ ФАЙЛ СЕРВЕРА AXELUS VPN
============================================
Здесь все API эндпоинты (маршруты).

Запуск сервера:
    cd axelus-backend
    python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

После запуска открой в браузере:
    http://localhost:8000/docs

Там будет красивая документация (Swagger UI)
где можно тестировать все эндпоинты прямо в браузере.
"""

from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session

from app.database import engine, Base, get_db
from app.schemas import (
    RegisterRequest,
    CreatePaymentRequest,
    ConfirmPaymentRequest,
    PromoRequest,
    ActivateTrialRequest,
    SubscriptionResponse,
    PaymentResponse,
    PaymentStatusResponse,
    MessageResponse
)
from app import crud

# ============================================
# СОЗДАЁМ ПРИЛОЖЕНИЕ
# ============================================

app = FastAPI(
    title="AXELUS VPN API",
    description="API сервер для управления подписками AXELUS VPN",
    version="1.0.0"
)

# ============================================
# СОЗДАЁМ ТАБЛИЦЫ В БАЗЕ ДАННЫХ
# ============================================
# При первом запуске SQLAlchemy посмотрит на модели
# (User, Payment, PromoActivation) и создаст
# соответствующие таблицы в файле axelus.db
# Если таблицы уже есть — ничего не произойдёт.

Base.metadata.create_all(bind=engine)


# ============================================
# ЭНДПОИНТЫ ДЛЯ VPN-ПРИЛОЖЕНИЯ (КЛИЕНТА)
# ============================================

@app.post("/register", response_model=MessageResponse)
def register(request: RegisterRequest, db: Session = Depends(get_db)):
    """
    Регистрация устройства.

    Вызывается при первом запуске приложения.
    Если устройство уже зарегистрировано — просто вернёт "ok".

    Пример запроса:
        POST /register
        {"device_id": "abc123def456"}
    """
    user = crud.register_user(db, request.device_id)
    return MessageResponse(
        message=f"Устройство зарегистрировано (id: {user.id})",
        success=True
    )


@app.get("/subscription/{device_id}", response_model=SubscriptionResponse)
def get_subscription(device_id: str, db: Session = Depends(get_db)):
    """
    Проверка статуса подписки.

    Клиент вызывает это:
    - При запуске приложения
    - При нажатии кнопки "Подключить"
    - После оплаты (polling каждые 5 сек)

    Пример запроса:
        GET /subscription/abc123def456
    """
    status = crud.get_subscription_status(db, device_id)
    return SubscriptionResponse(**status)


@app.post("/activate-trial", response_model=MessageResponse)
def activate_trial(
    request: ActivateTrialRequest,
    db: Session = Depends(get_db)
):
    """
    Активация пробного периода (3 дня бесплатно).

    Можно использовать ОДИН раз на устройство.
    Повторный вызов вернёт ошибку.

    Пример запроса:
        POST /activate-trial
        {"device_id": "abc123def456"}
    """
    result = crud.activate_trial(db, request.device_id)
    return MessageResponse(**result)


@app.post("/payment/create")
def create_payment(
    request: CreatePaymentRequest,
    db: Session = Depends(get_db)
):
    """
    Создание платежа — генерация уникальной суммы.

    Клиент выбирает тариф, сервер возвращает
    уникальную сумму для перевода.

    Пример запроса:
        POST /payment/create
        {"device_id": "abc123def456", "plan": "month"}

    Пример ответа:
        {"unique_amount": 149.03, "plan": "month", ...}
    """
    result = crud.create_payment(db, request.device_id, request.plan)

    if not result.get("success"):
        return MessageResponse(
            message=result["message"],
            success=False
        )

    return PaymentResponse(
        unique_amount=result["unique_amount"],
        plan=result["plan"],
        plan_name=result["plan_name"],
        duration_days=result["duration_days"],
        expires_in_minutes=result["expires_in_minutes"],
        message=result["message"]
    )


@app.get("/payment/status/{device_id}", response_model=PaymentStatusResponse)
def payment_status(device_id: str, db: Session = Depends(get_db)):
    """
    Проверка статуса платежа.

    Клиент вызывает это каждые 5 секунд после создания платежа.
    Как только статус станет "confirmed" — подписка активна.

    Пример запроса:
        GET /payment/status/abc123def456
    """
    result = crud.get_payment_status(db, device_id)
    return PaymentStatusResponse(**result)


@app.post("/promo/activate", response_model=MessageResponse)
def activate_promo(request: PromoRequest, db: Session = Depends(get_db)):
    """
    Активация промокода.

    Пример запроса:
        POST /promo/activate
        {"device_id": "abc123def456", "code": "AXELUS-OWNER-001"}
    """
    result = crud.activate_promo(db, request.device_id, request.code)
    return MessageResponse(**result)


# ============================================
# ЭНДПОИНТ ДЛЯ АДМИНКИ
# ============================================

@app.post("/admin/confirm-payment", response_model=MessageResponse)
def confirm_payment(
    request: ConfirmPaymentRequest,
    db: Session = Depends(get_db)
):
    """
    Подтверждение платежа администратором.

    Вызывается админкой когда она парсит пуш от Сбера.
    Требует admin_key для безопасности.

    Пример запроса:
        POST /admin/confirm-payment
        {"amount": 149.03, "admin_key": "secret123"}
    """
    result = crud.confirm_payment(db, request.amount, request.admin_key)
    return MessageResponse(**result)


# ============================================
# КОРНЕВОЙ ЭНДПОИНТ (ПРОВЕРКА ЧТО СЕРВЕР ЖИВА)
# ============================================

@app.get("/")
def root():
    """
    Просто проверка что сервер работает.
    Открой http://localhost:8000/ в браузере.
    """
    return {
        "name": "AXELUS VPN API",
        "version": "1.0.0",
        "status": "running"
    }