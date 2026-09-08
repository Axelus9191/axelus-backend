"""
CRUD — БИЗНЕС-ЛОГИКА
CRUD = Create, Read, Update, Delete

Здесь вся логика работы с данными:
- Регистрация пользователей
- Генерация уникальных сумм
- Подтверждение платежей
- Активация промокодов
- Проверка подписок
- Реферальная система
"""
import random
import string
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app import models
from app.config import (
    PLANS,
    PROMO_CODES,
    PAYMENT_TIMEOUT_MINUTES,
    MAX_PENDING_PAYMENTS,
    ADMIN_SECRET_KEY
)


# ============================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ РЕФЕРАЛОВ
# ============================================

def generate_referral_reward_code():
    """Генерирует уникальный промокод для награды вида REF-X7K9M2"""
    return "REF-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))


def process_referral_on_register(db: Session, new_device_id: str, referrer_device_id: str | None = None):
    """
    Обрабатывает реферальную связь при регистрации.
    Возвращает кортеж: (новый_пользователь, информация_о_награде_или_None)
    """
    # 1. Регистрируем нового пользователя
    user = register_user(db, new_device_id)
    
    reward_info = None
    
    # 2. Если есть реферер — обновляем его статистику
    if referrer_device_id and referrer_device_id != new_device_id:
        referrer = db.query(models.User).filter(
            models.User.device_id == referrer_device_id
        ).first()
        
        if referrer:
            # Привязываем нового пользователя к рефереру
            user.referred_by = referrer_device_id
            
            # Увеличиваем счетчик приглашений у реферера
            referrer.referral_count += 1
            
            # 3. Проверяем условие награды (ровно 10 друзей)
            if referrer.referral_count == 10:
                reward_code = generate_referral_reward_code()
                
                # Сохраняем награду как специальный промокод в БД
                # Но пока не активируем его, а просто создаем запись
                # Чтобы он стал доступен для активации
                reward_activation = models.PromoActivation(
                    code=reward_code,
                    device_id=referrer_device_id, # Привязываем к рефереру
                    activated_at=datetime.utcnow(), # Помечаем как "выданный", но не "использованный"
                    is_used=False # ВАЖНО: флаг что код еще не активирован
                )
                db.add(reward_activation)
                
                reward_info = {
                    "code": reward_code,
                    "days": 30,
                    "description": "Награда за 10 приглашенных друзей"
                }
                
    db.commit()
    return user, reward_info


# ============================================
# РЕГИСТРАЦИЯ ПОЛЬЗОВАТЕЛЯ
# ============================================

def register_user(db: Session, device_id: str) -> models.User:
    """
    Регистрирует новое устройство в системе.
    Логика:
    1. Проверяем — есть ли уже такой device_id в базе
    2. Если есть — просто возвращаем существующего пользователя
    3. Если нет — создаём нового
    """
    user = db.query(models.User).filter(
        models.User.device_id == device_id
    ).first()

    if user:
        return user

    user = models.User(device_id=device_id)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ============================================
# ПРОВЕРКА СТАТУСА РЕФЕРАЛОВ (НОВЫЙ ЭНДПОИНТ)
# ============================================

def get_referral_status(db: Session, device_id: str) -> dict:
    """
    Возвращает текущий прогресс реферальной системы.
    """
    user = db.query(models.User).filter(
        models.User.device_id == device_id
    ).first()

    if not user:
        return {
            "device_id": device_id,
            "referral_count": 0,
            "target": 10,
            "progress_percent": 0,
            "reward_claimed": False,
            "reward_code": None
        }

    # Проверяем, была ли уже выдана награда за 10 друзей
    # Ищем в таблице PromoActivation код, начинающийся с REF- и привязанный к этому устройству
    reward = db.query(models.PromoActivation).filter(
        models.PromoActivation.device_id == device_id,
        models.PromoActivation.code.like("REF-%"),
        models.PromoActivation.is_used == False
    ).first()

    return {
        "device_id": device_id,
        "referral_count": user.referral_count,
        "target": 10,
        "progress_percent": min((user.referral_count / 10) * 100, 100),
        "reward_claimed": reward is not None,
        "reward_code": reward.code if reward else None
    }


