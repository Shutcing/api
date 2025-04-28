FROM python:3.11-slim

# Системные зависимости и headless Chrome
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

# Debug-вывод версий
RUN google-chrome --version && chromedriver --version

# Запуск с логированием Xvfb
CMD sh -c "set -x; \
           Xvfb :99 -screen 0 1920x1080x24 &>& /tmp/xvfb.log & \
           gunicorn --bind 0.0.0.0:$PORT app:app"

# Запуск через Gunicorn (WSGI)
CMD sh -c "gunicorn --bind 0.0.0.0:$PORT app:app"
