import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import Subscription, User
from pydantic import BaseModel
from datetime import datetime, timedelta
from app.database import get_db

router = APIRouter()

# Логирование
logger = logging.getLogger(__name__)

class SubscriptionCreate(BaseModel):
    user_id: int
    plan_name: str
    duration_days: int

@router.post("/")
def create_subscription(subscription: SubscriptionCreate, db: Session = Depends(get_db)):
    print("Received request for subscription creation")  # Лог для отладки

    # Проверка существования пользователя
    user = db.query(User).filter(User.id == subscription.user_id).first()
    if not user:
        print(f"User not found: {subscription.user_id}")  # Лог для отладки
        raise HTTPException(status_code=404, detail="User not found")

    # Расчет даты начала и окончания подписки
    start_date = datetime.utcnow()
    end_date = start_date + timedelta(days=subscription.duration_days)

    # Создание нового объекта подписки
    new_subscription = Subscription(
        user_id=subscription.user_id,
        plan_name=subscription.plan_name,
        start_date=start_date.strftime('%Y-%m-%d'),  # Форматируем дату в строку
        end_date=end_date.strftime('%Y-%m-%d'),    # Форматируем дату в строку
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

@router.get("/")
def get_all_subscriptions(db: Session = Depends(get_db)):
    # Получение всех подписок в системе
    subscriptions = db.query(Subscription).all()
    if not subscriptions:
        raise HTTPException(status_code=404, detail="No subscriptions found")
    return {"subscriptions": subscriptions}

@router.get("/{user_id}")
def get_subscriptions(user_id: int, db: Session = Depends(get_db)):
    # Получение всех подписок пользователя
    subscriptions = db.query(Subscription).filter(Subscription.user_id == user_id).all()
    if not subscriptions:
        raise HTTPException(status_code=404, detail="No subscriptions found for this user")
    return {"subscriptions": subscriptions}
