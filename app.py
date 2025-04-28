import asyncio
import json
import logging
import os
import re
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from flask import Flask, jsonify, request, Response
from selenium import webdriver
from selenium.common import TimeoutException, NoSuchElementException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

# --- Logging Configuration ---
# Configure logging to output to stdout/stderr (which Render captures)
# Include timestamp, log level, and message.
# Add task_id to relevant log messages for better tracking.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(threadName)s] - %(message)s',
    stream=sys.stdout  # Explicitly direct logs to stdout
)
# --- End Logging Configuration ---

# Increase recursion depth (Keep if needed, but often indicates deeper issues)
# sys.setrecursionlimit(10**9) # Consider removing if not strictly necessary

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False

# --- Task Storage ---
# WARNING: In-memory storage is volatile and will be lost on server restarts/crashes.
# Consider using Render Redis or another persistent store for production.
tasks = {}
tasks_lock = threading.Lock() # Use a lock for thread-safe access to the tasks dictionary
logging.info("Task storage initialized (in-memory).")
# --- End Task Storage ---

async def getAnswer(task_id, prompt, model, image_url=None):
    """
    Uses Selenium to interact with the web client and get a response.
    Includes detailed logging for debugging.
    """
    current_loop = asyncio.get_running_loop()
    log_prefix = f"[Task {task_id}]"
    logging.info(f"{log_prefix} getAnswer started for prompt: '{prompt[:50]}...'")

    driver = None # Initialize driver to None for the finally block

    async def _async_task():
        nonlocal driver # Allow modification of the outer scope driver variable
        start_time = time.time()
        with ThreadPoolExecutor() as pool:
            try:
                # --- Chrome Options ---
                logging.debug(f"{log_prefix} Setting Chrome options.")
                chrome_options = Options()
                chrome_options.add_argument("--headless=new")
                chrome_options.add_argument("--no-sandbox")
                chrome_options.add_argument("--disable-dev-shm-usage")
                chrome_options.add_argument("--disable-gpu")
                chrome_options.add_argument("--window-size=1920,1080")
                chrome_options.add_argument("--disable-blink-features=AutomationControlled")
                chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
                chrome_options.add_experimental_option("useAutomationExtension", False)
                chrome_options.add_argument("--log-level=3") # Minimize browser logs

                # --- Initialize WebDriver ---
                logging.info(f"{log_prefix} Initializing WebDriver...")
                init_start = time.time()
                driver = await current_loop.run_in_executor(
                    pool,
                    lambda: webdriver.Chrome(options=chrome_options)
                )
                logging.info(f"{log_prefix} WebDriver initialized ({time.time() - init_start:.2f}s). Session ID: {driver.session_id}")
                # await current_loop.run_in_executor(pool, driver.set_window_size, 800, 600) # Already set via options

                # --- Navigate and Interact ---
                target_url = "https://shutcing.github.io/gptClient/"
                logging.info(f"{log_prefix} Navigating to {target_url}")
                nav_start = time.time()
                await current_loop.run_in_executor(pool, driver.get, target_url)
                logging.info(f"{log_prefix} Navigation complete ({time.time() - nav_start:.2f}s).")

                # Wait for main input explicitly
                wait_timeout = 30
                logging.info(f"{log_prefix} Waiting up to {wait_timeout}s for main input field...")
                wait_start = time.time()
                try:
                    textarea = await current_loop.run_in_executor(
                        pool,
                        lambda: WebDriverWait(driver, wait_timeout).until(
                            EC.presence_of_element_located((By.ID, "main-input"))
                        )
                    )
                    logging.info(f"{log_prefix} Main input found ({time.time() - wait_start:.2f}s).")
                except TimeoutException:
                    logging.error(f"{log_prefix} Timeout waiting for main input field after {wait_timeout}s.")
                    # Capture page source or screenshot for debugging
                    page_source = await current_loop.run_in_executor(pool, lambda: driver.page_source)
                    logging.debug(f"{log_prefix} Page source on timeout:\n{page_source[:1000]}...") # Log beginning of source
                    raise # Re-raise the exception

                # Input prompt
                logging.info(f"{log_prefix} Clearing and sending prompt to input field.")
                await current_loop.run_in_executor(pool, textarea.clear)
                await current_loop.run_in_executor(
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

                # Select model
                logging.info(f"{log_prefix} Selecting model: {model}")
                select_elem = await current_loop.run_in_executor(pool, driver.find_element, By.ID, "model-selector")
                select_wrapper = Select(select_elem)
                await current_loop.run_in_executor(pool, select_wrapper.select_by_value, model)

                # Handle image URL if provided
                if image_url:
                    logging.info(f"{log_prefix} Handling image URL: {image_url}")
                    img_input = await current_loop.run_in_executor(pool, driver.find_element, By.ID, "image-url-input")
                    await current_loop.run_in_executor(pool, img_input.clear)
                    await current_loop.run_in_executor(pool, img_input.send_keys, image_url)

                # Click generate button
                logging.info(f"{log_prefix} Clicking generate button.")
                button = await current_loop.run_in_executor(pool, driver.find_element, By.ID, "generate-btn")
                await current_loop.run_in_executor(pool, button.click)

                # --- Handle Authentication Popup ---
                auth_wait_timeout = 15
                logging.info(f"{log_prefix} Checking for authentication popup (wait up to {auth_wait_timeout}s)...")
                try:
                    # Find the dialog first
                    host_element = await current_loop.run_in_executor(
                        pool,
                        lambda: WebDriverWait(driver, auth_wait_timeout).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, "puter-dialog"))
                        )
                    )
                    logging.info(f"{log_prefix} Found puter-dialog. Accessing shadow root...")

                    # Access shadow root (retry mechanism might be useful here if it fails intermittently)
                    shadow_root = await current_loop.run_in_executor(
                        pool,
                        lambda: driver.execute_script("return arguments[0].shadowRoot", host_element)
                    )
                    if not shadow_root:
                         logging.warning(f"{log_prefix} Could not access shadow root for puter-dialog.")
                         # Handle cases where the popup might not appear or shadow root isn't accessible
                         # Decide if this is an error or if the flow can continue
                         # For now, we'll try to proceed assuming it might not always be needed.

                    else:
                        logging.info(f"{log_prefix} Searching for auth button within shadow root...")
                        # Find the button within the shadow root
                        auth_element = await current_loop.run_in_executor(
                            pool,
                            shadow_root.find_element,
                            By.CSS_SELECTOR,
                            "#launch-auth-popup"
                        )
                        logging.info(f"{log_prefix} Found auth button. Clicking it.")
                        await current_loop.run_in_executor(pool, auth_element.click)

                        # Wait for the new window/tab to open
                        logging.info(f"{log_prefix} Waiting for new window/tab to open (max 10s)...")
                        window_wait_start = time.time()
                        await current_loop.run_in_executor(
                            pool,
                            lambda: WebDriverWait(driver, 10).until(lambda d: len(d.window_handles) > 1)
                        )
                        logging.info(f"{log_prefix} New window detected ({time.time() - window_wait_start:.2f}s). Handles: {driver.window_handles}")

                        # Switch to the popup, move it off-screen, switch back
                        original_window = driver.current_window_handle
                        popup_window = driver.window_handles[-1]
                        logging.info(f"{log_prefix} Switching to popup window ({popup_window}).")
                        await current_loop.run_in_executor(pool, driver.switch_to.window, popup_window)
                        # Moving might not be necessary/possible in headless Docker, but doesn't hurt
                        # logging.info(f"{log_prefix} Moving popup window.")
                        # await current_loop.run_in_executor(pool, driver.set_window_position, -2000, -2000)
                        logging.info(f"{log_prefix} Switching back to original window ({original_window}).")
                        await current_loop.run_in_executor(pool, driver.switch_to.window, original_window)

                except TimeoutException:
                    logging.warning(f"{log_prefix} Authentication popup (puter-dialog) did not appear within {auth_wait_timeout}s. Proceeding...")
                except NoSuchElementException:
                    logging.warning(f"{log_prefix} Could not find elements related to auth popup. Proceeding...")
                except Exception as auth_err: # Catch other potential errors during auth handling
                    logging.error(f"{log_prefix} Error during authentication popup handling: {auth_err}", exc_info=True)
                    # Decide if this error should stop the process
                    # raise # Or maybe just log and continue

                # --- Wait for Result ---
                loader_wait_timeout = 120 # Increased timeout for potentially long generations
                logging.info(f"{log_prefix} Waiting for loader to disappear (max {loader_wait_timeout}s)...")
                loader_wait_start = time.time()
                try:
                    await current_loop.run_in_executor(
                        pool,
                        lambda: WebDriverWait(driver, loader_wait_timeout).until(
                            EC.invisibility_of_element_located((By.CSS_SELECTOR, ".loader"))
                        )
                    )
                    logging.info(f"{log_prefix} Loader disappeared ({time.time() - loader_wait_start:.2f}s).")
                except TimeoutException:
                    logging.error(f"{log_prefix} Timeout waiting for loader to disappear after {loader_wait_timeout}s.")
                    # Capture state for debugging
                    page_source = await current_loop.run_in_executor(pool, lambda: driver.page_source)
                    logging.debug(f"{log_prefix} Page source on loader timeout:\n{page_source[:1000]}...")
                    raise # Re-raise

                # Optional small delay after loader disappears, before grabbing output
                post_load_delay = 5 # Reduced from 6
                logging.debug(f"{log_prefix} Waiting {post_load_delay}s after loader disappearance...")
                await asyncio.sleep(post_load_delay)

                # Get result
                logging.info(f"{log_prefix} Finding output element.")
                output_find_start = time.time()
                answer_element = await current_loop.run_in_executor(pool, driver.find_element, By.CSS_SELECTOR, ".output")
                result_text = answer_element.text
                logging.info(f"{log_prefix} Output element found and text extracted ({time.time() - output_find_start:.2f}s). Result length: {len(result_text)}")
                logging.debug(f"{log_prefix} Raw result text: '{result_text[:100]}...'") # Log beginning of result

                total_time = time.time() - start_time
                logging.info(f"{log_prefix} getAnswer successfully completed in {total_time:.2f}s.")
                return result_text

            except Exception as e:
                # Log any exception that occurred during the process
                total_time = time.time() - start_time
                logging.error(f"{log_prefix} Exception in _async_task after {total_time:.2f}s: {e}", exc_info=True)
                # Try to capture page source on generic error as well
                if driver:
                    try:
                        page_source = await current_loop.run_in_executor(pool, lambda: driver.page_source)
                        logging.debug(f"{log_prefix} Page source on error:\n{page_source[:1000]}...")
                    except Exception as ps_err:
                        logging.error(f"{log_prefix} Failed to get page source on error: {ps_err}")
                raise # Re-raise the original exception to be caught by async_task

            finally:
                # --- Quit WebDriver ---
                if driver:
                    quit_start_time = time.time()
                    logging.info(f"{log_prefix} Quitting WebDriver (Session ID: {driver.session_id})...")
                    try:
                        await current_loop.run_in_executor(pool, driver.quit)
                        logging.info(f"{log_prefix} WebDriver quit successfully ({time.time() - quit_start_time:.2f}s).")
                    except Exception as quit_err:
                        logging.error(f"{log_prefix} Exception during WebDriver quit: {quit_err}", exc_info=True)
                else:
                     logging.warning(f"{log_prefix} WebDriver was not initialized, nothing to quit.")

    return await _async_task()

