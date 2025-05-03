class CandleHandler:
    def __init__(self):
        self.candles = []
        
    def add_candle(self, candle):
        self.candles.append(candle)
        # Keep only the last 100 candles to save memory
        if len(self.candles) > 100:
            self.candles = self.candles[-100:]
    
    def get_latest_candle(self):
        return self.candles[-1] if self.candles else None
    
    def get_previous_candle(self):
        return self.candles[-2] if len(self.candles) >= 2 else None