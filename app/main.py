from app.database import Base, engine
from app.routers import auth, subscriptions
from fastapi import FastAPI
from app.routers import payments
from app.database import Base, engine
from app.models import User, Subscription, Payment

# Пересоздаем таблицы
Base.metadata.create_all(bind=engine)
print("База данных и таблицы успешно созданы.")

app = FastAPI()

app.include_router(auth.router, prefix="/api/auth")
app.include_router(subscriptions.router, prefix="/api/subscriptions")
app.include_router(payments.router, prefix="/api/payments")