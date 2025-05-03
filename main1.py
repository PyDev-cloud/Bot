import time
import json
import atexit
import threading
import websocket
from seleniumwire import webdriver
from selenium.webdriver.chrome.options import Options
from signal_handler import extract_signal_data, get_trade_direction
from candle_handler import CandleHandler

symbol = "EURUSD"  # Change if needed
timeframe = 60     # 60 seconds candle

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
        # Auto-detect asset symbol from WebSocket or REST request payload
        if "candles" in request.url and request.method == "POST":
            try:
                body = request.body.decode("utf-8")
                if "symbol" in body:
                    data = json.loads(body)
                    detected_symbol = data.get("symbol")
            except:
                continue


    if not ws_url:
        raise Exception("❌ Could not detect WebSocket URL!")
    
    if not detected_symbol:
        print("[⚠️ Warning] Could not auto-detect symbol. Using default: USDTRY_otc")
        detected_symbol = "USDTRY_otc"

    headers = {
        "User-Agent": user_agent,
        "Origin": "https://qxbroker.com",
        "Cookie": cookie_header
    }

    return headers, ws_url, detected_symbol

def connect_to_websocket(headers, ws_url):
    ws_headers = [f"{k}: {v}" for k, v in headers.items()]
    candle_handler = CandleHandler() 
    def on_open(ws):
        print("[✅ Connected to WebSocket]")

        def send_ping():
            while True:
                try:
                    ws.send("2")  # Send ping to keep connection alive
                    print("[📤 Ping sent]")
                    time.sleep(25)
                except:
                    break

        def send_subscribe():
            time.sleep(1.5)  # Wait for server to be ready
            payload = [
                "candles",
                {
                    "symbol": symbol,
                    "resolution": timeframe
                }
            ]
            message = f"42{json.dumps(payload)}"
            ws.send(message)
            print(f"[📤 Sent candle subscription for {symbol} ({timeframe}s)]")

        threading.Thread(target=send_ping, daemon=True).start()
        threading.Thread(target=send_subscribe).start()

    def on_message(ws, message):
        if isinstance(message, bytes):
            message = message.decode('utf-8') 
        print(f"[📩 RAW]: {message}")

        if message == "2":
            ws.send("3")
            print("[📡 Ping received → Sent pong]")
            return

        if message == "40":
            print("[🚀 Server is ready. Sending candle subscription...]")
            payload = [
                "candles",
                {
                    "symbol": symbol,
                    "resolution": timeframe
                }
            ]
            message = f"42{json.dumps(payload)}"
            ws.send(message)
            print(f"[📤 Sent candle subscription for {symbol} ({timeframe}s)]")
            """
        if message.startswith("42"):
            try:
                data = json.loads(message[2:])
                print("[📥 Parsed Message]:", data)  # DEBUG

                event = data[0]
                payload = data[1]

                if event == "candle-generated":
                    candle = payload['msg']['candle']
                    print(f"[🕯️ Candle] Time: {candle['time']} | Open: {candle['open']} | Close: {candle['close']}")
            except Exception as e:
                print(f"[❌ Error parsing 42 message]: {e}")"""
            
            if message.startswith("42"):
                try:
                    data = json.loads(message[2:])
                    print("[📥 Parsed Message]:", data)

                    event = data[0]
                    payload = data[1]
                    if event == "candle-generated":
                        candle_raw = payload['msg']['candle']
                        candle = {
                            "timestamp": candle_raw['time'],
                            "open": float(candle_raw['open']),
                            "high": float(candle_raw['max']),
                            "low": float(candle_raw['min']),
                            "close": float(candle_raw['close'])
                        }
                        print(f"[🕯️ Candle] {candle}")
                        rsi = candle_handler.process_new_candle(candle)
                        if rsi is not None:
                            print(f"[📈 RSI]: {rsi:.2f}")

                    # ✅ Handle 'instrument/list' type data with signals
                    elif isinstance(payload, list) and len(payload) > 12 and isinstance(payload[12], list):
                        detected_symbol, signals = extract_signal_data(payload)
                        direction = get_trade_direction(signals, timeframe)
                        if direction:
                            print(f"[📊 SIGNAL FOUND] {detected_symbol} | {timeframe}s → {direction.upper()}")
                        else:
                            print(f"[⚠️ NO SIGNAL] {detected_symbol} has no signal for {timeframe}s")

                    
                except Exception as e:
                    print(f"[❌ Error parsing 42 message]: {e}")


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
    connect_to_websocket(headers, ws_url)