# ============================================
# ПРОВЕРКА ПОДПИСКИ
# ============================================

def get_subscription_status(db: Session, device_id: str) -> dict:
    """
    Проверяет активна ли подписка у пользователя.
    """
    user = db.query(models.User).filter(
        models.User.device_id == device_id
    ).first()

    if not user:
        return {
            "is_active": False,
            "days_left": 0,
            "is_trial": False,
            "plan": None,
            "expires_at": None
        }

    if not user.subscription_until:
        return {
            "is_active": False,
            "days_left": 0,
            "is_trial": False,
            "plan": None,
            "expires_at": None
        }

    now = datetime.utcnow()

    if user.subscription_until <= now:
        return {
            "is_active": False,
            "days_left": 0,
            "is_trial": False,
            "plan": None,
            "expires_at": user.subscription_until
        }

    delta = user.subscription_until - now
    days_left = delta.days

    if days_left > 50000:
        days_left = 99999

    is_trial = user.trial_used and days_left <= 3

    return {
        "is_active": True,
        "days_left": days_left,
        "is_trial": is_trial,
        "plan": "active",
        "expires_at": user.subscription_until
    }


# ============================================
# АКТИВАЦИЯ ПРОБНОГО ПЕРИОДА
# ============================================

def activate_trial(db: Session, device_id: str) -> dict:
    """
    Даёт пользователю 3 бесплатных дня.
    """
    user = register_user(db, device_id)

    if user.trial_used:
        return {
            "success": False,
            "message": "Пробный период уже был использован"
        }

    now = datetime.utcnow()
    user.subscription_until = now + timedelta(days=3)
    user.trial_used = True

    db.commit()

    return {
        "success": True,
        "message": "Пробный период активирован на 3 дня"
    }


# ============================================
# СОЗДАНИЕ ПЛАТЕЖА
# ============================================

def create_payment(db: Session, device_id: str, plan: str) -> dict:
    """
    Создаёт платёж с уникальной суммой.
    """
    if plan not in PLANS:
        return {"success": False, "message": f"Неизвестный тариф: {plan}"}

    plan_info = PLANS[plan]

    if plan == "trial":
        return {"success": False, "message": "Используйте /activate-trial"}

    register_user(db, device_id)

    db.query(models.Payment).filter(
        models.Payment.device_id == device_id,
        models.Payment.status == "pending"
    ).update({"status": "expired"})
    db.commit()

    now = datetime.utcnow()
    db.query(models.Payment).filter(
        models.Payment.status == "pending",
        models.Payment.expires_at < now
    ).update({"status": "expired"})
    db.commit()

    base_price = plan_info["base_price"]

    active_payments = db.query(models.Payment).filter(
        models.Payment.base_amount == base_price,
        models.Payment.status == "pending"
    ).all()

    used_kopecks = set()
    for p in active_payments:
        kopeck = round((p.unique_amount - base_price) * 100)
        used_kopecks.add(kopeck)

    unique_kopeck = None
    for k in range(1, MAX_PENDING_PAYMENTS + 1):
        if k not in used_kopecks:
            unique_kopeck = k
            break

    if unique_kopeck is None:
        return {
            "success": False,
            "message": "Слишком много платежей. Попробуйте через 5 минут."
        }

    unique_amount = base_price + unique_kopeck / 100.0
    unique_amount = round(unique_amount, 2)

    payment = models.Payment(
        device_id=device_id,
        plan=plan,
        base_amount=base_price,
        unique_amount=unique_amount,
        duration_days=plan_info["days"],
        status="pending",
        expires_at=now + timedelta(minutes=PAYMENT_TIMEOUT_MINUTES)
    )

    db.add(payment)
    db.commit()
    db.refresh(payment)

    return {
        "success": True,
        "unique_amount": unique_amount,
        "plan": plan,
        "plan_name": plan_info["name"],
        "duration_days": plan_info["days"],
        "expires_in_minutes": PAYMENT_TIMEOUT_MINUTES,
        "message": f"Переведите {unique_amount} ₽ на номер +7XXXXXXXXXX"
    }


# ============================================
# ПОДТВЕРЖДЕНИЕ ПЛАТЕЖА
# ============================================

