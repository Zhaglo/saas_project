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
from app.models import User

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
    print(f"Found active subscriptions: {subscriptions}")
    return {"subscriptions": [sub for sub in subscriptions]}


@router.get("/expired")
def get_expired_subscriptions(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    update_subscription_statuses(db)
    expired_subscriptions = db.query(Subscription).filter(
        Subscription.user_id == current_user.id,
        Subscription.status == "expired"
    ).all()
    return {"expired_subscriptions": expired_subscriptions}

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