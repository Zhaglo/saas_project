from app.routers import auth
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import payments, subscriptions
from app.database import Base, engine

# Пересоздаем таблицы
Base.metadata.create_all(bind=engine)
print("База данных и таблицы успешно созданы.")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://176.108.250.41"],  # Указываем домен фронтенда
    allow_credentials=True,
    allow_methods=["*"],  # Разрешаем все методы
    allow_headers=["*"],  # Разрешаем все заголовки
)
@app.get("/")
def read_root():
    return {"message": "Hello World"}

app.include_router(auth.router, prefix="/api/auth")
app.include_router(subscriptions.router, prefix="/api/subscriptions", tags=["subscriptions"])
app.include_router(payments.router, prefix="/api/payments")