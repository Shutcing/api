import os
import uuid
import json
import asyncio
import logging
import threading
from flask import Flask, jsonify, request, Response
from concurrent.futures import ThreadPoolExecutor
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Flask-приложение
app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False

# Пул задач
tasks = {}

async def getAnswer(prompt: str, model: str, image_url: str = None) -> str:
    logger.info("Асинхронная задача: prompt=%s", prompt)
    loop = asyncio.get_running_loop()
    with ThreadPoolExecutor() as pool:
        # Опции Chrome
        chrome_options = Options()
        chrome_options.binary_location = "/usr/bin/google-chrome-stable"
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--enable-logging")
        chrome_options.add_argument("--v=1")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
        )

        # Service для ChromeDriver с verbose-логированием
        service = Service(
            ChromeDriverManager().install(),
            log_path="-",               # stderr
            service_args=["--verbose"]
        )

        # Инициализация WebDriver
        try:
            driver = await loop.run_in_executor(
                pool,
                lambda: webdriver.Chrome(service=service, options=chrome_options)
            )
        except Exception as e:
            logger.exception("Не удалось запустить ChromeDriver")
            raise
        await loop.run_in_executor(pool, driver.set_window_size, 800, 600)

        try:
            logger.info("Открытие страницы gptClient")
            await loop.run_in_executor(pool, driver.get, "https://shutcing.github.io/gptClient/")
            # далее ваша логика...
            # здесь вставьте WebDriverWait, ввод prompt, нажатие и т.д.
            # по завершении:
            element = await loop.run_in_executor(pool, driver.find_element, By.CSS_SELECTOR, ".output")
            result = element.text
            logger.info("Ответ получен")
            return result
        finally:
            await loop.run_in_executor(pool, driver.quit)

async def run_task(task_id: str, prompt: str):
    try:
        res = await getAnswer(prompt, "gpt-4o")
        tasks[task_id] = {"status": "completed", "result": res}
    except Exception as ex:
        tasks[task_id] = {"status": "error", "error": str(ex)}
        logger.exception("Ошибка в задаче %s", task_id)

@app.route('/send_prompt', methods=['POST'])
def start_task():
    prompt = request.args.get('prompt', '')
    task_id = str(uuid.uuid4())
    tasks[task_id] = {"status": "processing"}
    logger.info("Создана задача %s", task_id)
    threading.Thread(target=lambda: asyncio.run(run_task(task_id, prompt)), daemon=True).start()
    return jsonify({"task_id": task_id})

@app.route('/get_result/<task_id>', methods=['GET'])
def get_result(task_id):
    task = tasks.get(task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404
    if task.get("status") == "completed":
        return Response(json.dumps({"result": task["result"]}, ensure_ascii=False), mimetype="application/json; charset=utf-8")
    return jsonify({"status": "still processing"}), 202

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
