from concurrent.futures import ThreadPoolExecutor
import asyncio
import time
import sys
import os
import re
from flask import Flask, jsonify, request, Response
import uuid
import threading
import json
import logging

log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(threadName)s - %(message)s')
log_handler = logging.StreamHandler(sys.stderr) # Вывод в stderr
log_handler.setFormatter(log_formatter)

sys.setrecursionlimit(10**9)

app = Flask(__name__)
app.logger.handlers = [] # Удаляем стандартные обработчики Flask, если они есть
app.logger.addHandler(log_handler)
app.logger.setLevel(logging.INFO) # Устанавливаем уровень для логгера Flask


app.config['JSON_AS_ASCII'] = False

# Хранилище задач (вместо Redis для простоты)
tasks = {}

import cloudscraper


def signup_user(scraper):
    resp = scraper.post(
        "https://puter.com/signup",
        json={"is_temp": True},
        headers={
            "Host":         "api.puter.com",
            "Content-Type": "application/json",
            "Origin":       "https://puter.com",
            "Referer":      "https://puter.com/signup",
            "User-Agent":   "user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/1xx.0.0.0 Safari/537.36",
            "Accept":       "*/*",
        },
        timeout=15
    )
    resp.raise_for_status()
    token = resp.json()["token"]
    cookie_value = scraper.cookies.get("puter_auth_token")
    if not cookie_value:
        raise RuntimeError("Кука puter_auth_token не найдена")
    return token, cookie_value

def call_chat(scraper, token, cookie_value, prompt):
    headers = {
        "Host":          "api.puter.com",
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json",
        "Accept":        "*/*",
        "Origin":        "https://puter.com",
        "Referer":       "https://puter.com/",
        "User-Agent":    "user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/1xx.0.0.0 Safari/537.36",
    }
    body = {
        "interface":"puter-chat-completion",
        "driver":"openai-completion",
        "test_mode": False,
        "method":"complete",
        "args": {
            "messages":[{"role":"user","content":prompt}],
            "model":"o1",
            # "imageURL": "",
            "max_completion_tokens":10**9,
            "stream": False
        }
    }
    resp = scraper.post(
        "https://api.puter.com/drivers/call",
        headers=headers,
        cookies={"puter_auth_token": cookie_value},
        json=body,
        timeout=30
    )
    resp.raise_for_status()
    return resp.json()

async def getAnswer(prompt, model, image_url=None):
    loop = asyncio.get_running_loop()
    scraper = cloudscraper.create_scraper()

    async def _async_task():
        with ThreadPoolExecutor() as pool:
            app.logger.info("Получаем токен и куки")
            token, cookie = signup_user(scraper)
            app.logger.info(token)
            app.logger.info(cookie)
            return call_chat(scraper, token, cookie, prompt)["result"]["message"]["content"]
            

    app.logger.info("Получили ответ")    
    return await _async_task()

def async_task(task_id, prompt):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(getAnswer(prompt, "gpt-4o"))
        app.logger.info(result)
        tasks[task_id] = {"status": "completed", "result": result}
    except Exception as e:
        tasks[task_id] = {"status": "error", "error": str(e)}
    finally:
        loop.close()

@app.route('/send_prompt', methods=['POST'])
def start_task():
    prompt = request.args.get('prompt')
    task_id = str(uuid.uuid4())
    tasks[task_id] = {"status": "processing"}
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
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
