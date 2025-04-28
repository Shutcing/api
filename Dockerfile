FROM python:3.11-slim

# 1) Системные утилиты и драйвер
RUN apt-get update && \
    apt-get install -y \
      wget ca-certificates xvfb unzip \
      chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# 2) Установка Google Chrome из .deb
RUN wget -qO /tmp/google-chrome.deb \
      https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb && \
    apt-get update && \
    apt-get install -y /tmp/google-chrome.deb && \
    rm /tmp/google-chrome.deb

WORKDIR /app

# 3) Python-зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4) Копируем код
COPY . .

ENV DISPLAY=:99 \
    PYTHONUNBUFFERED=1

RUN google-chrome --version && chromedriver --version

# 5) Запуск Xvfb + Gunicorn (shell-форма для подстановки $PORT)
CMD sh -c "Xvfb :99 -screen 0 1920x1080x24 & \
           gunicorn --bind 0.0.0.0:$PORT app:app"
