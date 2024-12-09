from functools import wraps

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.database import get_db
from app.models import User
from passlib.context import CryptContext
from datetime import datetime, timedelta
from jose import jwt
from app.dependencies import verify_token

from app.routers.subscriptions import oauth2_scheme

# Инициализация CryptContext для хэширования пароля
pwd_context = CryptContext(schemes=["bcrypt", "sha256_crypt"], deprecated="auto")

router = APIRouter()

SECRET_KEY = "your_secret_key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30


# Модель для данных при регистрации
class UserCreate(BaseModel):
    username: str
    email: str
    password: str
    role: str = "user"

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

# Модель данных для логина
class UserLogin(BaseModel):
    email: str
    password: str


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
    return {"access_token": access_token, "token_type": "bearer", "user_id": db_user.id}

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