def async_task(task_id, prompt):
    """
    Runs the async getAnswer function in a separate thread with its own event loop.
    Handles task status updates and logging.
    """
    log_prefix = f"[Task {task_id}]"
    thread_name = threading.current_thread().name
    logging.info(f"{log_prefix} Starting background task in thread '{thread_name}'...")

    # Create and set a new event loop for this thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    logging.debug(f"{log_prefix} New asyncio event loop created and set for thread '{thread_name}'.")

    task_result_status = "unknown"
    result_data = None
    error_data = None

    try:
        # Run the main async function
        run_start_time = time.time()
        logging.info(f"{log_prefix} Executing getAnswer coroutine...")
        result_data = loop.run_until_complete(getAnswer(task_id, prompt, "gpt-4o")) # Pass task_id for logging
        run_time = time.time() - run_start_time
        logging.info(f"{log_prefix} getAnswer coroutine completed successfully in {run_time:.2f}s.")
        task_result_status = "completed"

    except Exception as e:
        run_time = time.time() - run_start_time if 'run_start_time' in locals() else 0
        logging.error(f"{log_prefix} Exception caught in async_task after ~{run_time:.2f}s: {e}", exc_info=True)
        task_result_status = "error"
        error_data = str(e)

    finally:
        # --- Update Task Status (Thread-Safe) ---
        try:
            with tasks_lock:
                if task_result_status == "completed":
                    tasks[task_id] = {"status": "completed", "result": result_data}
                    logging.info(f"{log_prefix} Task status updated to 'completed' in shared dictionary.")
                elif task_result_status == "error":
                    tasks[task_id] = {"status": "error", "error": error_data}
                    logging.info(f"{log_prefix} Task status updated to 'error' in shared dictionary.")
                else:
                    # Should not happen, but good to log
                    logging.warning(f"{log_prefix} Task finished with unknown status. Not updating dictionary.")
        except Exception as dict_err:
             logging.error(f"{log_prefix} Failed to update task dictionary: {dict_err}", exc_info=True)


        # --- Close Event Loop ---
        try:
            loop_close_start = time.time()
            logging.debug(f"{log_prefix} Closing asyncio event loop for thread '{thread_name}'...")
            loop.close()
            logging.debug(f"{log_prefix} Asyncio event loop closed ({time.time() - loop_close_start:.2f}s).")
        except Exception as loop_err:
            logging.error(f"{log_prefix} Exception during event loop close: {loop_err}", exc_info=True)

        logging.info(f"{log_prefix} Background task finished in thread '{thread_name}'.")


