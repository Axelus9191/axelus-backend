"""
ГЛАВНЫЙ ФАЙЛ СЕРВЕРА AXELUS VPN
Здесь все API эндпоинты (маршруты).
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
    MessageResponse,
    ReferralStatusResponse  # ДОБАВЛЕНО
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

Base.metadata.create_all(bind=engine)

# ============================================
# ЭНДПОИНТЫ ДЛЯ VPN-ПРИЛОЖЕНИЯ (КЛИЕНТА)
# ============================================

@app.post("/register", response_model=MessageResponse)
def register(request: RegisterRequest, db: Session = Depends(get_db)):
    user = crud.register_user(db, request.device_id)
    return MessageResponse(message=f"Устройство зарегистрировано (id: {user.id})", success=True)

@app.get("/subscription/{device_id}", response_model=SubscriptionResponse)
def get_subscription(device_id: str, db: Session = Depends(get_db)):
    status = crud.get_subscription_status(db, device_id)
    return SubscriptionResponse(**status)

# НОВЫЙ ЭНДПОИНТ ДЛЯ ПРОВЕРКИ БОНУСОВ
@app.get("/referral/status/{device_id}", response_model=ReferralStatusResponse)
def get_referral_status(device_id: str, db: Session = Depends(get_db)):
    """
    Возвращает прогресс реферальной системы.
    Пример запроса: GET /referral/status/abc123def456
    """
    status = crud.get_referral_status(db, device_id)
    return ReferralStatusResponse(**status)

@app.post("/activate-trial", response_model=MessageResponse)
def activate_trial(request: ActivateTrialRequest, db: Session = Depends(get_db)):
    result = crud.activate_trial(db, request.device_id)
    return MessageResponse(**result)

@app.post("/payment/create")
def create_payment(request: CreatePaymentRequest, db: Session = Depends(get_db)):
    result = crud.create_payment(db, request.device_id, request.plan)
    if not result.get("success"):
        return MessageResponse(message=result["message"], success=False)
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
    result = crud.get_payment_status(db, device_id)
    return PaymentStatusResponse(**result)

@app.post("/promo/activate", response_model=MessageResponse)
def activate_promo(request: PromoRequest, db: Session = Depends(get_db)):
    result = crud.activate_promo(db, request.device_id, request.code)
    return MessageResponse(**result)

# ============================================
# ЭНДПОИНТ ДЛЯ АДМИНКИ
# ============================================

@app.post("/admin/confirm-payment", response_model=MessageResponse)
def confirm_payment(request: ConfirmPaymentRequest, db: Session = Depends(get_db)):
    result = crud.confirm_payment(db, request.amount, request.admin_key)
    return MessageResponse(**result)

# ============================================
# КОРНЕВОЙ ЭНДПОИНТ
# ============================================

@app.get("/")
def root():
    return {"name": "AXELUS VPN API", "version": "1.0.0", "status": "running"}
