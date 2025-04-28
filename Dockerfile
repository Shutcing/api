FROM python:3.11-slim

# 1) Системные утилиты и библиотеки для Headless Chrome
RUN apt-get update && \
    apt-get install -y \
      wget ca-certificates xvfb unzip \
      gconf-service libasound2 libatk1.0-0 libatk-bridge2.0-0 libc6 libcairo2 libcups2 \
      libdbus-1-3 libexpat1 libfontconfig1 libgbm1 libgconf-2-4 libgdk-pixbuf2.0-0 \
      libglib2.0-0 libgtk-3-0 libnspr4 libpango-1.0-0 libpangocairo-1.0-0 libstdc++6 \
      libx11-6 libx11-xcb1 libxcb1 libxcomposite1 libxcursor1 libxdamage1 libxext6 \
      libxfixes3 libxi6 libxrandr2 libxrender1 libxss1 libxtst6 fonts-liberation \
      libappindicator1 lsb-release xdg-utils chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# 2) Установка Google Chrome из .deb
RUN wget -qO /tmp/google-chrome.deb \
      https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb && \
    apt-get update && \
    apt-get install -y /tmp/google-chrome.deb && \
    rm /tmp/google-chrome.deb && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 3) Установка Python-зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4) Копирование кода приложения
COPY . .

# 5) Отладочная проверка версий браузера и драйвера
RUN google-chrome --version && chromedriver --version

# Определяем переменные окружения
ENV DISPLAY=:99 \
    PYTHONUNBUFFERED=1

# 6) Запуск Xvfb и сервера через Gunicorn (shell-форма для подстановки $PORT)
CMD sh -c "set -x; \
           Xvfb :99 -screen 0 1920x1080x24 & \
           gunicorn --bind 0.0.0.0:$PORT app:app"