@app.route('/send_prompt', methods=['POST'])
def start_task():
    """
    API endpoint to start a new background task.
    """
    request_id = str(uuid.uuid4())[:8] # Short ID for this specific request/log correlation
    log_prefix = f"[Request {request_id}]"
    logging.info(f"{log_prefix} Received POST /send_prompt request.")

    prompt = request.args.get('prompt')
    if not prompt:
        logging.warning(f"{log_prefix} Bad Request: 'prompt' query parameter is missing.")
        return jsonify({"error": "Missing 'prompt' query parameter"}), 400

    logging.info(f"{log_prefix} Prompt received: '{prompt[:50]}...'")

    task_id = str(uuid.uuid4())
    log_prefix_task = f"[Request {request_id} / Task {task_id}]" # Include task ID in subsequent logs

    logging.info(f"{log_prefix_task} Generated task ID.")

    # --- Update Task Status (Thread-Safe) ---
    try:
        with tasks_lock:
            tasks[task_id] = {"status": "processing"}
            logging.info(f"{log_prefix_task} Task status set to 'processing' in shared dictionary.")
    except Exception as dict_err:
         logging.error(f"{log_prefix_task} Failed to initialize task in dictionary: {dict_err}", exc_info=True)
         return jsonify({"error": "Failed to initialize task processing"}), 500

    # --- Start Background Thread ---
    try:
        thread = threading.Thread(target=async_task, args=(task_id, prompt), name=f"TaskThread-{task_id[:8]}")
        thread.start()
        logging.info(f"{log_prefix_task} Background thread '{thread.name}' started.")
    except Exception as thread_err:
        logging.error(f"{log_prefix_task} Failed to start background thread: {thread_err}", exc_info=True)
        # Clean up task status if thread fails to start
        with tasks_lock:
            tasks[task_id] = {"status": "error", "error": "Failed to start background worker"}
        return jsonify({"error": "Failed to start background processing"}), 500

    logging.info(f"{log_prefix_task} Responding to client with task ID.")
    return jsonify({"task_id": task_id})


