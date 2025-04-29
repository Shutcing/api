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

# 5. Копируем код вашего приложения в рабочую директорию
COPY new_app.py .

# 6. Указываем команду для запуска приложения с помощью Gunicorn
# Render автоматически установит переменную окружения PORT
# Gunicorn будет слушать на всех интерфейсах (0.0.0.0) на порту, указанном Render
# new_app:app указывает, что нужно запустить объект 'app' из файла 'new_app.py'
# --workers 1 : Начнем с одного worker-процесса, что обычно достаточно для небольших планов Render.
#               Вы можете увеличить это число при необходимости.
CMD ["gunicorn", "--bind", "0.0.0.0:$PORT", "--workers", "1", "new_app:app"]
