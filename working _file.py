import time
import json
import atexit
import websocket
from seleniumwire import webdriver  # ✅ Use selenium-wire instead of normal Selenium
from selenium.webdriver.chrome.options import Options

def extract_headers_and_ws_url():
    options = Options()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--start-maximized")

    # ✅ Create selenium-wire driver
    driver = webdriver.Chrome(options=options)
    atexit.register(lambda: driver.quit())

    print("[⏳] Opening Quotex login page...")
    driver.get("https://qxbroker.com/en/trade")

    input("[🔐] Log in manually, then press ENTER here...")

    print("[✅] Logged in. Extracting cookies, headers, and WebSocket URL...")

    cookies = driver.get_cookies()
    cookie_header = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
    user_agent = driver.execute_script("return navigator.userAgent;")

    # ✅ Find WebSocket request from network logs
    ws_url = None
    for request in driver.requests:
        if request.response and request.url.startswith("wss://") and "socket" in request.url:
            ws_url = request.url
            break

    if not ws_url:
        raise Exception("❌ Could not detect WebSocket URL!")

    headers = {
        "User-Agent": user_agent,
        "Origin": "https://qxbroker.com",
        "Cookie": cookie_header
    }

    return headers, ws_url

def connect_to_websocket(headers, ws_url):
    ws_headers = [f"{k}: {v}" for k, v in headers.items()]

    def on_open(ws):
        print("[✅ Connected to WebSocket]")

    def on_message(ws, message):
        print("[📩 Received]:", message)

    def on_error(ws, error):
        print("[❌ Error]:", error)

    def on_close(ws, code, reason):
        print(f"[🔚 Closed]: {code} – {reason}")

    ws = websocket.WebSocketApp(
        ws_url,
        header=ws_headers,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )

    print(f"[📡 Connecting to WebSocket: {ws_url}]")
    ws.run_forever()

if __name__ == "__main__":
    headers, ws_url = extract_headers_and_ws_url()
    print(json.dumps(headers, indent=4))
    print(f"[🌐 WebSocket URL]: {ws_url}")
    connect_to_websocket(headers, ws_url)