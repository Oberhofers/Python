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

def save_signals_to_file():
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
        buy_signals[symbol].append((df.index[-1], close_price))
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
        sell_signals[symbol].append((df.index[-1], close_price))
        logging.info(f"Sell signal triggered for {symbol}: Close Price = {close_price}, RSI(60) = {rsi_value}")
    else:
        logging.info(f"No sell signal for {symbol}: Close Price = {close_price}, RSI(60) = {rsi_value}")

    return sell_signal

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
    """Execute a market buy order with proper balance check and precision handling."""
    try:
        current_time = time.time()
        if current_time - last_buy_time[symbol] < cooldown_period:
            logging.info(f"Cooldown active for {symbol}. Skipping buy order.")
            return
        
        logging.info(f"Checking USDT balance before buying {symbol}.")
        usdt_balance = safe_api_call(client.get_asset_balance, asset="USDT")
        if not usdt_balance or 'free' not in usdt_balance:
            logging.error("Failed to retrieve USDT balance. Aborting buy order.")
            return

        usdt_balance = float(usdt_balance['free'])
        logging.info(f"Current USDT balance: {usdt_balance:.2f} USDT")

        if usdt_balance < usdt_amount:
            logging.warning(f"Insufficient USDT balance ({usdt_balance:.2f}). Needed: {usdt_amount}. Aborting buy order for {symbol}.")
            return

        price = float(client.get_symbol_ticker(symbol=symbol)['price'])
        quantity = usdt_amount / price

        min_qty, step_size = get_symbol_precision(symbol)
        if min_qty is None or step_size is None:
            logging.error(f"Could not retrieve precision for {symbol}. Aborting buy order for {symbol}.")
            return

        precision = abs(int(math.log10(step_size)))  
        quantity = round(quantity - (quantity % step_size), precision)

        if quantity < min_qty:
            logging.error(f"Calculated quantity {quantity} is less than the minimum required {min_qty}. Aborting buy order for {symbol}.")
            return

        order = safe_api_call(client.order_market_buy, symbol=symbol, quantity=quantity)

        if order:
            logging.info(f"Buy order placed for {symbol}: {order}")
        else:
            logging.error(f"Failed to place buy order for {symbol}")

    except Exception as e:
        logging.error(f"Error placing buy order for {symbol}: {e}")

def execute_sell_order(symbol, quantity):
    """Place a sell order, adjusting quantity to the step size."""
    step_size = get_step_size(symbol)
    if step_size is None:
        logging.error(f"Could not retrieve step size for {symbol}. Aborting sell order.")
        return
    
    quantity = math.floor(quantity / step_size) * step_size
    logging.info(f"Adjusted quantity for {symbol}: {quantity}")

    if quantity == 0.0:
            logging.error(f"Quantitiy for {symbol} with {quantity} to low. Aborting sell order.")
            return

    try:
        order = safe_api_call(client.order_market_sell, symbol=symbol, quantity=quantity)
        if order:
            logging.info(f"Sell order placed for {symbol}: {order}")
        else:
            logging.error(f"Failed to place sell order for {symbol}.")
    except Exception as e:
        logging.error(f"Error placing sell order for {symbol}: {e}")

def plot_trading_signals(symbol, df, buy_signal, sell_signal):
    """Plot buy/sell signals on a chart."""
    plt.figure(figsize=(14, 8))
    plt.plot(df.index, df['close'], label='Close Price', color='black', alpha=0.5)
    plt.plot(df.index, df['upper_band'], label='Upper Band', color='red', linestyle='--')
    plt.plot(df.index, df['lower_band'], label='Lower Band', color='green', linestyle='--')
    plt.plot(df.index, df['SMA'], label='SMA', color='blue', linestyle='-.')
    
    # Plot all buy and sell signals from the history
    if buy_signals[symbol]:
        buy_dates, buy_prices = zip(*buy_signals[symbol])
        plt.scatter(buy_dates, buy_prices, marker='^', color='green', label='Buy Signal', alpha=0.7)
    
    if sell_signals[symbol]:
        sell_dates, sell_prices = zip(*sell_signals[symbol])
        plt.scatter(sell_dates, sell_prices, marker='v', color='red', label='Sell Signal', alpha=0.7)
    
    plt.xlabel('Time')
    plt.ylabel('Price (USDT)')
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
        if buy_signal:
            execute_buy_order(symbol, usdt_amount)
        if sell_signal:
            execute_sell_order(symbol, get_symbol_balance(symbol))
        plot_trading_signals(symbol, df, buy_signal, sell_signal)

    # Save the signals to a file after each trade cycle
    save_signals_to_file()

if __name__ == "__main__":
    while True:
        trade()
        time.sleep(60)
