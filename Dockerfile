# Используем базовый образ Python
FROM python:3.10-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Устанавливаем системные зависимости для Chrome и ChromeDriver
# Взято из рекомендаций и официальных источников
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
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
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Определяем версию установленного Chrome
RUN CHROME_VERSION=$(google-chrome --version | cut -f 3 -d ' ' | cut -d '.' -f 1) \
    && echo "Detected Chrome version: $CHROME_VERSION"

# Скачиваем и устанавливаем ChromeDriver соответствующей версии
# Используем новый JSON эндпоинт для определения нужной версии ChromeDriver
RUN LATEST_CHROMEDRIVER_VERSION=$(wget -qO- https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json | grep -oP '"linux64":\[{"platform":"linux64","url":"\K[^"]*') \
    && echo "Attempting to download ChromeDriver from: $LATEST_CHROMEDRIVER_VERSION" \
    && wget -q $LATEST_CHROMEDRIVER_VERSION -O /tmp/chromedriver.zip \
    && unzip /tmp/chromedriver.zip -d /usr/local/bin/ \
    # Убедимся, что извлеченный файл называется chromedriver и находится по ожидаемому пути
    && mv /usr/local/bin/chromedriver-linux64/chromedriver /usr/local/bin/chromedriver \
    && rm -rf /tmp/chromedriver.zip /usr/local/bin/chromedriver-linux64 \
    && chmod +x /usr/local/bin/chromedriver

# Устанавливаем Python зависимости
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код приложения в контейнер
COPY . .

# Указываем порт, который будет слушать Gunicorn (Render ожидает 10000 по умолчанию для Docker)
ENV PORT 10000
EXPOSE 10000

# Команда для запуска приложения через Gunicorn
# Увеличьте timeout (-t), если ваши Selenium задачи выполняются долго
# Количество workers (-w) подбирайте в зависимости от тарифа Render (CPU/RAM)
# Используйте gevent или eventlet для асинхронной работы, если используете async/await глубоко,
# но для вашего случая с ThreadPoolExecutor стандартные sync воркеры Gunicorn тоже подойдут.
CMD ["gunicorn", "--bind", "0.0.0.0:10000", "--workers", "2", "--threads", "4", "--timeout", "120", "app:app"]
