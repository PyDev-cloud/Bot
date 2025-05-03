import time
import json
import atexit
import threading
import websocket
from seleniumwire import webdriver
from selenium.webdriver.chrome.options import Options
from signal_handler import extract_signal_data, get_trade_direction
from candle_handler import CandleHandler
from parse_instruments import parse_instruments_list


def extract_headers_and_ws_url():
    options = Options()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--start-maximized")

    driver = webdriver.Chrome(options=options)
    atexit.register(lambda: driver.quit())

    print("[⏳] Opening Quotex login page...")
    driver.get("https://qxbroker.com/en/trade")
    input("[🔐] Log in manually, then press ENTER here...")

    print("[✅] Logged in. Extracting cookies, headers, and WebSocket URL...")

    cookies = driver.get_cookies()
    cookie_header = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
    user_agent = driver.execute_script("return navigator.userAgent;")

    ws_url = None
    detected_symbol = None
    for request in driver.requests:
        if request.response and request.url.startswith("wss://") and "socket" in request.url:
            ws_url = request.url
        if request.method == "POST" and "candles" in request.url:
            try:
                body = request.body.decode("utf-8")
                data = json.loads(body)
                if "symbol" in data:
                    detected_symbol = data["symbol"]
                    print(f"[✅ Auto-detected Symbol from POST]: {detected_symbol}")
            except Exception as e:
                print("[⚠️ Error decoding symbol from POST]:", e)

    if not ws_url:
        raise Exception("❌ Could not detect WebSocket URL!")
    
    if not detected_symbol:
        print("[⚠️ Warning] Could not auto-detect symbol. Using default: AUDCAD")
        detected_symbol = "AUDCAD"

    headers = {
        "User-Agent": user_agent,
        "Origin": "https://qxbroker.com",
        "Cookie": cookie_header
    }

    return headers, ws_url, detected_symbol


def connect_to_websocket(headers, ws_url, symbol, timeframe=60):
    ws_headers = [f"{k}: {v}" for k, v in headers.items()]
    candle_handler = CandleHandler()

    def on_open(ws):
        print("[✅ Connected to WebSocket]")

        def send_ping():
            while True:
                try:
                    ws.send("2")
                    time.sleep(25)
                except:
                    break

        threading.Thread(target=send_ping, daemon=True).start()

    def on_message(ws, message):
        if isinstance(message, bytes):
            try:
                message = message.decode("utf-8", errors="ignore")
            except Exception as e:
                print(f"[❌ Decode Error]: {e}")
                return
        if message.strip() == "3":
            print("hello")
            return
            
        # Check if the message starts with the expected "♦[["
        if message.startswith("♦[["):
            try:
                print("Data lod")
                # Remove "♦[" from the beginning before parsing
                data = json.loads(message[2:])  # Start slicing at index 2
                
                # Ensure we have data to process
                if isinstance(data, list) and len(data) > 0:
                    print("Data work")
                    subdata = data[0]
                    asset_id = subdata[0]
                    symbol = subdata[1]
                    name = subdata[2]
                    asset_type = subdata[3]
                    signal_data = subdata[-1]

                    print(f"[🪙 Asset]: {symbol} ({name}) | Type: {asset_type}")
                    print("[📊 Signals by timeframe:]")

                    # Iterate over signal_data and print information
                    for entry in signal_data:
                        duration_sec, signal = entry
                        mins = duration_sec // 60
                        print(f"   ⏱️ {mins:>4} min → {signal.upper()}")
            except json.JSONDecodeError as e:
                print(f"Error decoding JSON: {e}")
            except Exception as e:
                print(f"Unexpected error: {e}")




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
    headers, ws_url, symbol = extract_headers_and_ws_url()
    print(json.dumps(headers, indent=4))
    print(f"[🌐 WebSocket URL]: {ws_url}")
    print(f"[📈 Detected Symbol]: {symbol}")
    connect_to_websocket(headers, ws_url, symbol)






def save_raw_message_to_file(message):
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename = f"raw_ws_data_{timestamp}.json"
    
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump({"timestamp": timestamp, "raw_message": message}, f, ensure_ascii=False, indent=4)
        print(f"[💾 Saved WebSocket message to]: {filename}")
    except Exception as e:
        print(f"[❌ Error saving message to file]: {e}")