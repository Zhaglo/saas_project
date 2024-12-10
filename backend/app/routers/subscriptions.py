import logging
from functools import wraps

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.models import Subscription, Payment, SubscriptionCancelRequest, SubscriptionResponse
from pydantic import BaseModel
from datetime import datetime, timedelta
from app.database import get_db
from app.dependencies import get_current_user
from app.dependencies import get_current_user_info
from app.models import User, Platform, PlatformSubscriptionRequest
from app.routers.payments import PaymentRequest

router = APIRouter()

# Логирование
logger = logging.getLogger(__name__)

class SubscriptionCreate(BaseModel):
    plan_name: str
    duration_days: int

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def get_current_user_role(token: str = Depends(oauth2_scheme)):
    user = get_current_user_info(token)
    return user.role

@router.get("/plans")
def get_subscription_plans():
    # Список доступных планов подписки
    plans = [
        {"id": 1, "name": "Basic", "price": 10, "duration_days": 30},
        {"id": 2, "name": "Pro", "price": 20, "duration_days": 60},
        {"id": 3, "name": "Premium", "price": 30, "duration_days": 90},
    ]
    return {"plans": plans}

@router.post("/")
def create_subscription(
    subscription: SubscriptionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    logger.info(f"Received request for subscription creation: {subscription}")

    # Проверка существования пользователя (больше не нужна, так как есть current_user)
    if not current_user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Проверка на существующую подписку
    existing_subscription = db.query(Subscription).filter(
        Subscription.user_id == current_user.id,
        Subscription.plan_name == subscription.plan_name,
        Subscription.status == "active"
    ).first()
    if existing_subscription:
        raise HTTPException(status_code=400, detail="User already has an active subscription for this plan")

    # Расчет даты начала и окончания подписки
    start_date = datetime.utcnow()
    end_date = start_date + timedelta(days=subscription.duration_days)

    # Создание нового объекта подписки
    new_subscription = Subscription(
        user_id=current_user.id,  # Используем ID текущего пользователя
        plan_name=subscription.plan_name,
        start_date=start_date,
        end_date=end_date,
        status="pending"
    )

    try:
        db.add(new_subscription)
        db.commit()
        db.refresh(new_subscription)
        logger.info(f"Subscription created successfully for user: {current_user.id}")
    except Exception as e:
        logger.error(f"Failed to create subscription for user {current_user.id}: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error while creating subscription")

    return {
        "message": "Subscription created successfully",
        "subscription": {
            "id": new_subscription.id,
            "plan_name": new_subscription.plan_name,
            "start_date": new_subscription.start_date,
            "end_date": new_subscription.end_date,
            "status": new_subscription.status
        }
    }

def get_user_subscriptions(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    # Получаем все подписки текущего пользователя
    subscriptions = db.query(Subscription).filter(Subscription.user_id == current_user.id).all()

    if not subscriptions:
        raise HTTPException(status_code=404, detail="No subscriptions found for this user")

    return {"subscriptions": subscriptions}

@router.post("/check-status/{subscription_id}")
def check_subscription_status(subscription_id: int, db: Session = Depends(get_db)):
    logger.info(f"Checking status for subscription {subscription_id}")

    try:
        # Ищем подписку по ID
        subscription = db.query(Subscription).filter(Subscription.id == subscription_id).first()
        if not subscription:
            logger.error(f"Subscription not found for ID {subscription_id}")
            raise HTTPException(status_code=404, detail="Subscription not found")

        # Проверка истечения срока подписки
        if subscription.end_date < datetime.utcnow().date():  # Сравниваем только дату (без времени)
            subscription.status = "expired"

        # Ищем платеж для подписки
        payment = db.query(Payment).filter(Payment.subscription_id == subscription_id).first()
        if payment:
            # Проверка статуса платежа
            if payment.status != "confirmed":
                subscription.status = "active"
        else:
            logger.info(f"No payment found for subscription {subscription_id}")

        db.commit()  # Сохраняем изменения в базе данных

        logger.info(f"Subscription {subscription_id} status updated to {subscription.status}")

        return {"message": "Subscription status updated", "status": subscription.status}

    except Exception as e:
        logger.error(f"Error occurred while checking subscription status: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

def role_required(role: str):
    def wrapper(fn):
        @wraps(fn)
        async def inner(*args, current_user: User = Depends(get_current_user), **kwargs):
            if current_user.role != role:
                raise HTTPException(status_code=403, detail="You don't have permission")
            return await fn(*args, **kwargs)
        return inner
    return wrapper

@router.post("/cancel_subscription")
@role_required("admin")
async def cancel_subscription(subscription_data: SubscriptionCancelRequest, db: Session = Depends(get_db),
                              current_user: User = Depends(get_current_user), token: str = Depends(oauth2_scheme)):
    # Можно отменить подписку как администратор для любого пользователя
    subscription = db.query(Subscription).filter(Subscription.id == subscription_data.subscription_id).first()

    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")

    # Если подписка активна, отменяем
    if subscription.status == "active":
        subscription.status = "cancelled"
        db.commit()
        return {"msg": "Subscription cancelled successfully"}

    raise HTTPException(status_code=400, detail="Subscription already cancelled")

def update_subscription_statuses(db: Session):
    current_date = datetime.utcnow().date()
    subscriptions = db.query(Subscription).filter(Subscription.status == "active").all()
    for subscription in subscriptions:
        if subscription.end_date < current_date:
            subscription.status = "expired"
    db.commit()

@router.get("/active")
def get_active_subscriptions(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    print(f"Fetching active subscriptions for user: {current_user.id}")
    update_subscription_statuses(db)
    subscriptions = db.query(Subscription).filter(
        Subscription.user_id == current_user.id,
        Subscription.status == "active"
    ).all()

    result = []
    for sub in subscriptions:
        result.append({
            "id": sub.id,
            "plan_name": sub.plan_name,
            "start_date": sub.start_date,
            "end_date": sub.end_date,
            "status": sub.status,
            "platform_name": sub.platform.name if sub.platform else "N/A"  # Извлечение имени платформы
        })
    return {"subscriptions": result}


@router.get("/expired")
def get_expired_subscriptions(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    update_subscription_statuses(db)
    expired_subscriptions = db.query(Subscription).filter(
        Subscription.user_id == current_user.id,
        Subscription.status == "expired"
    ).all()

    return {
        "expired_subscriptions": [
            {
                "id": sub.id,
                "plan_name": sub.plan_name,
                "start_date": sub.start_date,
                "end_date": sub.end_date,
                "platform_name": sub.platform.name if sub.platform else None,  # Добавлено
                "status": sub.status
            }
            for sub in expired_subscriptions
        ]
    }

@router.post("/extend")
def extend_subscription(subscription_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    subscription = db.query(Subscription).filter(
        Subscription.id == subscription_id,
        Subscription.user_id == current_user.id
    ).first()
    if not subscription or subscription.status != "active":
        raise HTTPException(status_code=404, detail="Subscription not found or not active")

    # Продлеваем срок действия подписки
    subscription.end_date += timedelta(days=30)
    db.commit()
    return {"message": "Subscription extended successfully", "subscription": subscription}

@router.post("/platforms/{platform_id}/subscribe")
def subscribe_to_platform(
    platform_id: int,
    request: PlatformSubscriptionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    platform = db.query(Platform).filter(Platform.id == platform_id).first()
    if not platform:
        raise HTTPException(status_code=404, detail="Platform not found")

    # Проверяем существующую активную подписку
    existing_subscription = db.query(Subscription).filter(
        Subscription.user_id == current_user.id,
        Subscription.platform_id == platform_id,
        Subscription.status == "active"
    ).first()

    if existing_subscription:
        # Меняем статус существующей подписки на 'cancelled'
        existing_subscription.status = "cancelled"
        db.commit()
        logger.info(f"Subscription (ID: {existing_subscription.id}) for user {current_user.id} cancelled")

    # Создаем новую подписку
    start_date = datetime.utcnow()
    end_date = start_date + timedelta(days=request.duration_days)
    new_subscription = Subscription(
        user_id=current_user.id,
        platform_id=platform_id,
        plan_name=request.plan_name,
        start_date=start_date,
        end_date=end_date,
        status="pending"
    )
    db.add(new_subscription)
    db.commit()
    db.refresh(new_subscription)

    # Создаем платеж
    payment_amount = request.duration_days * 10  # Пример расчета суммы
    payment_request = PaymentRequest(
        user_id=current_user.id,
        plan_name=request.plan_name,
        amount=payment_amount,
        subscription_id=new_subscription.id
    )

    try:
        # Вызов метода create_checkout_session для создания платежа
        from app.routers.payments import create_checkout_session  # Импортируем метод платежа
        payment_response = create_checkout_session(payment_request, db)

        return {
            "message": "Subscription created",
            "subscription": new_subscription,
            "payment_url": payment_response["url"]
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create payment: {str(e)}")


@router.get("/platforms/{platform_id}")
def get_platform_details(platform_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    platform = db.query(Platform).filter(Platform.id == platform_id).first()
    if not platform:
        raise HTTPException(status_code=404, detail="Platform not found")

    # Получение активных подписок пользователя для этой платформы
    current_subscription = db.query(Subscription).filter(
        Subscription.user_id == current_user.id,
        Subscription.platform_id == platform_id,
        Subscription.status == "active"
    ).first()

    # Описания планов подписки
    plans_dict = {
        6: [
            {"name": "Базовый", "price": 1000, "duration_days": 30, "description": "Основные функции управления облачными ресурсами.", "is_active": current_subscription and current_subscription.plan_name == "Базовый"},
            {"name": "Профессиональный", "price": 2000, "duration_days": 30, "description": "Расширенные функции, включая автоматизацию процессов.", "is_active": current_subscription and current_subscription.plan_name == "Профессиональный"},
            {"name": "Премиум", "price": 3000, "duration_days": 30, "description": "Все функции, приоритетная поддержка и аналитические отчеты.", "is_active": current_subscription and current_subscription.plan_name == "Премиум"},
        ],
        7: [
            {"name": "Стартовый", "price": 1500, "duration_days": 30, "description": "Базовые инструменты управления продажами.", "is_active": current_subscription and current_subscription.plan_name == "Стартовый"},
            {"name": "Продвинутый", "price": 2500, "duration_days": 30, "description": "Дополнительные функции аналитики и интеграции.", "is_active": current_subscription and current_subscription.plan_name == "Продвинутый"},
            {"name": "Экспертный", "price": 4000, "duration_days": 30, "description": "Полный набор инструментов и персональная поддержка.", "is_active": current_subscription and current_subscription.plan_name == "Экспертный"},
        ],
        8: [
            {"name": "Аналитик", "price": 2000, "duration_days": 30, "description": "Доступ к основным аналитическим данным.", "is_active": current_subscription and current_subscription.plan_name == "Аналитик"},
            {"name": "Стратег", "price": 3500, "duration_days": 30, "description": "Расширенные данные и прогнозы.", "is_active": current_subscription and current_subscription.plan_name == "Стратег"},
            {"name": "Гуру", "price": 5000, "duration_days": 30, "description": "Полный доступ ко всем данным и индивидуальные отчеты.", "is_active": current_subscription and current_subscription.plan_name == "Гуру"},
        ],
        9: [
            {"name": "Команда", "price": 1200, "duration_days": 30, "description": "Основные функции управления проектами для небольших команд.", "is_active": current_subscription and current_subscription.plan_name == "Команда"},
            {"name": "Бизнес", "price": 2500, "duration_days": 30, "description": "Расширенные функции для средних компаний.", "is_active": current_subscription and current_subscription.plan_name == "Бизнес"},
            {"name": "Корпоративный", "price": 4000, "duration_days": 30, "description": "Полный функционал для крупных организаций.", "is_active": current_subscription and current_subscription.plan_name == "Корпоративный"},
        ],
        10: [
            {"name": "Рекрутер", "price": 1000, "duration_days": 30, "description": "Инструменты для найма и отслеживания кандидатов.", "is_active": current_subscription and current_subscription.plan_name == "Рекрутер"},
            {"name": "Менеджер", "price": 2000, "duration_days": 30, "description": "Дополнительные функции адаптации и обучения.", "is_active": current_subscription and current_subscription.plan_name == "Менеджер"},
            {"name": "Директор", "price": 3500, "duration_days": 30, "description": "Полный спектр HR-инструментов и аналитики.", "is_active": current_subscription and current_subscription.plan_name == "Директор"},
        ]
    }

    plans = plans_dict.get(platform.id, [])
    return {
        "platform": platform,
        "plans": plans,
        "current_subscription": {
            "plan_name": current_subscription.plan_name,
            "end_date": current_subscription.end_date
        } if current_subscription else None
    }

@router.get("/platforms")
def get_platforms(db: Session = Depends(get_db)):
    platforms = db.query(Platform).all()
    return {"platforms": platforms}

@router.get("/{user_id}")
def get_subscriptions(user_id: int, db: Session = Depends(get_db)):
    # Получение всех подписок пользователя
    subscriptions = db.query(Subscription).filter(Subscription.user_id == user_id).all()
    if not subscriptions:
        raise HTTPException(status_code=404, detail="No subscriptions found for this user")

    for subscription in subscriptions:
        # Проверка истечения срока подписки
        if subscription.end_date < datetime.utcnow().date():
            subscription.status = "expired"

        # Проверка подтверждения платежа (предполагаем, что у подписки есть платеж)
        payment = db.query(Payment).filter(Payment.subscription_id == subscription.id).first()
        if payment and payment.status != "confirmed":
            subscription.status = "active"

        db.commit()  # Сохраняем изменения в базе данных

    return {"subscriptions": [SubscriptionResponse.from_orm(sub) for sub in subscriptions]}