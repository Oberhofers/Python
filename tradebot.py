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

# Set up Binance API keys
api_key = os.getenv('BINANCE_API_KEY')
api_secret = os.getenv('BINANCE_API_SECRET')
if not api_key or not api_secret:
    logging.error("Missing Binance API keys. Check environment variables.")
    exit(1)

client = Client(api_key, api_secret)

# Trading parameters
symbols = ["ADAUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "SPELLUSDT", "BTCUSDT", "ETHUSDT"]
usdt_amount = 100
lookback = 100
bollinger_window = 14
bollinger_std_dev = 1.5
cooldown_period = 60
last_buy_time = {symbol: 0 for symbol in symbols}
cached_balance = None
last_balance_check = 0
symbol_precision_cache = {}

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

def check_buy_signal(df):
    return df.iloc[-1]['close'] < df.iloc[-1]['lower_band'] and df.iloc[-1]['RSI'] < 40

def check_sell_signal(df):
    return df.iloc[-1]['close'] > df.iloc[-1]['upper_band'] and df.iloc[-1]['RSI'] > 60

def get_symbol_precision(symbol):
    """Fetch symbol precision and minimum quantity."""
    if symbol in symbol_precision_cache:
        return symbol_precision_cache[symbol]
    info = safe_api_call(client.get_symbol_info, symbol)
    if info:
        for filter in info['filters']:
            if filter['filterType'] == 'LOT_SIZE':
                min_qty = float(filter['minQty'])
                step_size = float(filter['stepSize'])
                symbol_precision_cache[symbol] = (min_qty, step_size)
                return min_qty, step_size
    return None, None

def execute_buy_order(symbol, usdt_amount):
    price = float(client.get_symbol_ticker(symbol=symbol)['price'])
    quantity = usdt_amount / price
    min_qty, step_size = get_symbol_precision(symbol)
    if min_qty is None or step_size is None:
        return
    precision = len(str(step_size).split(".")[-1]) if '.' in str(step_size) else 0
    quantity = round(quantity, precision)
    if quantity < min_qty:
        return
    order = client.order_market_buy(symbol=symbol, quantity=quantity)
    logging.info(f"Buy order placed: {order}")

def execute_sell_order(symbol, quantity):
    order = client.order_market_sell(symbol=symbol, quantity=quantity)
    logging.info(f"Sell order placed: {order}")

def plot_trading_signals(symbol, df, buy_signal, sell_signal):
    plt.figure(figsize=(14, 8))
    plt.plot(df.index, df['close'], label='Close Price', color='black', alpha=0.5)
    plt.plot(df.index, df['upper_band'], label='Upper Band', color='red', linestyle='--')
    plt.plot(df.index, df['lower_band'], label='Lower Band', color='green', linestyle='--')
    plt.plot(df.index, df['SMA'], label='SMA', color='blue', linestyle='-.')
    if buy_signal:
        plt.scatter(df.index[-1], df['close'].iloc[-1], marker='^', color='green', label='Buy Signal')
    if sell_signal:
        plt.scatter(df.index[-1], df['close'].iloc[-1], marker='v', color='red', label='Sell Signal')
    plt.xlabel('Time')
    plt.ylabel('Price (USDT)')
    plt.legend()
    plt.grid()
    plt.xticks(rotation=45)
    plt.savefig(f'{symbol}_trading_signals.png')
    plt.close()

def trade():
    for symbol in symbols:
        df = get_historical_data(symbol)
        if df is None:
            continue
        df = calculate_bollinger_bands(df)
        df = calculate_rsi(df)
        buy_signal = check_buy_signal(df)
        sell_signal = check_sell_signal(df)
        if buy_signal:
            execute_buy_order(symbol, usdt_amount)
        if sell_signal:
            execute_sell_order(symbol, get_symbol_balance(symbol))
        plot_trading_signals(symbol, df, buy_signal, sell_signal)

if __name__ == "__main__":
    while True:
        trade()
        time.sleep(5)
