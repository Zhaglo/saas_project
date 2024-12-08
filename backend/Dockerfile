FROM python:3.11-slim

# Устанавливаем зависимости
WORKDIR /app
COPY requirements.txt /app/
RUN pip install -r requirements.txt

# Копируем весь проект
COPY . /app/

# Указываем команду для запуска FastAPI
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