@app.route('/get_result/<task_id>', methods=['GET'])
def get_result(task_id):
    """
    API endpoint to retrieve the result of a background task.
    """
    request_id = str(uuid.uuid4())[:8]
    log_prefix = f"[Request {request_id} / Task {task_id}]"
    logging.info(f"{log_prefix} Received GET /get_result request.")

    # --- Get Task Status (Thread-Safe) ---
    task = None
    try:
        with tasks_lock:
            task = tasks.get(task_id) # Use .get() for safer access
            if task:
                logging.info(f"{log_prefix} Task found in dictionary. Status: {task.get('status')}")
            else:
                 logging.warning(f"{log_prefix} Task ID not found in dictionary.")

    except Exception as dict_err:
         logging.error(f"{log_prefix} Failed to access task dictionary: {dict_err}", exc_info=True)
         return jsonify({"error": "Failed to retrieve task status"}), 500

    if not task:
        return jsonify({"error": "Task not found"}), 404

    task_status = task.get("status")

    if task_status == "completed":
        logging.info(f"{log_prefix} Task completed. Returning result.")
        # Ensure result is JSON serializable (it should be text)
        result_payload = {"result": task.get("result", "N/A")}
        try:
            data = json.dumps(result_payload, ensure_ascii=False)
            return Response(data, mimetype="application/json; charset=utf-8")
        except TypeError as json_err:
             logging.error(f"{log_prefix} Failed to serialize result to JSON: {json_err}", exc_info=True)
             return jsonify({"error": "Failed to serialize result"}), 500

    elif task_status == "error":
        logging.warning(f"{log_prefix} Task failed. Returning error status.")
        return jsonify({"status": "error", "error": task.get("error", "Unknown error")}), 200 # Or maybe 500? 200 is okay if the query succeeded but task failed.
    elif task_status == "processing":
        logging.info(f"{log_prefix} Task still processing. Returning status.")
        return jsonify({"status": "processing"}), 202 # Use 202 Accepted for processing
    else:
        logging.error(f"{log_prefix} Unknown task status found: {task_status}")
        return jsonify({"error": f"Unknown task status: {task_status}"}), 500


# --- Health Check Endpoint ---
@app.route('/health', methods=['GET'])
def health_check():
    """A simple health check endpoint."""
    logging.debug("Received GET /health request.")
    return jsonify({"status": "ok"}), 200
# --- End Health Check Endpoint ---


if __name__ == '__main__':
    # This block is mainly for local development.
    # Gunicorn runs the 'app' object directly in production (based on Dockerfile CMD).
    logging.info("Starting Flask development server (DO NOT USE IN PRODUCTION)...")
    port = int(os.environ.get('PORT', 5000))
    # Set debug=False when running locally if you want logs similar to production
    # Set debug=True for Flask's interactive debugger (unsafe for prod)
    app.run(host='0.0.0.0', port=port, debug=False)
