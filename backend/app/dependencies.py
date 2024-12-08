from fastapi import HTTPException, Depends
from jose import jwt, JWTError
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordBearer
from app.database import get_db
from app.models import User

SECRET_KEY = "your_secret_key"
ALGORITHM = "HS256"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")


# Функция для декодирования токена
def verify_token(token: str):
    try:
        print(f"Verifying token: {token}")  # Логируем токен для отладки
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        # Проверка наличия обязательных данных в payload
        email: str = payload.get("sub")
        role: str = payload.get("role")
        exp: int = payload.get("exp")

        if email is None or role is None:
            raise HTTPException(status_code=403, detail="Could not validate credentials")

        return payload
    except JWTError as e:
        print(f"JWTError: {str(e)}")  # Логируем ошибку
        raise HTTPException(status_code=403, detail="Could not validate credentials")

# Функция для получения текущего пользователя
def get_current_user(db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    # Используем функцию verify_token для извлечения данных из токена
    print(f"Received token: {token}")
    payload = verify_token(token)
    username: str = payload.get("sub")  # Используем username (если он есть в токене)
    if username is None:
        raise HTTPException(status_code=401, detail="Invalid token")

    print(f"Looking for user with username: {username}")
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


# Функция для получения информации о текущем пользователе
def get_current_user_info(db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    user = get_current_user(db=db, token=token)
    return {"username": user.username, "role": user.role}
