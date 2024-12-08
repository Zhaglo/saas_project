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
    user_id: int
    plan_name: str
    duration_days: int

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def get_current_user_role(token: str = Depends(oauth2_scheme)):
    user = get_current_user_info(token)
    return user.role

@router.post("/")
def create_subscription(subscription: SubscriptionCreate, db: Session = Depends(get_db)):
    print("Received request for subscription creation")  # Лог для отладки

    # Проверка существования пользователя
    user = db.query(User).filter(User.id == subscription.user_id).first()
    if not user:
        print(f"User not found: {subscription.user_id}")  # Лог для отладки
        raise HTTPException(status_code=404, detail="User not found")

    # Расчет даты начала и окончания подписки
    start_date = datetime.utcnow()  # Используем datetime с временем
    end_date = start_date + timedelta(days=subscription.duration_days)

    # Преобразуем в строки сразу в нужном формате
    start_date_str = start_date.strftime('%Y-%m-%d')  # Строка без времени
    end_date_str = end_date.strftime('%Y-%m-%d')      # Строка без времени

    # Создание нового объекта подписки
    new_subscription = Subscription(
        user_id=subscription.user_id,
        plan_name=subscription.plan_name,
        start_date=start_date_str,  # Строковое представление даты
        end_date=end_date_str,      # Строковое представление даты
        status="active"
    )

    print(f"Subscription created for user: {subscription.user_id}")  # Лог для отладки

    try:
        db.add(new_subscription)
        db.commit()
        db.refresh(new_subscription)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to create subscription")

    return {"message": "Subscription created successfully", "subscription": new_subscription}


def get_user_subscriptions(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    # Получаем все подписки текущего пользователя
    subscriptions = db.query(Subscription).filter(Subscription.user_id == current_user.id).all()

    if not subscriptions:
        raise HTTPException(status_code=404, detail="No subscriptions found for this user")

    return {"subscriptions": subscriptions}


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
