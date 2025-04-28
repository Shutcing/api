FROM python:3.11-slim

# 1) Устанавливаем Chrome и необходимые пакеты
RUN apt-get update && \
    apt-get install -y \
      wget ca-certificates xvfb \
      chromium-driver \
      google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# 2) Рабочая директория
WORKDIR /app

# 3) Python-зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4) Копируем код
COPY . .

# 5) Переменные окружения
ENV DISPLAY=:99 \
    PYTHONUNBUFFERED=1

# 6) Запуск сервера (Gunicorn в shell-форме для подстановки $PORT)
CMD sh -c "Xvfb :99 -screen 0 1920x1080x24 & \
           gunicorn --bind 0.0.0.0:$PORT app:app"
