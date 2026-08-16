"""
============================================
CRUD — БИЗНЕС-ЛОГИКА
============================================
CRUD = Create, Read, Update, Delete

Здесь вся логика работы с данными:
- Регистрация пользователей
- Генерация уникальных сумм
- Подтверждение платежей
- Активация промокодов
- Проверка подписок

Каждая функция делает ОДНУ конкретную вещь.
"""

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
# РЕГИСТРАЦИЯ ПОЛЬЗОВАТЕЛЯ
# ============================================

def register_user(db: Session, device_id: str) -> models.User:
    """
    Регистрирует новое устройство в системе.

    Логика:
    1. Проверяем — есть ли уже такой device_id в базе
    2. Если есть — просто возвращаем существующего пользователя
    3. Если нет — создаём нового

    Это безопасно вызывать сколько угодно раз —
    повторная регистрация не создаст дубликат.
    """

    # Ищем пользователя в базе
    user = db.query(models.User).filter(
        models.User.device_id == device_id
    ).first()

    # Если уже существует — возвращаем его
    if user:
        return user

    # Создаём нового пользователя
    user = models.User(device_id=device_id)

    # Добавляем в базу
    db.add(user)

    # Сохраняем изменения
    db.commit()

    # Обновляем объект (чтобы получить id который база присвоила)
    db.refresh(user)

    return user


# ============================================
# ПРОВЕРКА ПОДПИСКИ
# ============================================

