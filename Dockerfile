FROM python:3.11-slim

RUN apt-get update && \
    apt-get install -y wget unzip xvfb libxi6 libgconf-2-4 libnss3 libxss1 libglib2.0-0 && \
    wget -qO /tmp/chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb && \
    apt-get install -y /tmp/chrome.deb && \
    rm /tmp/chrome.deb && \
    wget -qO /usr/local/bin/chromedriver.zip https://chromedriver.storage.googleapis.com/116.0.5845.96/chromedriver_linux64.zip && \
    unzip /usr/local/bin/chromedriver.zip -d /usr/local/bin && \
    chmod +x /usr/local/bin/chromedriver

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

ENV PYTHONUNBUFFERED=1 \
    DISPLAY=:99

CMD ["sh", "-c", "Xvfb :99 -screen 0 1920x1080x24 & uvicorn app:app --host 0.0.0.0 --port $PORT"]