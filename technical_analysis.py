import numpy as np

def calculate_rsi(prices, period=14):
    deltas = np.diff(prices)
    seed = deltas[:period+1]
    up = seed[seed >= 0].sum()/period
    down = -seed[seed < 0].sum()/period
    rs = up/down
    rsi = 100 - (100/(1+rs))
    
    for i in range(period, len(prices)-1):
        delta = deltas[i]
        if delta > 0:
            upval = delta
            downval = 0
        else:
            upval = 0
            downval = -delta
            
        up = (up*(period-1) + upval)/period
        down = (down*(period-1) + downval)/period
        rs = up/down
        rsi = np.append(rsi, 100 - (100/(1+rs)))
        
    return rsi[-1]

def calculate_macd(prices, fast=12, slow=26, signal=9):
    exp1 = np.convolve(prices, np.ones(fast)/fast, mode='valid')
    exp2 = np.convolve(prices, np.ones(slow)/slow, mode='valid')
    macd = exp1[-1] - exp2[-1]
    
    # For signal line (EMA of MACD)
    macd_history = exp1 - exp2
    signal_line = np.convolve(macd_history, np.ones(signal)/signal, mode='valid')[-1]
    
    return macd, signal_line

def calculate_bollinger_bands(prices, window=20, num_std=2):
    sma = np.mean(prices[-window:])
    std = np.std(prices[-window:])
    
    upper = sma + (std * num_std)
    middle = sma
    lower = sma - (std * num_std)
    
    return upper, middle, lower