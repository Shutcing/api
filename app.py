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
tasks: dict[str, dict] = {}

async def getAnswer(prompt: str, model: str, image_url: str = None) -> str:
    logger.info("Асинхронная задача: prompt=%s", prompt)
    loop = asyncio.get_running_loop()

    # Инициализация WebDriver в отдельном потоке
    def init_driver():
        chrome_options = Options()
        chrome_options.binary_location = "/usr/bin/google-chrome-stable"
        # chrome_options.add_argument("--headless")
        # chrome_options.add_argument("--no-sandbox")
        # chrome_options.add_argument("--disable-dev-shm-usage")
        # chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        # chrome_options.add_argument("--enable-logging")
        # chrome_options.add_argument("--v=1")
        # chrome_options.add_argument("--disable-gpu")
        # chrome_options.add_argument(
        #     "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        #     "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
        # )
        service = Service(
            ChromeDriverManager().install(),
            log_path="-",               # вывод логов в stderr
            service_args=["--verbose"]  # подробное логирование
        )
        return webdriver.Chrome(service=service, options=chrome_options)

    driver = await loop.run_in_executor(ThreadPoolExecutor(), init_driver)
    await loop.run_in_executor(ThreadPoolExecutor(), driver.set_window_size, 800, 600)

    try:
        logger.info("Открытие страницы gptClient")
        await loop.run_in_executor(
            ThreadPoolExecutor(),
            driver.get,
            "https://shutcing.github.io/gptClient/"
        )

        # Пауза для полной загрузки страницы
        await asyncio.sleep(5)

        # Ожидание поля ввода
        await loop.run_in_executor(
            ThreadPoolExecutor(),
            lambda: WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.ID, "main-input"))
            )
        )

        logger.info("Нашли поле ввода")

        # Ввод prompt
        textarea = await loop.run_in_executor(
            ThreadPoolExecutor(),
            driver.find_element,
            By.ID,
            "main-input"
        )
        await loop.run_in_executor(ThreadPoolExecutor(), textarea.clear)
        await loop.run_in_executor(
            ThreadPoolExecutor(),
            lambda: driver.execute_script(
                """
                arguments[0].value = arguments[1];
                arguments[0].dispatchEvent(new Event('input', { bubbles: true }));
                arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
                """,
                textarea, prompt
            )
        )

        logger.info("Ввели")

        # Выбор модели
        select_elem = await loop.run_in_executor(
            ThreadPoolExecutor(),
            driver.find_element,
            By.ID,
            "model-selector"
        )
        select_wrapper = Select(select_elem)
        await loop.run_in_executor(
            ThreadPoolExecutor(),
            select_wrapper.select_by_value,
            model
        )

        logger.info("Выбрали модель")

        # Ввод URL изображения (если задан)
        if image_url:
            img_input = await loop.run_in_executor(
                ThreadPoolExecutor(),
                driver.find_element,
                By.ID,
                "image-url-input"
            )
            await loop.run_in_executor(ThreadPoolExecutor(), img_input.clear)
            await loop.run_in_executor(ThreadPoolExecutor(), img_input.send_keys, image_url)

        # Отправка формы
        button = await loop.run_in_executor(
            ThreadPoolExecutor(),
            driver.find_element,
            By.ID,
            "generate-btn"
        )
        await loop.run_in_executor(ThreadPoolExecutor(), button.click)

        logger.info("Отправили форму")

        # Работа с shadow DOM для авторизации
        host_element = await loop.run_in_executor(
            ThreadPoolExecutor(),
            driver.find_element,
            By.CSS_SELECTOR,
            "puter-dialog"
        )
        shadow_root = await loop.run_in_executor(
            ThreadPoolExecutor(),
            lambda: driver.execute_script("return arguments[0].shadowRoot", host_element)
        )
        auth_element = await loop.run_in_executor(
            ThreadPoolExecutor(),
            shadow_root.find_element,
            By.CSS_SELECTOR,
            "#launch-auth-popup"
        )
        await loop.run_in_executor(ThreadPoolExecutor(), auth_element.click)

        # Ожидание новой вкладки и переключение
        await loop.run_in_executor(
            ThreadPoolExecutor(),
            lambda: WebDriverWait(driver, 10).until(lambda d: len(d.window_handles) > 1)
        )
        await loop.run_in_executor(ThreadPoolExecutor(), driver.switch_to.window, driver.window_handles[-1])
        await loop.run_in_executor(ThreadPoolExecutor(), driver.set_window_position, -1600, -1600)
        await loop.run_in_executor(ThreadPoolExecutor(), driver.switch_to.window, driver.window_handles[0])

        logger.info("началась генерация")

        # Ожидание завершения генерации
        # await loop.run_in_executor(
        #     ThreadPoolExecutor(),
        #     lambda: WebDriverWait(driver, 360).until(
        #         EC.invisibility_of_element_located((By.CSS_SELECTOR, ".loader"))
        #     )
        # )

        # Ждём появления текста в .output
        await loop.run_in_executor(
            ThreadPoolExecutor(),
            lambda: WebDriverWait(driver, 360).until(
                lambda d: d.find_element(By.CSS_SELECTOR, ".output").text.strip() != ""
            )
        )

        logger.info("получили результат")
        
        await asyncio.sleep(10)

        # Получение результата
        answer_element = await loop.run_in_executor(
            ThreadPoolExecutor(),
            driver.find_element,
            By.CSS_SELECTOR,
            ".output"
        )
        result = answer_element.text
        logger.info("Ответ получен")
        return result

    finally:
        # Всегда закрываем браузер
        await loop.run_in_executor(ThreadPoolExecutor(), driver.quit)

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
    threading.Thread(
        target=lambda: asyncio.run(run_task(task_id, prompt)),
        daemon=True
    ).start()
    return jsonify({"task_id": task_id})

@app.route('/get_result/<task_id>', methods=['GET'])
def get_result(task_id: str):
    task = tasks.get(task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404
    if task["status"] == "completed":
        return Response(
            json.dumps({"result": task["result"]}, ensure_ascii=False),
            mimetype="application/json; charset=utf-8"
        )
    return jsonify({"status": "still processing"}), 202

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
