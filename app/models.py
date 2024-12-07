from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    subscription_id = Column(Integer, ForeignKey("subscriptions.id"))
    plan_name = Column(String, nullable=False)
    amount = Column(Integer, nullable=False)
    status = Column(String, default="pending")

    # Связь с пользователем и подпиской
    user = relationship("User", back_populates="payments")
    subscription = relationship("Subscription", back_populates="payments")

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    password_hash = Column(String)

    # Связь с платежами и подписками
    payments = relationship("Payment", back_populates="user")
    subscriptions = relationship("Subscription", back_populates="user")

class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    plan_name = Column(String)
    start_date = Column(String)
    end_date = Column(String)
    status = Column(String, default="active")

    # Связь с пользователем и платежами
    user = relationship("User", back_populates="subscriptions")
    payments = relationship("Payment", back_populates="subscription")
