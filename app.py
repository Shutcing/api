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
            # Небольшая пауза для полной загрузки
                await asyncio.sleep(5)

                # Ожидание поля ввода prompt
                await loop.run_in_executor(
                    pool,
                    lambda: WebDriverWait(driver, 30).until(
                        EC.presence_of_element_located((By.ID, "main-input"))
                    )
                )

                # Ввод prompt
                textarea = await loop.run_in_executor(
                    pool,
                    driver.find_element,
                    By.ID,
                    "main-input"
                )
                await loop.run_in_executor(
                    pool,
                    textarea.clear
                )
                await loop.run_in_executor(
                    pool,
                    lambda: driver.execute_script(
                        """
                        arguments[0].value = arguments[1];
                        arguments[0].dispatchEvent(new Event('input', { bubbles: true }));
                        arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
                        """,
                        textarea, prompt
                    )
                )

                #выбор модели
                select_elem = await loop.run_in_executor(
                    pool,
                    driver.find_element,
                    By.ID,
                    "model-selector"
                )
                # оборачиваем WebElement в Select
                select_wrapper = Select(select_elem)  # :contentReference[oaicite:0]{index=0}

                # выбираем по значению option.value="gpt-4o"
                await loop.run_in_executor(
                    pool,
                    select_wrapper.select_by_value,
                    model  # или любой другой нужный вам value
                ) 


                # Ввод URL изображения, если указан
                if image_url:
                    img_input = await loop.run_in_executor(
                        pool,
                        driver.find_element,
                        By.ID,
                        "image-url-input"
                    )
                    await loop.run_in_executor(
                        pool,
                        img_input.clear
                    )
                    await loop.run_in_executor(
                        pool,
                        img_input.send_keys,
                        image_url
                    )

                # Нажатие кнопки Generate
                button = await loop.run_in_executor(
                    pool,
                    driver.find_element,
                    By.ID,
                    "generate-btn"
                )
                await loop.run_in_executor(pool, button.click)

                # Работа с shadow DOM (остается без изменений)
                host_element = await loop.run_in_executor(
                    pool,
                    driver.find_element,
                    By.CSS_SELECTOR,
                    "puter-dialog"
                )
                shadow_root = await loop.run_in_executor(
                    pool,
                    lambda: driver.execute_script(
                        "return arguments[0].shadowRoot",
                        host_element
                    )
                )
                auth_element = await loop.run_in_executor(
                    pool,
                    shadow_root.find_element,
                    By.CSS_SELECTOR,
                    "#launch-auth-popup"
                )
                await loop.run_in_executor(pool, auth_element.click)

                # Ожидание новой вкладки для авторизации
                await loop.run_in_executor(
                    pool,
                    lambda: WebDriverWait(driver, 10).until(
                        lambda d: len(d.window_handles) > 1
                    )
                )

                # Переключение вкладок и скрытие авторизационной
                await loop.run_in_executor(
                    pool,
                    driver.switch_to.window,
                    driver.window_handles[-1]
                )
                await loop.run_in_executor(
                    pool,
                    driver.set_window_position,
                    -1600,
                    -1600
                )
                await loop.run_in_executor(
                    pool,
                    driver.switch_to.window,
                    driver.window_handles[0]
                )

                # Ожидание завершения генерации (инвизибилити кнопки)
                await loop.run_in_executor(
                    pool,
                    lambda: WebDriverWait(driver, 60).until(
                        EC.invisibility_of_element_located((By.CSS_SELECTOR, ".loader"))
                    )
                )

                # Дополнительная небольшая задержка для доста‌точного ожидания текста
                await asyncio.sleep(6)
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
