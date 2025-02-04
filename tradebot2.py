import matplotlib.pyplot as plt
import os
import time
import pandas as pd
import logging
from logging.handlers import RotatingFileHandler
from binance.client import Client
import math
import csv
from threading import Lock


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

# CSV for saving Trade Signals
signal_file = 'trade_signals.csv'

# Lock for thread safety
file_lock = Lock()

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

def save_trade_signal(symbol, signal_type, price, timestamp):
    """Save trade signals (buy/sell) to a CSV file.

    Args:
        symbol (str): The trading symbol (e.g., "BTC-USD").
        signal_type (str): The type of signal (e.g., "buy" or "sell").
        price (float): The price at which the signal was generated.
        timestamp (str): The timestamp of the signal.
    """
    try:
        logging.info("Attempting to save trade signal.")
        
        # Validate inputs
        if not all([symbol, signal_type, price, timestamp]):
            logging.error("Invalid input parameters.")
            raise ValueError("All parameters must be non-empty.")

        # Ensure the signal file path is set
        if not signal_file:
            logging.error("Signal file path is not defined.")
            raise ValueError("Signal file path must be defined.")

        # Use a lock to ensure thread safety
        with file_lock:
            file_exists = os.path.isfile(signal_file)

            with open(signal_file, mode='a', newline='') as file:
                writer = csv.writer(file)
                
                # Write header if the file doesn't exist
                if not file_exists:
                    writer.writerow(["timestamp", "symbol", "signal_type", "price"])
                
                # Write the trade signal
                writer.writerow([timestamp, symbol, signal_type, price])
                logging.info("Trade signal saved successfully.")

    except Exception as e:
        logging.error(f"Failed to save trade signal: {e}", exc_info=True)
        raise

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

def check_buy_signal(df,symbol):
    """return df.iloc[-1]['close'] < df.iloc[-1]['lower_band'] and df.iloc[-1]['RSI'] < 40"""
        # Calculate the current RSI and price condition
    rsi_value = df.iloc[-1]['RSI']
    close_price = df.iloc[-1]['close']
    lower_band = df.iloc[-1]['lower_band']

    # Log the RSI and price comparison
    logging.info(f"Checking buy signal for {symbol}: Close Price = {close_price}, RSI = {rsi_value}, Lower Band = {lower_band}")

    # Check if the price is below the lower band and RSI is under 40
    buy_signal = close_price < lower_band and rsi_value < 40

    if buy_signal:
        logging.info(f"Buy signal triggered for {symbol}: Close Price = {close_price}, RSI(40) = {rsi_value}")
    else:
        logging.info(f"No buy signal for {symbol}: Close Price = {close_price}, RSI(40) = {rsi_value}")

    return buy_signal

def check_sell_signal(df,symbol):
    """return df.iloc[-1]['close'] > df.iloc[-1]['upper_band'] and df.iloc[-1]['RSI'] > 60"""
    rsi_value = df.iloc[-1]['RSI']
    close_price = df.iloc[-1]['close']
    upper_band = df.iloc[-1]['upper_band']

    # Log the RSI and price comparison
    logging.info(f"Checking sell signal for {symbol}: Close Price = {close_price}, RSI = {rsi_value}, Upper Band = {upper_band}")

    # Check if the price is above the upper band and RSI is over 60
    sell_signal = close_price > upper_band and rsi_value > 60

    if sell_signal:
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

        # Get the available USDT balance
        usdt_balance = safe_api_call(client.get_asset_balance, asset="USDT")
        if not usdt_balance or 'free' not in usdt_balance:
            logging.error("Failed to retrieve USDT balance. Aborting buy order.")
            return

        usdt_balance = float(usdt_balance['free'])
        logging.info(f"Current USDT balance: {usdt_balance:.2f} USDT")

        # Ensure there is enough USDT to buy
        if usdt_balance < usdt_amount:
            logging.warning(f"Insufficient USDT balance ({usdt_balance:.2f}). Needed: {usdt_amount}. Aborting buy order for {symbol}.")
            return

        # Get the current price of the symbol
        price = float(client.get_symbol_ticker(symbol=symbol)['price'])
        
        # Calculate the quantity to buy based on the available USDT
        quantity = usdt_amount / price

        # Fetch symbol's precision and minimum quantity
        min_qty, step_size = get_symbol_precision(symbol)
        if min_qty is None or step_size is None:
            logging.error(f"Could not retrieve precision for {symbol}. Aborting buy order for {symbol}.")
            return

        # **Fix: Adjust quantity using stepSize**
        precision = abs(int(math.log10(step_size)))  # Get decimal places allowed
        quantity = round(quantity - (quantity % step_size), precision)  # Make sure quantity is a multiple of stepSize

        # Ensure the quantity meets the minimum quantity requirement
        if quantity < min_qty:
            logging.error(f"Calculated quantity {quantity} is less than the minimum required {min_qty}. Aborting buy order for {symbol}.")
            return

        # Place the buy order
        order = safe_api_call(client.order_market_buy, symbol=symbol, quantity=quantity)

        if order:
            logging.info(f"Buy order placed for {symbol}: {order}")
        else:
            logging.error(f"Failed to place buy order for {symbol}")

    except Exception as e:
        logging.error(f"Error placing buy order for {symbol}: {e}")




