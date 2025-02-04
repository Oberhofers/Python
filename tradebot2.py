import matplotlib.pyplot as plt
import os
import time
import pandas as pd
import logging
from logging.handlers import RotatingFileHandler
from binance.client import Client
import math
import json

# Define the log file and rotation settings
log_file = 'tradebot.log'
max_log_size = 1024 * 1024 * 1024  # 1GB
backup_count = 5

# Create a rotating file handler
handler = RotatingFileHandler(log_file, maxBytes=max_log_size, backupCount=backup_count)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logging.basicConfig(level=logging.DEBUG, handlers=[handler])
logging.getLogger('binance').setLevel(logging.WARNING)

# Set up Binance API keys
api_key = os.getenv('BINANCE_API_KEY')
api_secret = os.getenv('BINANCE_API_SECRET')
if not api_key or not api_secret:
    logging.error("Missing Binance API keys. Check environment variables.")
    exit(1)

client = Client(api_key, api_secret)

# Trading parameters
symbols = ["ADAUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "SPELLUSDT", "BTCUSDT", "ETHUSDT"]
usdt_amount = 20
lookback = 100
bollinger_window = 14
bollinger_std_dev = 1.5
cooldown_period = 3600
last_buy_time = {symbol: 0 for symbol in symbols}
cached_balance = None
last_balance_check = 0
symbol_precision_cache = {}

# File paths for storing buy and sell signals
buy_sell_signals_file = 'buy_sell_signals.json'

def load_signals_from_file():
    """Load buy and sell signals from a file."""
    if os.path.exists(buy_sell_signals_file):
        with open(buy_sell_signals_file, 'r') as f:
            data = json.load(f)
            return data.get('buy_signals', {}), data.get('sell_signals', {})
    return {}, {}

def save_signals_to_file(buy_signals, sell_signals):
    """Save the buy and sell signals to a file."""
    data = {
        'buy_signals': buy_signals,
        'sell_signals': sell_signals
    }
    with open(buy_sell_signals_file, 'w') as f:
        json.dump(data, f, default=str)  # Convert timestamps to string for JSON compatibility
    logging.info("Buy and Sell signals saved to file.")

# Initialize buy and sell signals on bot startup
buy_signals, sell_signals = load_signals_from_file()

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

def get_symbol_balance(symbol):
    """Fetch the balance of the asset."""
    balance = safe_api_call(client.get_asset_balance, asset=symbol[:-4])
    return float(balance['free']) if balance and 'free' in balance else 0.0

def get_historical_data(symbol):
    """Fetch and process historical kline data."""
    data = safe_api_call(client.get_historical_klines, symbol, '1h', f"{lookback} hours ago UTC")
    if not data:
        return None
    df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', '_', '_', '_', '_', '_', '_'])
    df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
    df[['open', 'high', 'low', 'close', 'volume']] = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)
    return df

def calculate_bollinger_bands(df):
    """Calculate Bollinger Bands."""
    df['SMA'] = df['close'].rolling(window=bollinger_window).mean()
    df['STD'] = df['close'].rolling(window=bollinger_window).std()
    df['upper_band'] = df['SMA'] + (df['STD'] * bollinger_std_dev)
    df['lower_band'] = df['SMA'] - (df['STD'] * bollinger_std_dev)
    return df

def calculate_rsi(df, window=7):
    """Calculate the Relative Strength Index (RSI)."""
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0).rolling(window=window).mean()
    loss = -delta.where(delta < 0, 0).rolling(window=window).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    return df

def check_buy_signal(df, symbol):
    """Check for buy signal and store it."""
    rsi_value = df.iloc[-1]['RSI']
    close_price = df.iloc[-1]['close']
    lower_band = df.iloc[-1]['lower_band']

    logging.info(f"Checking buy signal for {symbol}: Close Price = {close_price}, RSI = {rsi_value}, Lower Band = {lower_band}")
    
    buy_signal = close_price < lower_band and rsi_value < 40
    if buy_signal:
        if symbol not in buy_signals:
            buy_signals[symbol] = []
        buy_signals[symbol].append((df.index[-1].isoformat(), close_price))
        logging.info(f"Buy signal triggered for {symbol}: Close Price = {close_price}, RSI(40) = {rsi_value}")
    else:
        logging.info(f"No buy signal for {symbol}: Close Price = {close_price}, RSI(40) = {rsi_value}")

    return buy_signal

def check_sell_signal(df, symbol):
    """Check for sell signal and store it."""
    rsi_value = df.iloc[-1]['RSI']
    close_price = df.iloc[-1]['close']
    upper_band = df.iloc[-1]['upper_band']

    logging.info(f"Checking sell signal for {symbol}: Close Price = {close_price}, RSI = {rsi_value}, Upper Band = {upper_band}")
    
    sell_signal = close_price > upper_band and rsi_value > 60
    if sell_signal:
        if symbol not in sell_signals:
            sell_signals[symbol] = []
        sell_signals[symbol].append((df.index[-1].isoformat(), close_price))
        logging.info(f"Sell signal triggered for {symbol}: Close Price = {close_price}, RSI(60) = {rsi_value}")
    else:
        logging.info(f"No sell signal for {symbol}: Close Price = {close_price}, RSI(60) = {rsi_value}")

    return sell_signal

def plot_trading_signals(symbol, df, buy_signals, sell_signals):
    """Plot buy/sell signals on a chart."""
    plt.figure(figsize=(14, 8))
    plt.plot(df.index, df['close'], label='Close Price', color='black', alpha=0.5)
    plt.plot(df.index, df['upper_band'], label='Upper Band', color='red', linestyle='--')
    plt.plot(df.index, df['lower_band'], label='Lower Band', color='green', linestyle='--')
    plt.plot(df.index, df['SMA'], label='SMA', color='blue', linestyle='-.')
    
    # Plot buy signals
    if symbol in buy_signals:
        buy_dates = [pd.to_datetime(date) for date, _ in buy_signals[symbol]]
        buy_prices = [price for _, price in buy_signals[symbol]]
        plt.scatter(buy_dates, buy_prices, marker='^', color='green', label='Buy Signal', alpha=0.7)
    
    # Plot sell signals
    if symbol in sell_signals:
        sell_dates = [pd.to_datetime(date) for date, _ in sell_signals[symbol]]
        sell_prices = [price for _, price in sell_signals[symbol]]
        plt.scatter(sell_dates, sell_prices, marker='v', color='red', label='Sell Signal', alpha=0.7)
    
    plt.xlabel('Time')
    plt.ylabel('Price (USDT)')
    plt.title(f'Trading Signals for {symbol}')
    plt.legend()
    plt.grid()
    plt.xticks(rotation=45)
    plt.savefig(f'{symbol}_trading_signals.png')
    plt.close()

def trade():
    """Main trading function."""
    for symbol in symbols:
        df = get_historical_data(symbol)
        if df is None:
            continue
        df = calculate_bollinger_bands(df)
        df = calculate_rsi(df)
        buy_signal = check_buy_signal(df, symbol)
        sell_signal = check_sell_signal(df, symbol)
        plot_trading_signals(symbol, df, buy_signals, sell_signals)

    # Save the signals to a file after each trade cycle
    save_signals_to_file(buy_signals, sell_signals)

if __name__ == "__main__":
    while True:
        trade()
        time.sleep(60)