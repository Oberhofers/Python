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
symbols = ["ADAUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "SPELLUSDT"]
usdt_amount = 100
lookback = 100
bollinger_window = 14
bollinger_std_dev = 1.5
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

def get_symbol_balance(symbol):
    """Fetch the balance of the asset."""
    balance = safe_api_call(client.get_asset_balance, asset=symbol[:-4])
    if balance and 'free' in balance:
        return float(balance['free'])
    return 0.0

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
    """Check if a buy signal is triggered."""
    return df.iloc[-1]['close'] < df.iloc[-1]['lower_band'] and df.iloc[-1]['RSI'] < 40

def check_sell_signal(df):
    """Check if a sell signal is triggered."""
    """return df.iloc[-1]['RSI'] > 70 """
    return df.iloc[-1]['close'] > df.iloc[-1]['upper_band'] and df.iloc[-1]['RSI'] > 60

def plot_trading_signals(symbol, df, buy_signals, sell_signals):
    """Plot the price with Bollinger Bands and buy/sell signals, with correct time axis."""
    df.index = pd.to_datetime(df.index, unit='ms')  # Convert timestamps
    plt.figure(figsize=(14, 8))
    plt.plot(df.index, df['close'], label='Close Price', color='black', alpha=0.5)
    plt.plot(df.index, df['upper_band'], label='Upper Band', color='red', linestyle='--')
    plt.plot(df.index, df['lower_band'], label='Lower Band', color='green', linestyle='--')
    plt.plot(df.index, df['SMA'], label='SMA', color='blue', linestyle='-.')
    
    # Ensure buy_signals and sell_signals are lists of indices
    buy_indices = [i for i, val in enumerate(buy_signals) if val]
    sell_indices = [i for i, val in enumerate(sell_signals) if val]
    
    plt.scatter(df.index[buy_indices], df['close'].iloc[buy_indices], marker='^', color='green', label='Buy Signal')
    plt.scatter(df.index[sell_indices], df['close'].iloc[sell_indices], marker='v', color='red', label='Sell Signal')
    
    plt.xlabel('Time')
    plt.ylabel('Price (USDT)')
    plt.legend()
    plt.grid()
    plt.xticks(rotation=45)
    plt.savefig(f'{symbol}_trading_signals.png')
    plt.close()
    logging.info(f"Saved trading signals plot for {symbol}")


def trade():
    """Main trading function."""
    for symbol in symbols:
        df = get_historical_data(symbol)
        if df is None:
            continue
        df = calculate_bollinger_bands(df)
        df = calculate_rsi(df)

        latest_rsi = df.iloc[-1]['RSI']  # Get the most recent RSI value

        # Print RSI in every loop iteration
        logging.info(f"RSI for {symbol}: {latest_rsi:.2f}")
        
        buy_signal = check_buy_signal(df)
        sell_signal = check_sell_signal(df)
        buy_signals = [df.index[-1]] if buy_signal else []
        sell_signals = [df.index[-1]] if sell_signal else []
        
        if buy_signal:
            logging.info(f"Buying {symbol}")
        if sell_signal:
            quantity_to_sell = get_symbol_balance(symbol)
            if quantity_to_sell > 0:
                logging.info(f"Selling {quantity_to_sell} of {symbol}")
        
        plot_trading_signals(symbol, df, buy_signals, sell_signals)

if __name__ == "__main__":
    while True:
        try:
            trade()
            time.sleep(5)
        except Exception as e:
            logging.error(f"Error in main loop: {e}")
            time.sleep(5)