import time
import json
import atexit
import threading
import websocket
from seleniumwire import webdriver
from selenium.webdriver.chrome.options import Options
from candle_handler import CandleHandler
from technical_analysis import calculate_rsi, calculate_macd, calculate_bollinger_bands
from pprint import pprint

class TradingBot:
    def __init__(self):
        self.headers = None
        self.ws_url = None
        self.symbol = "USDCHF_otc"
        self.display_symbol = "USD/CHF (OTC)"
        self.timeframe = 60
        self.candle_handler = CandleHandler()
        self.current_candle = None
        self.previous_candle = None
        self.indicators = {
            'rsi': None,
            'macd': {'macd': None, 'signal': None},
            'bollinger': {'upper': None, 'middle': None, 'lower': None}
        }
        self.signals = []
        self.previous_indicators = {}
        self.ws = None
        self.last_price = None

    def extract_headers_and_ws_url(self):
        options = Options()
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--start-maximized")

        driver = webdriver.Chrome(options=options)
        atexit.register(lambda: driver.quit())

        print("[⏳] Opening Quotex login page...")
        driver.get("https://qxbroker.com/en/trade")
        input("[🔐] Log in manually, then press ENTER here...")

        print("[✅] Logged in. Extracting cookies, headers, and WebSocket URL...")
        time.sleep(3)

        cookies = driver.get_cookies()
        cookie_header = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
        user_agent = driver.execute_script("return navigator.userAgent;")

        ws_url = None
        for request in driver.requests:
            if request.response and request.url.startswith("wss://") and "socket" in request.url:
                ws_url = request.url
                break

        if not ws_url:
            raise Exception("❌ Could not detect WebSocket URL!")

        self.headers = {
            "User-Agent": user_agent,
            "Origin": "https://qxbroker.com",
            "Cookie": cookie_header
        }
        self.ws_url = ws_url

    def connect_to_websocket(self):
        if not self.headers or not self.ws_url:
            raise Exception("Headers or WebSocket URL not set!")

        ws_headers = [f"{k}: {v}" for k, v in self.headers.items()]

        def on_open(ws):
            print("[✅ Connected to WebSocket]")
            ws.send('2probe')
            time.sleep(1)

            # Start ping thread
            threading.Thread(target=self.send_ping, args=(ws,), daemon=True).start()
            
            # Send subscriptions
            self.send_subscriptions(ws)

        def on_message(ws, message):
            try:
                # Handle ping-pong
                if message == "2":
                    ws.send("3")
                    return
                if message == "40":
                    return
                
                # Handle binary messages
                if isinstance(message, bytes):
                    self.process_binary_message(message)
                    return
                    
                # Handle text messages
                if message.startswith("42"):
                    try:
                        data = json.loads(message[2:])
                        self.process_relevant_data(data)
                    except Exception as e:
                        print(f"[TEXT DECODE ERROR] {e}")
            except Exception as e:
                print(f"[MESSAGE HANDLER ERROR] {e}")

        def on_error(ws, error):
            print(f"[❌ WebSocket Error]: {error}")

        def on_close(ws, code, reason):
            print(f"[🔚 WebSocket Closed]: {code} - {reason}")
            time.sleep(5)
            print("[🔄 Attempting to reconnect...]")
            self.connect_to_websocket()

        print(f"[📡 Connecting to WebSocket: {self.ws_url}]")
        self.ws = websocket.WebSocketApp(
            self.ws_url,
            header=ws_headers,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close
        )
        self.ws.run_forever()

    def send_ping(self, ws):
        """Send regular ping messages to keep connection alive"""
        while True:
            try:
                ws.send("2")
                time.sleep(25)
            except Exception as e:
                print(f"[PING ERROR] {e}")
                break

    def send_subscriptions(self, ws):
        """Send all required subscription messages"""
        time.sleep(2)
        subscriptions = [
            ["subscribe", {
                "name": "candles",
                "params": {
                    "symbol": self.symbol,  # Using correct symbol format
                    "timeframe": self.timeframe,
                    "type": "OTC"
                }
            }],
            ["cmd", {
                "name": "subscribe",
                "params": {
                    "routingFilters": {
                        "symbol": self.symbol,
                        "instrument_type": "OTC"
                    }
                }
            }],
            ["subscribe", {
                "name": "quotes/stream",
                "params": {
                    "symbol": self.symbol
                }
            }]
        ]

        for sub in subscriptions:
            try:
                message = f"42{json.dumps(sub)}"
                ws.send(message)
                print(f"[📤 Sent]: {message[:100]}...")
                time.sleep(0.3)
            except Exception as e:
                print(f"[❌ Subscription error]: {e}")

    def process_binary_message(self, message):
        """Process binary WebSocket messages"""
        try:
            if message[0] == 0x04:  # Binary message header
                decoded = message[1:].decode('utf-8')
                data = json.loads(decoded)
                
                if isinstance(data, list):
                    # Handle price quotes
                    if len(data) == 2 and data[0] == self.symbol:
                        print(f"\n[💰 {self.display_symbol} Quote]: {data[1]}")
                        self.handle_price_update(data[1])
                    
                    # Handle instrument lists
                    elif any(isinstance(x, list) for x in data):
                        for instrument in data:
                            if isinstance(instrument, list) and instrument[1] == self.symbol:
                                print(f"\n[📊 {self.display_symbol} Instrument Update]")
                                pprint(instrument)
                                self.process_instrument_data(instrument)
        except Exception as e:
            print(f"[BINARY DECODE ERROR] {e}")



   








    def process_instrument_data(self, instrument_data):
        """Fixed version that properly detects valid options"""
        try:
            # Validate input structure
            if not isinstance(instrument_data, list) or len(instrument_data) < 22:
                print("[⚠️ Invalid data structure]")
                return

            print(f"\n[📢 {self.display_symbol} Instrument Update]")
            print(f"⏱️ {time.strftime('%H:%M:%S')}")

            # Basic info section
            print("\n🔍 Basic Info:")
            print(f"  Type: {instrument_data[3]}")
            print(f"  Status: {'🟢 Active' if instrument_data[13] else '🔴 Inactive'}")
            
            # Options pricing section - FIXED HERE
            print("\n💲 Options Pricing:")
            valid_options = []
            if isinstance(instrument_data[11], list):
                for option in instrument_data[11]:
                    if isinstance(option, dict) and 'price' in option and option['price'] > 0:
                        valid_options.append(option)
            
            if valid_options:
                for option in valid_options:
                    # Fixed direction detection logic
                    is_call = any(opt[0] == option['time'] and opt[1] == 'call' 
                                for opt in instrument_data[10] if isinstance(opt, list) and len(opt) > 1)
                    direction = "📈 CALL" if is_call else "📉 PUT"
                    print(f"  {direction} {option['time']}s: {option['price']:.5f}")
            else:
                print("  No valid options available")

            # Rest of the method remains the same...
            print("\n📈 Market Analysis:")
            if isinstance(instrument_data[19], (int, float)):
                trend = "⬆️ Bullish" if instrument_data[19] >= 0 else "⬇️ Bearish"
                print(f"  Trend: {trend} ({instrument_data[19]:.2f})")
            
            if isinstance(instrument_data[20], (int, float)):
                print(f"  Volatility: {instrument_data[20]:.2f} {'(High)' if instrument_data[20] > 50 else '(Normal)'}")

        except Exception as e:
            print(f"\n[❌ Processing Error] {type(e).__name__}: {str(e)}")
            print("[ℹ️ Data Sample]:")
            if isinstance(instrument_data, list) and len(instrument_data) > 10:
                print(f"Options Data: {instrument_data[11]}")
                print(f"Option Types: {instrument_data[10]}")








    def process_relevant_data(self, data):                 
        if not isinstance(data, list):
            return      
            
        # Handle candle data
        if data[0] == "candle-generated":
            if data[1].get("symbol") == self.symbol:
                print(f"\n[{self.display_symbol} CANDLE]")
                self.handle_candle_data(data[1])

    def handle_price_update(self, price):
        """Handle real-time price updates"""
        print(f"[📈 Price Update] {time.ctime()}: {price:.5f}")
        if self.last_price is not None:
            change = (price - self.last_price) / self.last_price * 100
            print(f"Change: {change:.2f}%")
        self.last_price = price

    def handle_candle_data(self, payload):
        candle_raw = payload['msg']['candle']
        new_candle = {
            "timestamp": candle_raw['time'],
            "open": float(candle_raw['open']),
            "high": float(candle_raw['max']),
            "low": float(candle_raw['min']),
            "close": float(candle_raw['close']),
            "volume": float(candle_raw.get('volume', 0))
        }

        self.previous_candle = self.current_candle
        self.current_candle = new_candle

        print(f"\n[🕯️ {self.display_symbol} Candle] {self.timeframe}s")
        print(f"⏰ Time: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(new_candle['timestamp']))}")
        print(f"📊 O: {new_candle['open']:.5f} H: {new_candle['high']:.5f} L: {new_candle['low']:.5f} C: {new_candle['close']:.5f}")

        if self.previous_candle:
            change = ((new_candle['close'] - self.previous_candle['close']) / self.previous_candle['close']) * 100
            print(f"📈 Change: {change:.2f}%")

        self.update_indicators(new_candle)
        self.generate_signals()

    def update_indicators(self, candle):
        self.candle_handler.add_candle(candle)

        if len(self.candle_handler.candles) >= 14:
            closes = [c['close'] for c in self.candle_handler.candles[-14:]]

            self.indicators['rsi'] = calculate_rsi(closes)
            macd, signal = calculate_macd(closes)
            self.indicators['macd']['macd'] = macd
            self.indicators['macd']['signal'] = signal
            upper, middle, lower = calculate_bollinger_bands(closes)
            self.indicators['bollinger'] = {
                'upper': upper,
                'middle': middle,
                'lower': lower
            }

            print(f"\n[📊 {self.display_symbol} Indicators]")
            print(f"📈 RSI: {self.indicators['rsi']:.2f}")
            print(f"📉 MACD: {macd:.5f} | Signal: {signal:.5f}")
            print(f"📊 Bollinger: U={upper:.5f} M={middle:.5f} L={lower:.5f}")

    # ... [rest of your methods remain unchanged] ...

if __name__ == "__main__":
    bot = TradingBot()
    bot.extract_headers_and_ws_url()
    print(f"[🌐 WebSocket URL]: {bot.ws_url}")
    print(f"[📈 Trading Symbol]: {bot.display_symbol}")
    print(f"[⏳ Timeframe]: {bot.timeframe}s")
    bot.connect_to_websocket()