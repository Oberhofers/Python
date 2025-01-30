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

def get_symbol_balance(symbol):
    """Fetch the balance of the symbol to sell."""
    balance = safe_api_call(client.get_asset_balance, asset=symbol[:-4])  # Removing "USDT" suffix for symbol
    if balance and 'free' in balance:
        return float(balance['free'])
    return 0.0

def calculate_bollinger_bands(df, window=20, std_dev=2):
    """Calculate Bollinger Bands."""
    df['SMA'] = df['close'].rolling(window=window).mean()
    df['STD'] = df['close'].rolling(window=window).std()
    df['upper_band'] = df['SMA'] + (df['STD'] * std_dev)
    df['lower_band'] = df['SMA'] - (df['STD'] * std_dev)
    return df

def calculate_rsi(df, window=14):
    """Calculate the Relative Strength Index (RSI)."""
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    return df

def plot_trading_signals(symbol, df, buy_signals, sell_signals):
    """Plot price with Bollinger Bands and buy/sell signals, ensuring time is displayed correctly."""
    
    # Convert timestamp from milliseconds and set it as index
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)
    
    # Ensure signals are properly extracted
    buy_indices = df.index[buy_signals].tolist()  # Extract timestamps for buys
    sell_indices = df.index[sell_signals].tolist()  # Extract timestamps for sells

    plt.figure(figsize=(14, 8))
    plt.plot(df.index, df['close'], label='Close Price', color='black', alpha=0.5)
    plt.plot(df.index, df['upper_band'], label='Upper Band', color='red', linestyle='--')
    plt.plot(df.index, df['lower_band'], label='Lower Band', color='green', linestyle='--')
    plt.plot(df.index, df['SMA'], label='SMA', color='blue', linestyle='-.')

    # Plot buy and sell signals correctly
    plt.scatter(buy_indices, df.loc[buy_indices, 'close'], marker='^', color='green', label='Buy Signal', s=100)
    plt.scatter(sell_indices, df.loc[sell_indices, 'close'], marker='v', color='red', label='Sell Signal', s=100)

    plt.xlabel('Time')
    plt.ylabel('Price (USDT)')
    plt.legend()
    plt.grid()
    plt.xticks(rotation=45)
    plt.gcf().autofmt_xdate()

    plt.savefig(f'{symbol}_trading_signals.png')
    plt.close()
    logging.info(f"Saved trading signals plot for {symbol}")

    # Debugging: Print number of buy and sell signals
    print(f"{symbol} - Buy signals: {len(buy_indices)}, Sell signals: {len(sell_indices)}")

def check_buy_signal(symbol, df, threshold=1.05):
    """Check buy signal based on latest data."""
    if len(df) < bollinger_window:
        return False
    lower_band, close_price, rsi = df.iloc[-1][['lower_band', 'close', 'RSI']]
    return close_price < lower_band * threshold and rsi < 30  # Buy when RSI is below 30 (oversold condition)

def check_sell_signal(symbol, df, threshold=70):
    """Check sell signal based on RSI."""
    if len(df) < bollinger_window:
        return False
    close_price, rsi = df.iloc[-1][['close', 'RSI']]
    return rsi > threshold  # Sell when RSI is above 70 (overbought condition)

def calculate_quantity_in_usdt(symbol, usdt_amount):
    """Calculate how much of the symbol to buy/sell with the given amount of USDT."""
    price = safe_api_call(client.get_symbol_ticker, symbol=symbol)
    if not price:
        return 0
    return usdt_amount / float(price['price'])

def place_buy_order(symbol, quantity):
    """Place a buy order for the given symbol and quantity."""
    try:
        order = client.order_market_buy(symbol=symbol, quantity=quantity)
        logging.info(f"Buy order placed for {symbol} with quantity {quantity}")
        return order
    except Exception as e:
        logging.error(f"Error placing buy order for {symbol}: {e}")
        return None

def place_sell_order(symbol, quantity):
    """Place a sell order for the given symbol and quantity."""
    try:
        order = client.order_market_sell(symbol=symbol, quantity=quantity)
        logging.info(f"Sell order placed for {symbol} with quantity {quantity}")
        return order
    except Exception as e:
        logging.error(f"Error placing sell order for {symbol}: {e}")
        return None

def trade():
    """Main trading function."""
    for symbol in symbols:
        df = safe_api_call(client.get_historical_klines, symbol, '1h', f"{lookback} hours ago UTC")
        if not df:
            continue
        df = pd.DataFrame([[float(x) for x in k[:5]] for k in df], columns=['open', 'high', 'low', 'close', 'volume'])
        df = calculate_bollinger_bands(df, bollinger_window, bollinger_std_dev)
        df = calculate_rsi(df)

        # Check for buy signal
        buy_signal = check_buy_signal(symbol, df)
        if buy_signal and (time.time() - last_buy_time[symbol]) > cooldown_period:
            balance = get_cached_balance()
            if balance and float(balance['free']) >= usdt_amount:
                quantity = calculate_quantity_in_usdt(symbol, usdt_amount)
                place_buy_order(symbol, quantity)
                last_buy_time[symbol] = time.time()

        # Check for sell signal
        sell_signal = check_sell_signal(symbol, df)
        if sell_signal:
            quantity_to_sell = get_symbol_balance(symbol)
            if quantity_to_sell > 0:
                place_sell_order(symbol, quantity_to_sell)

        plot_trading_signals(symbol, df, [], [])

if __name__ == "__main__":
    while True:
        try:
            trade()
            time.sleep(60)  # Wait for the next iteration
        except Exception as e:
            logging.error(f"Error in main loop: {e}")
            time.sleep(60)