def get_subscription_status(db: Session, device_id: str) -> dict:
    """
    Проверяет активна ли подписка у пользователя.

    Логика:
    1. Находим пользователя по device_id
    2. Если subscription_until не задан — подписки нет
    3. Если subscription_until в будущем — подписка активна
    4. Если subscription_until в прошлом — подписка истекла

    Возвращает словарь с полями:
    - is_active: True/False
    - days_left: сколько дней осталось
    - is_trial: это пробный период или нет
    """

    user = db.query(models.User).filter(
        models.User.device_id == device_id
    ).first()

    # Пользователь не найден
    if not user:
        return {
            "is_active": False,
            "days_left": 0,
            "is_trial": False,
            "plan": None,
            "expires_at": None
        }

    # Подписка не установлена
    if not user.subscription_until:
        return {
            "is_active": False,
            "days_left": 0,
            "is_trial": False,
            "plan": None,
            "expires_at": None
        }

    now = datetime.utcnow()

    # Подписка истекла
    if user.subscription_until <= now:
        return {
            "is_active": False,
            "days_left": 0,
            "is_trial": False,
            "plan": None,
            "expires_at": user.subscription_until
        }

    # Подписка активна — считаем сколько дней осталось
    delta = user.subscription_until - now
    days_left = delta.days

    # Если осталось больше 50000 дней — это "навсегда"
    if days_left > 50000:
        days_left = 99999

    # Определяем это пробный период или нет
    # Пробный = подписка активна И trial_used = True
    # И осталось <= 3 дней
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

    Логика:
    1. Находим пользователя
    2. Проверяем — использовал ли он уже пробный период
    3. Если использовал — отказываем
    4. Если нет — даём 3 дня и помечаем trial_used = True

    Пробный период даётся ОДИН раз на устройство.
    Нельзя удалить приложение и получить ещё 3 дня —
    device_id остаётся тем же.
    """

    # Регистрируем (или находим) пользователя
    user = register_user(db, device_id)

    # Уже использовал пробный период
    if user.trial_used:
        return {
            "success": False,
            "message": "Пробный период уже был использован"
        }

    # Даём 3 дня
    now = datetime.utcnow()
    user.subscription_until = now + timedelta(days=3)
    user.trial_used = True

    db.commit()

    return {
        "success": True,
        "message": "Пробный период активирован на 3 дня"
    }


# ============================================
# СОЗДАНИЕ ПЛАТЕЖА (ГЕНЕРАЦИЯ УНИКАЛЬНОЙ СУММЫ)
# ============================================

def create_payment(db: Session, device_id: str, plan: str) -> dict:
    """
    Создаёт платёж с уникальной суммой.

    Логика:
    1. Проверяем что тариф существует
    2. Регистрируем пользователя (если ещё не зарегистрирован)
    3. Отменяем предыдущие неоплаченные платежи этого юзера
    4. Находим свободную копеечную добавку (01, 02, 03...)
    5. Создаём платёж со статусом "pending"
    6. Возвращаем уникальную сумму

    Пример:
    - Тариф "month" стоит 149 руб
    - Уже есть pending платежи на 149.01 и 149.02
    - Значит выдаём 149.03
    - Юзер переводит ровно 149.03 руб
    - Админка видит пуш "149.03" и подтверждает
    """

    # Проверяем что тариф существует
    if plan not in PLANS:
        return {"success": False, "message": f"Неизвестный тариф: {plan}"}

    plan_info = PLANS[plan]

    # Пробный период нельзя "купить"
    if plan == "trial":
        return {"success": False, "message": "Используйте /activate-trial"}

    # Регистрируем пользователя
    register_user(db, device_id)

    # Отменяем старые pending платежи этого юзера
    # (чтобы не было путаницы если он передумал и выбрал другой тариф)
    db.query(models.Payment).filter(
        models.Payment.device_id == device_id,
        models.Payment.status == "pending"
    ).update({"status": "expired"})
    db.commit()

    # Помечаем просроченные платежи ВСЕХ юзеров
    now = datetime.utcnow()
    db.query(models.Payment).filter(
        models.Payment.status == "pending",
        models.Payment.expires_at < now
    ).update({"status": "expired"})
    db.commit()

    # Ищем свободную копейку
    base_price = plan_info["base_price"]

    # Получаем все занятые копейки для этой базовой цены
    active_payments = db.query(models.Payment).filter(
        models.Payment.base_amount == base_price,
        models.Payment.status == "pending"
    ).all()

    # Собираем множество занятых копеек
    used_kopecks = set()
    for p in active_payments:
        # Вытаскиваем копейки: 149.03 → 3
        kopeck = round((p.unique_amount - base_price) * 100)
        used_kopecks.add(kopeck)

    # Находим первую свободную копейку
    unique_kopeck = None
    for k in range(1, MAX_PENDING_PAYMENTS + 1):
        if k not in used_kopecks:
            unique_kopeck = k
            break

    # Все слоты заняты (99 человек одновременно платят)
    if unique_kopeck is None:
        return {
            "success": False,
            "message": "Слишком много платежей. Попробуйте через 5 минут."
        }

    # Формируем уникальную сумму
    unique_amount = base_price + unique_kopeck / 100.0
    # Округляем чтобы не было 149.0000000001
    unique_amount = round(unique_amount, 2)

    # Создаём платёж
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
# ПОДТВЕРЖДЕНИЕ ПЛАТЕЖА (ОТ АДМИНКИ)
# ============================================

def confirm_payment(db: Session, amount: float, admin_key: str) -> dict:
    """
    Подтверждает платёж по сумме.
    Вызывается админкой когда она видит пуш от Сбера.

    Логика:
    1. Проверяем админский ключ
    2. Ищем pending платёж с такой суммой
    3. Если нашли — активируем подписку
    4. Если не нашли — возвращаем ошибку

    Безопасность:
    - Без правильного admin_key подтвердить нельзя
    - Подтвердить можно только pending платёж
    - Просроченные платежи не подтверждаются
    """

    # Проверяем админский ключ
    if admin_key != ADMIN_SECRET_KEY:
        return {"success": False, "message": "Неверный ключ администратора"}

    now = datetime.utcnow()

    # Сначала помечаем просроченные
    db.query(models.Payment).filter(
        models.Payment.status == "pending",
        models.Payment.expires_at < now
    ).update({"status": "expired"})
    db.commit()

    # Ищем pending платёж с такой суммой
    # Округляем до 2 знаков для точного сравнения
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

    # Нашли платёж! Подтверждаем его
    payment.status = "confirmed"
    payment.confirmed_at = now

    # Активируем подписку пользователю
    user = db.query(models.User).filter(
        models.User.device_id == payment.device_id
    ).first()

    if user:
        # Если подписка уже есть — продлеваем от текущей даты окончания
        # Если подписки нет — начинаем от сейчас
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
    Клиент вызывает это каждые 5 секунд после создания платежа,
    чтобы узнать — подтвердили его или нет.
    """

    now = datetime.utcnow()

    # Помечаем просроченные
    db.query(models.Payment).filter(
        models.Payment.status == "pending",
        models.Payment.expires_at < now
    ).update({"status": "expired"})
    db.commit()

    # Берём последний платёж пользователя
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

    Логика:
    1. Приводим код к верхнему регистру (axelus-owner-001 → AXELUS-OWNER-001)
    2. Проверяем что такой промокод существует в config.py
    3. Проверяем что он ещё не был использован
    4. Если всё ок — активируем подписку и записываем использование

    Каждый промокод можно использовать ТОЛЬКО ОДИН РАЗ.
    """

    # Приводим к верхнему регистру
    code = code.strip().upper()

    # Проверяем существование промокода
    if code not in PROMO_CODES:
        return {"success": False, "message": "Промокод не найден"}

    # Проверяем — не использован ли уже
    existing = db.query(models.PromoActivation).filter(
        models.PromoActivation.code == code
    ).first()

    if existing:
        return {"success": False, "message": "Этот промокод уже использован"}

    # Регистрируем пользователя
    user = register_user(db, device_id)

    # Получаем данные промокода
    promo_info = PROMO_CODES[code]
    days = promo_info["days"]

    # Активируем подписку
    now = datetime.utcnow()

    if user.subscription_until and user.subscription_until > now:
        start_date = user.subscription_until
    else:
        start_date = now

    user.subscription_until = start_date + timedelta(days=days)

    # Записываем что промокод использован
    activation = models.PromoActivation(
        code=code,
        device_id=device_id
    )
    db.add(activation)

    db.commit()

    return {
        "success": True,
        "message": f"Промокод активирован! Подписка: {promo_info['description']}"
    }