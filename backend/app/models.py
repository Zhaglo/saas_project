from sqlalchemy import Column, Integer, String, ForeignKey, Date
from sqlalchemy.orm import relationship
from datetime import date
from app.database import Base
from pydantic import BaseModel

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
    role = Column(String, default="user")

    # Связь с платежами и подписками
    payments = relationship("Payment", back_populates="user")
    subscriptions = relationship("Subscription", back_populates="user")

class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    plan_name = Column(String)
    start_date = Column(Date)
    end_date = Column(Date)
    status = Column(String, default="active")
    platform_id = Column(Integer, ForeignKey("platforms.id"))

    # Связь с пользователем и платежами
    user = relationship("User", back_populates="subscriptions")
    payments = relationship("Payment", back_populates="subscription")  # Изменение: payments = relationship
    platform = relationship("Platform", back_populates="subscriptions")

class SubscriptionCancelRequest(BaseModel):
    subscription_id: int  # Идентификатор подписки, которую нужно отменить

class SubscriptionResponse(BaseModel):
    id: int
    user_id: int
    plan_name: str
    start_date: date
    end_date: date
    status: str

    class Config:
        from_attributes = True  # Это нужно, чтобы Pydantic понимал объекты SQLAlchemy

class Platform(Base):
    __tablename__ = "platforms"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=False)
    image_url = Column(String, nullable=False)

    subscriptions = relationship("Subscription", back_populates="platform")

class PlatformSubscriptionRequest(BaseModel):
    plan_name: str
    duration_days: int
