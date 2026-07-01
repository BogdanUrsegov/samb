FROM python:3.10-slim

WORKDIR /app

# 1. Сначала копируем только зависимости (слой кэшируется)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 2. Копируем весь код
COPY . .

# 3. Создаем папку для базы данных
RUN mkdir -p /app/data

# Запуск (так как main.py в корне)
CMD ["python", "main.py"]