def confirm_payment(db: Session, amount: float, admin_key: str) -> dict:
    """
    Подтверждает платёж по сумме от админки.
    """
    if admin_key != ADMIN_SECRET_KEY:
        return {"success": False, "message": "Неверный ключ администратора"}

    now = datetime.utcnow()

    db.query(models.Payment).filter(
        models.Payment.status == "pending",
        models.Payment.expires_at < now
    ).update({"status": "expired"})
    db.commit()

    amount = round(amount, 2)

    payment = db.query(models.Payment).filter(
        models.Payment.unique_amount == amount,
        models.Payment.status == "pending"
    ).first()

    if not payment:
        return {
            "success": False,
            "message": f"Платёж на сумму {amount} не найден или просрочен"
        }

    payment.status = "confirmed"
    payment.confirmed_at = now

    user = db.query(models.User).filter(
        models.User.device_id == payment.device_id
    ).first()

    if user:
        if user.subscription_until and user.subscription_until > now:
            start_date = user.subscription_until
        else:
            start_date = now

        user.subscription_until = start_date + timedelta(
            days=payment.duration_days
        )

    db.commit()

    return {
        "success": True,
        "message": (
            f"Платёж {amount} ₽ подтверждён. "
            f"Подписка '{payment.plan}' активирована для "
            f"устройства {payment.device_id}"
        )
    }


# ============================================
# ПРОВЕРКА СТАТУСА ПЛАТЕЖА
# ============================================

def get_payment_status(db: Session, device_id: str) -> dict:
    """
    Проверяет статус последнего платежа пользователя.
    """
    now = datetime.utcnow()

    db.query(models.Payment).filter(
        models.Payment.status == "pending",
        models.Payment.expires_at < now
    ).update({"status": "expired"})
    db.commit()

    payment = db.query(models.Payment).filter(
        models.Payment.device_id == device_id
    ).order_by(models.Payment.created_at.desc()).first()

    if not payment:
        return {
            "status": "none",
            "unique_amount": 0,
            "plan": ""
        }

    return {
        "status": payment.status,
        "unique_amount": payment.unique_amount,
        "plan": payment.plan
    }


# ============================================
# АКТИВАЦИЯ ПРОМОКОДА
# ============================================

def activate_promo(db: Session, device_id: str, code: str) -> dict:
    """
    Активирует промокод.
    Поддерживает как статические коды из config.py,
    так и динамические реферальные награды из БД.
    """
    code = code.strip().upper()

    # 1. Сначала проверяем динамические реферальные награды в БД
    # Ищем запись где код совпадает, device_id совпадает, и is_used=False
    reward_activation = db.query(models.PromoActivation).filter(
        models.PromoActivation.code == code,
        models.PromoActivation.device_id == device_id,
        models.PromoActivation.is_used == False
    ).first()

    promo_info = None
    
    if reward_activation:
        # Это реферальная награда
        promo_info = {
            "days": 30,
            "description": "Награда за 10 приглашенных друзей"
        }
    elif code in PROMO_CODES:
        # Это статический код из конфига
        promo_info = PROMO_CODES[code]
    else:
        return {"success": False, "message": "Промокод не найден"}

    # 2. Для обычных промокодов проверяем, не использован ли он кем-то вообще
    if not code.startswith("REF-"):
        existing_standard = db.query(models.PromoActivation).filter(
            models.PromoActivation.code == code
        ).first()

        if existing_standard:
            return {"success": False, "message": "Этот промокод уже использован"}

    # 3. Активируем подписку
    user = register_user(db, device_id)
    days = promo_info["days"]

    now = datetime.utcnow()
    if user.subscription_until and user.subscription_until > now:
        start_date = user.subscription_until
    else:
        start_date = now

    user.subscription_until = start_date + timedelta(days=days)

    # 4. Обновляем запись о промокоде
    if reward_activation:
        # Для реферальной награды просто помечаем как использованную
        reward_activation.is_used = True
    else:
        # Для обычного промокода создаем новую запись
        activation = models.PromoActivation(
            code=code,
            device_id=device_id,
            is_used=True
        )
        db.add(activation)

    db.commit()

    return {
        "success": True,
        "message": f"Промокод активирован! Подписка: {promo_info['description']}"
    }
