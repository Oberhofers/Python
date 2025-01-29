import matplotlib.pyplot as plt
import os
import time
import pandas as pd
import logging
from logging.handlers import RotatingFileHandler
from binance.client import Client

# Define the log file and rotation settings
log_file = 'tradebot.log'
max_log_size = 1024 * 1024 * 1024  # 1GB
backup_count = 5

# Create a rotating file handler
handler = RotatingFileHandler(log_file, maxBytes=max_log_size, backupCount=backup_count)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logging.basicConfig(level=logging.DEBUG, handlers=[handler])

# Set up your Binance API keys
api_key = os.getenv('BINANCE_API_KEY')
api_secret = os.getenv('BINANCE_API_SECRET')
if not api_key or not api_secret:
    logging.error("Missing Binance API keys. Check environment variables.")
    exit(1)

client = Client(api_key, api_secret)

# Trading parameters
symbols = ['DOGEUSDT', 'SHIBUSDT', 'SPELLUSDT', 'ANIMEUSDT']
usdt_amount = 10
lookback = 100
bollinger_window = 20
bollinger_std_dev = 2
cooldown_period = 60
last_buy_time = {symbol: 0 for symbol in symbols}
cached_balance = None
last_balance_check = 0

def safe_api_call(func, *args, **kwargs):
    """Handle API rate limits with exponential backoff."""
    for i in range(5):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logging.warning(f"API call failed: {e}, retrying in {2 ** i} sec")
            time.sleep(2 ** i)
    logging.error("API call failed after multiple retries.")
    return None

def get_cached_balance():
    """Fetch USDT balance with caching."""
    global cached_balance, last_balance_check
    if time.time() - last_balance_check > 60:
        cached_balance = safe_api_call(client.get_asset_balance, asset='USDT')
        last_balance_check = time.time()
    return cached_balance

def plot_trading_signals(symbol, df, buy_signals, sell_signals):
    """Plot the price with Bollinger Bands and buy/sell signals, with correct time axis."""
    df.index = pd.to_datetime(df.index, unit='ms')  # Convert timestamps
    plt.figure(figsize=(14, 8))
    plt.plot(df.index, df['close'], label='Close Price', color='black', alpha=0.5)
    plt.plot(df.index, df['upper_band'], label='Upper Band', color='red', linestyle='--')
    plt.plot(df.index, df['lower_band'], label='Lower Band', color='green', linestyle='--')
    plt.plot(df.index, df['SMA'], label='SMA', color='blue', linestyle='-.')
    plt.scatter(df.index[buy_signals], df['close'].iloc[buy_signals], marker='^', color='green', label='Buy Signal')
    plt.scatter(df.index[sell_signals], df['close'].iloc[sell_signals], marker='v', color='red', label='Sell Signal')
    plt.xlabel('Time')
    plt.ylabel('Price (USDT)')
    plt.legend()
    plt.grid()
    plt.xticks(rotation=45)
    plt.savefig(f'{symbol}_trading_signals.png')
    plt.close()
    logging.info(f"Saved trading signals plot for {symbol}")

def check_buy_signal(symbol, df, threshold=1.05):
    """Check buy signal based on latest data."""
    if len(df) < bollinger_window:
        return False
    lower_band, close_price, rsi = df.iloc[-1][['lower_band', 'close', 'RSI']]
    return close_price < lower_band * threshold and rsi > 20

def trade():
    """Main trading function."""
    for symbol in symbols:
        df = safe_api_call(client.get_historical_klines, symbol, '1h', f"{lookback} hours ago UTC")
        if not df:
            continue
        df = pd.DataFrame([[float(x) for x in k[:5]] for k in df], columns=['open', 'high', 'low', 'close', 'volume'])
        df = calculate_bollinger_bands(df, bollinger_window, bollinger_std_dev)
        df = calculate_rsi(df)
        buy_signal = check_buy_signal(symbol, df)
        if buy_signal and (time.time() - last_buy_time[symbol]) > cooldown_period:
            balance = get_cached_balance()
            if balance and float(balance['free']) >= usdt_amount:
                quantity = calculate_quantity_in_usdt(symbol, usdt_amount)
                place_buy_order(symbol, quantity)
                last_buy_time[symbol] = time.time()
        plot_trading_signals(symbol, df, [], [])

if __name__ == "__main__":
    while True:
        try:
            trade()
            time.sleep(60)
        except Exception as e:
            logging.error(f"Error in main loop: {e}")
            time.sleep(60)
