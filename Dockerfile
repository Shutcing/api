FROM python:3.11-slim

# Системные пакеты и headless Chrome
RUN apt-get update && \
    apt-get install -y wget ca-certificates xvfb \
        libxi6 libnss3 libxss1 libglib2.0-0 && \
    wget -qO /tmp/chrome.deb \
        https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb && \
    apt-get install -y /tmp/chrome.deb && \
    rm /tmp/chrome.deb

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

ENV DISPLAY=:99 \
    PYTHONUNBUFFERED=1

CMD ["sh", "-c", "Xvfb :99 -screen 0 1920x1080x24 & uvicorn app:app --host 0.0.0.0 --port $PORT"]
