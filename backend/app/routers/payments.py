from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Payment, Subscription, PaymentRequest, PaymentRecord, ConfirmPaymentRequest
import random

router = APIRouter()

# Запрос для получения всех платежей
@router.get("/")
def list_all_payments(db: Session = Depends(get_db)):
    payments = db.query(Payment).all()
    if not payments:
        return {"message": "No payments found"}
    return payments

@router.post("/create-checkout-session")
def create_checkout_session(payment: PaymentRequest, db: Session = Depends(get_db)):  # Исправлено
    # Логируем входящие данные
    print(
        f"Received payment request: user_id={payment.user_id}, plan_name={payment.plan_name}, amount={payment.amount}"
    )
    # Проверяем корректность суммы
    if payment.amount <= 0:
        raise HTTPException(status_code=400, detail="Invalid payment amount")
    # Привязка к подписке
    subscription = db.query(Subscription).filter(
        Subscription.user_id == payment.user_id,
        Subscription.plan_name == payment.plan_name
    ).first()
    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")
    subscription_id = subscription.id  # Получаем ID подписки
    print(f"Found subscription_id: {subscription_id}")
    # Генерация платежа
    payment_id = random.randint(100000, 999999)
    new_payment = Payment(
        id=payment_id,
        user_id=payment.user_id,
        plan_name=payment.plan_name,
        amount=payment.amount,
        status="pending",
        subscription_id=subscription_id  # Используем ID подписки
    )
    try:
        db.add(new_payment)
        db.commit()
        db.refresh(new_payment)  # Обновляем объект из базы
    except Exception as e:
        db.rollback()
        print(f"Error creating payment: {e}")
        raise HTTPException(status_code=500, detail="Failed to create payment")

    # Генерация фейкового URL
    fake_url = f"http://176.108.250.41:80/checkout.html?payment_id={payment_id}"
    print(f"Payment created successfully. Redirect URL: {fake_url}")
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
        if subscription.end_date < datetime.utcnow().date():
            subscription.end_date = datetime.utcnow() + timedelta(days=30)
        db.commit()
        print(f"Payment {request.payment_id} confirmed. Subscription {subscription.id} activated.")
    else:
        print(f"No subscription found for payment {request.payment_id}")

    return {"message": "Payment confirmed and subscription activated"}
