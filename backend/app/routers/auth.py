from functools import wraps
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, UserCreate, UserLogin, Subscription, SubscriptionCancelRequest
from passlib.context import CryptContext
from datetime import datetime, timedelta
from jose import jwt
from app.dependencies import verify_token, get_current_user
from app.routers.subscriptions import oauth2_scheme

# Инициализация CryptContext для хэширования пароля
pwd_context = CryptContext(schemes=["bcrypt", "sha256_crypt"], deprecated="auto")

router = APIRouter()

SECRET_KEY = "your_secret_key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Хешируем пароль
def hash_password(password: str):
    return pwd_context.hash(password)

# Функция для генерации JWT
def create_access_token(data: dict, expires_delta: timedelta = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)):
    to_encode = data.copy()
    expire = datetime.utcnow() + expires_delta
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def role_required(role: str):
    def wrapper(fn):
        @wraps(fn)
        async def inner(*args, **kwargs):
            # Получаем текущего пользователя с помощью зависимости
            current_user = kwargs.get('current_user')  # Или используй Depends(get_current_user)
            if current_user.role != role:
                raise HTTPException(status_code=403, detail="You don't have permission")
            return await fn(*args, **kwargs)
        return inner
    return wrapper

# Регистрация пользователя
@router.post("/register")
def register_user(user: UserCreate, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.email == user.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    hashed_password = hash_password(user.password)

    new_user = User(username=user.username, email=user.email, password_hash=hashed_password, role="user")
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {"message": "User registered successfully", "user": {"username": new_user.username, "role": new_user.role}}

# Авторизация пользователя и получение токена
@router.post("/login")
def login_user(user: UserLogin, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.email == user.email).first()
    if not db_user or not pwd_context.verify(user.password, db_user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token = create_access_token(data={"sub": db_user.username, "role": db_user.role})
    return {"access_token": access_token, "token_type": "bearer", "user_id": db_user.id, "role": db_user.role}

@router.get("/me/")
def get_current_user_info(db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    user_data = verify_token(token)
    user = db.query(User).filter(User.email == user_data["sub"]).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"username": user.username, "role": user.role}

@router.get("/admin-only/")
def admin_only(token: str = Depends(role_required("admin"))):
    return {"message": "You are an admin!"}

@router.post("/users/{user_id}/subscriptions/cancel")
async def cancel_user_subscription(
    user_id: int,
    request: SubscriptionCancelRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    subscription_id = request.subscription_id

    # Проверка роли текущего пользователя
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="You don't have permission to access this resource")

    # Проверка существования подписки
    subscription = db.query(Subscription).filter(
        Subscription.id == subscription_id,
        Subscription.user_id == user_id
    ).first()

    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")

    # Проверка статуса подписки
    if subscription.status != "active":
        raise HTTPException(status_code=400, detail="Only active subscriptions can be cancelled")

    # Отмена подписки
    subscription.status = "cancelled"
    db.commit()

    return {"message": f"Subscription {subscription_id} cancelled successfully"}

# Эндпоинт для получения подписок пользователя (доступен только администраторам)
@router.get("/users/{user_id}/subscriptions")
async def get_user_subscriptions(user_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Проверка роли текущего пользователя
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="You don't have permission to access this resource")

    # Получение подписок пользователя
    subscriptions = db.query(Subscription).filter(Subscription.user_id == user_id).all()

    if not subscriptions:
        return {"subscriptions": []}

    # Форматирование ответа
    return {
        "subscriptions": [
            {
                "id": sub.id,
                "plan_name": sub.plan_name,
                "start_date": sub.start_date,
                "end_date": sub.end_date,
                "status": sub.status,
            }
            for sub in subscriptions
        ]
    }

@router.get("/users")
async def get_users(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Проверка роли текущего пользователя
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="You don't have permission to access this resource")

    # Получение списка всех пользователей
    users = db.query(User).all()

    return {
        "users": [
            {"id": user.id, "username": user.username, "email": user.email, "role": user.role}
            for user in users
        ]
    }
