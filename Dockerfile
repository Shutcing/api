# Используем базовый образ Python
FROM python:3.10-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Устанавливаем системные зависимости (в одну строку для надежности)
RUN apt-get update && apt-get install -y wget gnupg unzip jq libglib2.0-0 libnss3 libgconf-2-4 libfontconfig1 libx11-6 libx11-xcb1 libxcb1 libxcomposite1 libxdamage1 libxext6 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libcups2 libatk1.0-0 libatk-bridge2.0-0 libgtk-3-0 && rm -rf /var/lib/apt/lists/*

# Скачиваем и устанавливаем Google Chrome (стабильную версию)
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Определяем ТОЧНУЮ версию установленного Chrome
RUN CHROME_VERSION=$(google-chrome --version | awk '{print $3}') \
    && echo "Detected Chrome version: $CHROME_VERSION"

# --- НАЧАЛО ОБНОВЛЕННОГО БЛОКА CHROMEDRIVER ---
# Скачиваем и устанавливаем ChromeDriver, соответствующий установленной версии Chrome
RUN CHROME_VERSION=$(google-chrome --version | awk '{print $3}') \
    # Скачиваем JSON со всеми известными версиями
    && JSON_DATA=$(wget -qO- https://googlechromelabs.github.io/chrome-for-testing/known-good-versions-with-downloads.json) \
    # Проверяем, что JSON скачался
    && if [ -z "$JSON_DATA" ]; then echo "Error: Could not download known-good-versions JSON."; exit 1; fi \
    # Ищем URL для ТОЧНОЙ версии Chrome
    && CHROMEDRIVER_URL=$(echo "$JSON_DATA" | jq -r --arg VERSION "$CHROME_VERSION" '.versions[] | select(.version==$VERSION) | .downloads.chromedriver[] | select(.platform=="linux64") | .url' | head -n 1) \
    # Если точной версии нет (иногда бывает при минорных обновлениях Chrome), ищем последнюю доступную версию для major.minor.build
    && if [ -z "$CHROMEDRIVER_URL" ]; then \
        CHROME_MAJOR_BUILD=$(echo "$CHROME_VERSION" | cut -d. -f1-3); \
        echo "Exact ChromeDriver match not found for $CHROME_VERSION. Finding latest for $CHROME_MAJOR_BUILD.* ..."; \
        CHROMEDRIVER_URL=$(echo "$JSON_DATA" | jq -r --arg PREFIX "$CHROME_MAJOR_BUILD." '.versions[] | select(.version | startswith($PREFIX)) | .downloads.chromedriver[] | select(.platform=="linux64") | .url' | sort -V | tail -n 1); \
    fi \
    # Финальная проверка, что URL найден
    && echo "Attempting to download ChromeDriver from: $CHROMEDRIVER_URL" \
    && if [ -z "$CHROMEDRIVER_URL" ]; then echo "Error: Could not find ChromeDriver download URL for Chrome $CHROME_VERSION or compatible."; exit 1; fi \
    # Скачиваем, распаковываем и устанавливаем
    && wget -q "$CHROMEDRIVER_URL" -O /tmp/chromedriver.zip \
    && unzip /tmp/chromedriver.zip -d /tmp/ \
    && mv /tmp/chromedriver-linux64/chromedriver /usr/local/bin/chromedriver \
    && rm -rf /tmp/chromedriver.zip /tmp/chromedriver-linux64 \
    && chmod +x /usr/local/bin/chromedriver \
    && chromedriver --version
# --- КОНЕЦ ОБНОВЛЕННОГО БЛОКА CHROMEDRIVER ---

# Устанавливаем Python зависимости
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код приложения в контейнер
COPY . .

# Указываем порт
ENV PORT 10000
EXPOSE 10000

# Команда для запуска
CMD ["gunicorn", "--bind", "0.0.0.0:10000", "--workers", "2", "--threads", "4", "--timeout", "120", "app:app"]
