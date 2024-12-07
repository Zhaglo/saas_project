from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Payment, Subscription
import random

router = APIRouter()

# Хранилище платежей
# payments = [
#     {"payment_id": 1, "user_id": 1, "plan_name": "Premium", "amount": 1000, "status": "confirmed", "subscription_id": 1},
#     {"payment_id": 2, "user_id": 2, "plan_name": "Basic", "amount": 500, "status": "pending", "subscription_id": 2},
#     {"payment_id": 123456, "user_id": 3, "plan_name": "Standard", "amount": 1500, "status": "pending", "subscription_id": 3}  # Добавлен тестовый платёж
# ]
#
# # Пример фейковых подписок
# subscriptions = [
#     {"id": 1, "user_id": 1, "plan_name": "Premium", "status": "active"},
#     {"id": 2, "user_id": 2, "plan_name": "Basic", "status": "inactive"},
#     {"id": 3, "user_id": 3, "plan_name": "Standard", "status": "inactive"}
# ]

class PaymentRequest(BaseModel):
    user_id: int
    plan_name: str
    amount: int  # Сумма в центах

class PaymentRecord(BaseModel):
    payment_id: int
    user_id: int
    plan_name: str
    amount: int
    status: str
    subscription_id: int  # добавленное поле для подписки

class ConfirmPaymentRequest(BaseModel):
    payment_id: int

# def find_subscription_id(user_id: int, plan_name: str):
#     for subscription in subscriptions:
#         if subscription["user_id"] == user_id and subscription["plan_name"] == plan_name:
#             return subscription["id"]
#     return None

# Запрос для получения всех платежей
@router.get("/")
def list_all_payments(db: Session = Depends(get_db)):
    payments = db.query(Payment).all()
    if not payments:
        return {"message": "No payments found"}
    return payments


@router.post("/create-checkout-session")
def create_checkout_session(payment: PaymentRequest, db: Session = Depends(get_db)):  # Исправлено
    # Проверяем корректность суммы
    if payment.amount <= 0:
        raise HTTPException(status_code=400, detail="Invalid payment amount")

    # Привязка к подписке
    subscription_id = db.query(Subscription.id).filter(
        Subscription.user_id == payment.user_id,
        Subscription.plan_name == payment.plan_name
    ).first()
    if not subscription_id:
        raise HTTPException(status_code=404, detail="Subscription not found")

    # Генерация платежа
    payment_id = random.randint(100000, 999999)
    new_payment = Payment(
        id=payment_id,
        user_id=payment.user_id,
        plan_name=payment.plan_name,
        amount=payment.amount,
        status="pending",
        subscription_id=subscription_id[0]  # Используем ID подписки
    )
    db.add(new_payment)
    db.commit()

    # Генерация фейкового URL
    fake_url = f"https://fake-payment-provider.com/checkout/{payment_id}"
    return {"url": fake_url, "payment_id": payment_id}

@router.post("/confirm-payment")
def confirm_payment(request: ConfirmPaymentRequest, db: Session = Depends(get_db)):
    print(f"Confirming payment with payment_id {request.payment_id}")

    # Поиск платежа в БД
    payment = db.query(Payment).filter(Payment.id == request.payment_id).first()

    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    # Обновление статуса платежа
    payment.status = "confirmed"
    db.commit()

    # Обновление статуса подписки, если платеж подтвержден
    subscription = db.query(Subscription).filter(Subscription.id == payment.subscription_id).first()
    if subscription:
        subscription.status = "active"
        db.commit()

    return {"message": "Payment confirmed successfully", "payment_id": payment.id}
