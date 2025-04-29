# Dockerfile

# 1. Используем официальный базовый образ Python
FROM python:3.10-slim

# 2. Устанавливаем рабочую директорию в контейнере
WORKDIR /app

# 3. Копируем файл зависимостей в рабочую директорию
COPY requirements.txt requirements.txt

# 4. Устанавливаем зависимости
# --no-cache-dir используется для уменьшения размера образа
# --upgrade pip обновляет pip перед установкой пакетов
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 5. Копируем код вашего приложения (уже app.py) в рабочую директорию
COPY app.py .

# 6. Указываем команду для запуска приложения с помощью Gunicorn
# Используем shell-форму CMD, чтобы переменная $PORT была подставлена оболочкой.
# Render автоматически установит переменную окружения PORT.
# Запускаем объект 'app' из файла 'app.py'
CMD gunicorn --bind 0.0.0.0:$PORT --workers 1 app:app
