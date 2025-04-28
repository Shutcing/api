FROM python:3.11-slim

# 1) Системные зависимости и SSL-сертификаты
RUN apt-get update && \
    apt-get install -y wget unzip ca-certificates xvfb \
        libxi6 libgconf-2-4 libnss3 libxss1 libglib2.0-0

# 2) Chrome и его драйвер
RUN wget -qO /tmp/chrome.deb \
        https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb && \
    apt-get install -y /tmp/chrome.deb && \
    rm /tmp/chrome.deb

RUN wget -qO /tmp/chromedriver.zip \
        https://chromedriver.storage.googleapis.com/116.0.5845.96/chromedriver_linux64.zip && \
    unzip /tmp/chromedriver.zip -d /usr/local/bin && \
    rm /tmp/chromedriver.zip && \
    chmod +x /usr/local/bin/chromedriver

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

ENV PYTHONUNBUFFERED=1 \
    DISPLAY=:99

CMD ["sh", "-c", "Xvfb :99 -screen 0 1920x1080x24 & uvicorn app:app --host 0.0.0.0 --port $PORT"]
