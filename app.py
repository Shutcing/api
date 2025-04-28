from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import Select
from concurrent.futures import ThreadPoolExecutor
import asyncio
import time
import sys
import os
import re

sys.setrecursionlimit(10**9)

async def getAnswer(prompt, model, image_url=None):
    loop = asyncio.get_running_loop()

    async def _async_task():
        with ThreadPoolExecutor() as pool:
            chrome_options = Options()
 # Включаем headless-режим
            chrome_options.add_argument("--headless=new")
            # Добавляем опции для обхода детекции
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option("useAutomationExtension", False)
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            # # Устанавливаем user-agent
            chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36")
            # chrome_options.add_argument("--window-position=-32000,-32000")
            chrome_options.add_argument("--log-level=3")

            # Асинхронный запуск Chrome
            driver = await loop.run_in_executor(
                pool,
                lambda: webdriver.Chrome(options=chrome_options)
            )
            await loop.run_in_executor(pool, driver.set_window_size, 800, 600)

            try:
                # Открытие страницы
                await loop.run_in_executor(
                    pool,
                    driver.get,
                    "https://shutcing.github.io/gptClient/"
                )

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

                # Получение ответа
                answer_element = await loop.run_in_executor(
                    pool,
                    driver.find_element,
                    By.CSS_SELECTOR,
                    ".output"
                )
                return answer_element.text

            finally:
                # Закрыть браузер
                await loop.run_in_executor(pool, driver.quit)

    return await _async_task()

#----------------------------------------------------------------------------
# app.py
from flask import Flask, jsonify, request, Response
import uuid
import threading
from time import sleep
import asyncio
import json

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False

# Хранилище задач (вместо Redis для простоты)
tasks = {}

def async_task(task_id, prompt):
    # Создаем новую event loop для потока
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        # Запускаем асинхронную функцию
        result = loop.run_until_complete(getAnswer(prompt, "gpt-4o"))  # Если getAnswer async
        tasks[task_id] = {"status": "completed", "result": result}
    except Exception as e:
        tasks[task_id] = {"status": "error", "error": str(e)}
    finally:
        loop.close()

@app.route('/send_prompt', methods=['POST'])
def start_task():
    prompt = request.args.get('prompt')
    task_id = str(uuid.uuid4())  # Генерируем уникальный ID задачи
    tasks[task_id] = {"status": "processing"}
    
    # Запускаем задачу в отдельном потоке
    thread = threading.Thread(target=async_task, args=(task_id, prompt))
    thread.start()
    
    return jsonify({"task_id": task_id})

@app.route('/get_result/<task_id>', methods=['GET'])
def get_result(task_id):
    task = tasks.get(task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404
    
    if task["status"] == "completed":
        data = json.dumps({"result": task["result"]}, ensure_ascii=False)
        return Response(data, mimetype="application/json; charset=utf-8")
    else:
        return jsonify({"status": "still processing"}), 202

if __name__ == '__main__':
    app.run(debug=True)