def get_step_size(symbol):
    """Fetch the step size from the Binance API."""
    symbol_info = safe_api_call(client.get_symbol_info, symbol)
    if symbol_info:
        for filter in symbol_info['filters']:
            if filter['filterType'] == 'LOT_SIZE':
                return float(filter['stepSize'])
    logging.error(f"Could not retrieve step size for {symbol}.")
    return None

def execute_sell_order(symbol, quantity):
    """Place a sell order, adjusting quantity to the step size."""
    step_size = get_step_size(symbol)
    if step_size is None:
        logging.error(f"Could not retrieve step size for {symbol}. Aborting sell order.")
        return
    
    # Round down the quantity to the nearest step size
    quantity = math.floor(quantity / step_size) * step_size
    logging.info(f"Adjusted quantity for {symbol}: {quantity}")

    if quantity == 0.0:
            logging.error(f"Quantitiy for {symbol} with {quantity} to low. Aborting sell order.")
            return

    # Place the sell order
    try:
        order = safe_api_call(client.order_market_sell, symbol=symbol, quantity=quantity)
        if order:
            logging.info(f"Sell order placed for {symbol}: {order}")
        else:
            logging.error(f"Failed to place sell order for {symbol}.")
    except Exception as e:
        logging.error(f"Error placing sell order for {symbol}: {e}")
        

def load_trade_signals(symbol):
    """Load past buy and sell signals for the given symbol from CSV."""
    if not os.path.exists(signal_file):
        return pd.DataFrame(columns=["timestamp", "symbol", "signal_type", "price"])
    
    df = pd.read_csv(signal_file)
    df["timestamp"] = pd.to_datetime(df["timestamp"])  # Convert to datetime
    df = df[df["symbol"] == symbol]  # Filter only for the given symbol
    return df

def plot_trading_signals(symbol, df):
    """Plot trading chart with past buy/sell signals."""
    plt.figure(figsize=(14, 8))
    plt.plot(df.index, df['close'], label='Close Price', color='black', alpha=0.5)
    plt.plot(df.index, df['upper_band'], label='Upper Band', color='red', linestyle='--')
    plt.plot(df.index, df['lower_band'], label='Lower Band', color='green', linestyle='--')
    plt.plot(df.index, df['SMA'], label='SMA', color='blue', linestyle='-.')

    # Load historical trade signals
    trade_signals = load_trade_signals(symbol)
    
    # Plot past buy signals
    buy_signals = trade_signals[trade_signals["signal_type"] == "BUY"]
    if not buy_signals.empty:
        plt.scatter(buy_signals["timestamp"], buy_signals["price"], marker='^', color='green', label='Past Buy', s=100)

    # Plot past sell signals
    sell_signals = trade_signals[trade_signals["signal_type"] == "SELL"]
    if not sell_signals.empty:
        plt.scatter(sell_signals["timestamp"], sell_signals["price"], marker='v', color='red', label='Past Sell', s=100)

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
        buy_signal = check_buy_signal(df,symbol)
        sell_signal = check_sell_signal(df,symbol)
        
        if buy_signal:
            execute_buy_order(symbol, usdt_amount)
            price = df.iloc[-1]['close']  # Fetch the latest close price
            save_trade_signal(symbol, "BUY", price, df.index[-1])
        if sell_signal:
            execute_sell_order(symbol, get_symbol_balance(symbol))
            price = df.iloc[-1]['close']  # Fetch the latest close price
            save_trade_signal(symbol, "SELL", price, df.index[-1])

        plot_trading_signals(symbol, df)

if __name__ == "__main__":
    while True:
        trade()
        time.sleep(60)