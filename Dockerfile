# Используем базовый образ Python
FROM python:3.10-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Устанавливаем системные зависимости, включая jq
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    jq \  # <--- Добавляем jq
    # Зависимости для Chrome
    libglib2.0-0 \
    libnss3 \
    libgconf-2-4 \
    libfontconfig1 \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libcups2 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    # Очистка кэша apt
    && rm -rf /var/lib/apt/lists/*

# Скачиваем и устанавливаем Google Chrome (стабильную версию)
# (Оставляем как было)
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Определяем версию установленного Chrome (Опционально, но может быть полезно для логов)
RUN google-chrome --version

# --- ИСПРАВЛЕННЫЙ БЛОК СКАЧИВАНИЯ CHROMEDRIVER ---
# Используем jq для извлечения URL последней стабильной версии ChromeDriver для linux64
# Используем другой JSON эндпоинт, который может быть стабильнее
RUN LATEST_CHROMEDRIVER_URL=$(wget -qO- https://googlechromelabs.github.io/chrome-for-testing/latest-stable-versions-with-downloads.json | jq -r '.channels.Stable.downloads.chromedriver[] | select(.platform=="linux64") | .url') \
    && echo "Attempting to download ChromeDriver from: $LATEST_CHROMEDRIVER_URL" \
    # Проверяем, что URL не пустой
    && if [ -z "$LATEST_CHROMEDRIVER_URL" ]; then echo "Error: Could not find ChromeDriver download URL."; exit 1; fi \
    # Скачиваем архив
    && wget -q "$LATEST_CHROMEDRIVER_URL" -O /tmp/chromedriver.zip \
    # Распаковываем архив (структура может быть разной, часто внутри есть папка)
    && unzip /tmp/chromedriver.zip -d /tmp/ \
    # Находим исполняемый файл chromedriver внутри распакованной папки и перемещаем его
    && mv /tmp/chromedriver-linux64/chromedriver /usr/local/bin/chromedriver \
    # Удаляем архив и распакованную папку
    && rm -rf /tmp/chromedriver.zip /tmp/chromedriver-linux64 \
    # Устанавливаем права на исполнение
    && chmod +x /usr/local/bin/chromedriver \
    # Проверяем версию chromedriver
    && chromedriver --version
# -----------------------------------------------------

# Устанавливаем Python зависимости
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код приложения в контейнер
COPY . .

# Указываем порт, который будет слушать Gunicorn (Render ожидает 10000 по умолчанию для Docker)
ENV PORT 10000
EXPOSE 10000

# Команда для запуска приложения через Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:10000", "--workers", "2", "--threads", "4", "--timeout", "120", "app:app"]
