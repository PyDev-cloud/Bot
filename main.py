import time
import json
import atexit
import threading
import websocket
import numpy as np
from seleniumwire import webdriver
from selenium.webdriver.chrome.options import Options
from pprint import pprint

class CandleHandler:
    def __init__(self):
        self.candles = []
        
    def add_candle(self, candle):
        self.candles.append(candle)
        if len(self.candles) > 100:
            self.candles = self.candles[-100:]
    
    def get_latest_candle(self):
        return self.candles[-1] if self.candles else None
    
    def get_previous_candle(self):
        return self.candles[-2] if len(self.candles) >= 2 else None

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
        self.last_timestamp = None

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

            threading.Thread(target=self.send_ping, args=(ws,), daemon=True).start()
            self.send_subscriptions(ws)

        def on_message(ws, message):
            try:
                if message == "2":
                    ws.send("3")
                    return
                if message == "40":
                    return
                
                if isinstance(message, bytes):
                    self.process_binary_message(message)
                    return
                    
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
        while True:
            try:
                ws.send("2")
                time.sleep(25)
            except Exception as e:
                print(f"[PING ERROR] {e}")
                break

    def send_subscriptions(self, ws):
        time.sleep(2)
        subscriptions = [
            ["subscribe", {
                "name": "candles",
                "params": {
                    "symbol": self.symbol,
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
        try:
            if message[0] == 0x04:
                decoded = message[1:].decode('utf-8', errors='replace')
                
                try:
                    data = json.loads(decoded)
                    
                    if isinstance(data, list) and len(data) > 0:
                        for item in data:
                            if (isinstance(item, list) and len(item) >= 3 and 
                                item[0] == self.symbol):
                                timestamp = item[1]
                                price = item[2]
                                volume = item[3] if len(item) > 3 else 0
                                
                                print(f"\n[💰 {self.display_symbol} Price Update]")
                                print(f"⏱️ {time.strftime('%H:%M:%S', time.localtime(timestamp))}")
                                print(f"📈 Price: {price:.5f}")
                                print(f"📊 Volume: {volume}")
                                
                                self.last_price = price
                                self.last_timestamp = timestamp
                                self.generate_trading_signals(price, timestamp)
                                return
                
                    if isinstance(data, list):
                        if len(data) == 2 and data[0] == self.symbol:
                            print(f"\n[💰 {self.display_symbol} Quote]: {data[1]}")
                            self.handle_price_update(data[1])
                        
                        elif any(isinstance(x, list) for x in data):
                            for instrument in data:
                                if isinstance(instrument, list) and instrument[1] == self.symbol:
                                    print(f"\n[📊 {self.display_symbol} Instrument Update]")
                                    pprint(instrument)
                                    self.process_instrument_data(instrument)
            
                except json.JSONDecodeError:
                    print(f"[⚠️ Couldn't decode binary message: {decoded}]")
    
        except Exception as e:
            print(f"[❌ Binary message processing error] {str(e)}")

    def generate_trading_signals(self, price, timestamp):
        if not self.current_candle or not self.previous_candle:
            return
            
        price_change = price - self.last_price
        pct_change = (price_change / self.last_price) * 100
        
        rsi = self.indicators['rsi']
        macd = self.indicators['macd']['macd']
        macd_signal = self.indicators['macd']['signal']
        bb_upper = self.indicators['bollinger']['upper']
        bb_lower = self.indicators['bollinger']['lower']
        
        current_dir = "Bullish" if self.current_candle['close'] > self.current_candle['open'] else "Bearish"
        prev_dir = "Bullish" if self.previous_candle['close'] > self.previous_candle['open'] else "Bearish"
        
        next_dir = self.predict_next_direction()
        
        signal = self.generate_signal(
            current_dir=current_dir,
            prev_dir=prev_dir,
            rsi=rsi,
            macd=macd,
            macd_signal=macd_signal,
            price=price,
            bb_upper=bb_upper,
            bb_lower=bb_lower
        )
        
        self.print_signal_output(
            signal=signal,
            current_dir=current_dir,
            rsi=rsi,
            bb_width=bb_upper - bb_lower
        )
        
        self.signals.append({
            'timestamp': timestamp,
            'price': price,
            'signal': signal,
            'indicators': self.indicators.copy()
        })

    def predict_next_direction(self):
        score = 0
        
        if self.indicators['rsi'] > 70:
            score -= 2
        elif self.indicators['rsi'] < 30:
            score += 2
            
        if self.indicators['macd']['macd'] > self.indicators['macd']['signal']:
            score += 1
        else:
            score -= 1
            
        if self.last_price > self.indicators['bollinger']['upper']:
            score -= 1
        elif self.last_price < self.indicators['bollinger']['lower']:
            score += 1
            
        return "CALL 🔺" if score > 0 else "PUT 🔻"

    def generate_signal(self, current_dir, prev_dir, rsi, macd, macd_signal, price, bb_upper, bb_lower):
        if current_dir == "Bullish" and prev_dir == "Bullish":
            if rsi < 70 and price < bb_upper:
                return {
                    'direction': 'CALL 🔺',
                    'reason': 'Trend Continuation',
                    'confidence': 'High' if rsi > 50 else 'Medium'
                }
            elif rsi > 70:
                return {
                    'direction': 'PUT 🔻',
                    'reason': 'Overbought Reversal',
                    'confidence': 'High'
                }
        
        if current_dir == "Bullish" and prev_dir == "Bearish":
            if macd > macd_signal:
                return {
                    'direction': 'CALL 🔺',
                    'reason': 'Bullish Reversal',
                    'confidence': 'Medium'
                }
        
        if current_dir == "Bearish" and prev_dir == "Bearish":
            if rsi > 30 and price > bb_lower:
                return {
                    'direction': 'PUT 🔻',
                    'reason': 'Trend Continuation',
                    'confidence': 'High' if rsi < 50 else 'Medium'
                }
            elif rsi < 30:
                return {
                    'direction': 'CALL 🔺',
                    'reason': 'Oversold Reversal',
                    'confidence': 'High'
                }
                
        return {
            'direction': 'CALL 🔺' if macd > macd_signal else 'PUT 🔻',
            'reason': 'MACD Crossover',
            'confidence': 'Medium'
        }

    def print_signal_output(self, signal, current_dir, rsi, bb_width):
        print("\n" + "="*50)
        print("🔔 AI Trading Signal Bot")
        print("="*50)
        print(f"📊 Asset: {self.display_symbol}")
        print(f"🕒 Timeframe: M{int(self.timeframe/60)}" if self.timeframe >=60 else f"🕒 Timeframe: {self.timeframe}s")
        print(f"📈 Trend: {current_dir} (RSI: {int(rsi) if rsi else 'N/A'})")
        print(f"⚡ Volatility: {'High' if bb_width > 0.002 else 'Normal'}")
        print(f"📤 Signal: {signal['direction']}")
        print(f"📝 Reason: {signal['reason']}")
        print(f"✅ Confidence: {signal['confidence']}")
        print("="*50 + "\n")

    def calculate_rsi(self, prices, period=14):
        deltas = np.diff(prices)
        seed = deltas[:period+1]
        up = seed[seed >= 0].sum()/period
        down = -seed[seed < 0].sum()/period
        rs = up/down
        rsi = 100 - (100/(1+rs))
        
        for i in range(period, len(prices)-1):
            delta = deltas[i]
            upval = delta if delta > 0 else 0
            downval = -delta if delta < 0 else 0
            
            up = (up*(period-1) + upval)/period
            down = (down*(period-1) + downval)/period
            rs = up/down
            rsi = np.append(rsi, 100 - (100/(1+rs)))
            
        return rsi[-1]

    def calculate_macd(self, prices, fast=12, slow=26, signal=9):
        exp1 = np.convolve(prices, np.ones(fast)/fast, mode='valid')
        exp2 = np.convolve(prices, np.ones(slow)/slow, mode='valid')
        macd = exp1[-1] - exp2[-1]
        macd_history = exp1 - exp2
        signal_line = np.convolve(macd_history, np.ones(signal)/signal, mode='valid')[-1]
        return macd, signal_line

    def calculate_bollinger_bands(self, prices, window=20, num_std=2):
        sma = np.mean(prices[-window:])
        std = np.std(prices[-window:])
        upper = sma + (std * num_std)
        middle = sma
        lower = sma - (std * num_std)
        return upper, middle, lower

    def process_instrument_data(self, instrument_data):
        try:
            if not isinstance(instrument_data, list) or len(instrument_data) < 22:
                print("[⚠️ Invalid data structure]")
                return

            print(f"\n[📢 {self.display_symbol} Instrument Update]")
            print(f"⏱️ {time.strftime('%H:%M:%S')}")

            print("\n🔍 Basic Info:")
            print(f"  Type: {instrument_data[3]}")
            print(f"  Status: {'🟢 Active' if instrument_data[13] else '🔴 Inactive'}")
            
            print("\n💲 Options Pricing:")
            valid_options = []
            if isinstance(instrument_data[11], list):
                for option in instrument_data[11]:
                    if isinstance(option, dict) and 'price' in option and option['price'] > 0:
                        valid_options.append(option)
            
            if valid_options:
                for option in valid_options:
                    is_call = any(opt[0] == option['time'] and opt[1] == 'call' 
                                for opt in instrument_data[10] if isinstance(opt, list) and len(opt) > 1)
                    direction = "📈 CALL" if is_call else "📉 PUT"
                    print(f"  {direction} {option['time']}s: {option['price']:.5f}")
            else:
                print("  No valid options available")

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
            
        if data[0] == "candle-generated":
            if data[1].get("symbol") == self.symbol:
                print(f"\n[{self.display_symbol} CANDLE]")
                self.handle_candle_data(data[1])

    def handle_price_update(self, price):
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

            self.indicators['rsi'] = self.calculate_rsi(closes)
            macd, signal = self.calculate_macd(closes)
            self.indicators['macd']['macd'] = macd
            self.indicators['macd']['signal'] = signal
            upper, middle, lower = self.calculate_bollinger_bands(closes)
            self.indicators['bollinger'] = {
                'upper': upper,
                'middle': middle,
                'lower': lower
            }

            print(f"\n[📊 {self.display_symbol} Indicators]")
            print(f"📈 RSI: {self.indicators['rsi']:.2f}")
            print(f"📉 MACD: {macd:.5f} | Signal: {signal:.5f}")
            print(f"📊 Bollinger: U={upper:.5f} M={middle:.5f} L={lower:.5f}")

if __name__ == "__main__":
    bot = TradingBot()
    bot.extract_headers_and_ws_url()
    print(f"[🌐 WebSocket URL]: {bot.ws_url}")
    print(f"[📈 Trading Symbol]: {bot.display_symbol}")
    print(f"[⏳ Timeframe]: {bot.timeframe}s")
    bot.connect_to_websocket()