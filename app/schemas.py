"""
СХЕМЫ ДАННЫХ (PYDANTIC)
Описывают формат данных для API.
"""
from pydantic import BaseModel
from typing import Optional
from datetime import datetime


# ============================================
# ЗАПРОСЫ
# ============================================

class RegisterRequest(BaseModel):
    device_id: str

class CreatePaymentRequest(BaseModel):
    device_id: str
    plan: str

class ConfirmPaymentRequest(BaseModel):
    amount: float
    admin_key: str

class PromoRequest(BaseModel):
    device_id: str
    code: str

class ActivateTrialRequest(BaseModel):
    device_id: str


# ============================================
# ОТВЕТЫ
# ============================================

class SubscriptionResponse(BaseModel):
    is_active: bool
    days_left: int
    is_trial: bool
    plan: Optional[str] = None
    expires_at: Optional[datetime] = None

class PaymentResponse(BaseModel):
    unique_amount: float
    plan: str
    plan_name: str
    duration_days: int
    expires_in_minutes: int
    message: str

class PaymentStatusResponse(BaseModel):
    status: str
    unique_amount: float
    plan: str

class MessageResponse(BaseModel):
    message: str
    success: bool

# НОВАЯ СХЕМА ДЛЯ РЕФЕРАЛЬНОГО СТАТУСА
class ReferralStatusResponse(BaseModel):
    device_id: str
    referral_count: int
    target: int
    progress_percent: float
    reward_claimed: bool
    reward_code: Optional[str] = None
