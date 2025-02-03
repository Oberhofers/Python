import matplotlib.pyplot as plt
import os
import time
import pandas as pd
import logging
from logging.handlers import RotatingFileHandler
from binance.client import Client
import math

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
stop_loss_percentage = 0.05  # 5% stop-loss
last_buy_time = {symbol: 0 for symbol in symbols}
cached_balance = None
last_balance_check = 0
symbol_precision_cache = {}
buy_prices = {}

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

def execute_sell_order(symbol, quantity):
    """Place a sell order, adjusting quantity to the step size."""
    step_size = get_step_size(symbol)
    if step_size is None:
        logging.error(f"Could not retrieve step size for {symbol}. Aborting sell order.")
        return
    
    # Round down the quantity to the nearest step size
    quantity = math.floor(quantity / step_size) * step_size
    logging.info(f"Adjusted quantity for {symbol}: {quantity}")

    # Place the sell order
    try:
        order = safe_api_call(client.order_market_sell, symbol=symbol, quantity=quantity)
        if order:
            logging.info(f"Sell order placed for {symbol}: {order}")
        else:
            logging.error(f"Failed to place sell order for {symbol}.")
    except Exception as e:
        logging.error(f"Error placing sell order for {symbol}: {e}")

def trade():
    for symbol in symbols:
        df = get_historical_data(symbol)
        if df is None:
            continue
        df = calculate_bollinger_bands(df)
        df = calculate_rsi(df)
        buy_signal = check_buy_signal(df, symbol)
        sell_signal = check_sell_signal(df, symbol)
        
        # Implement stop-loss check first
        if symbol in buy_prices:
            stop_loss_price = buy_prices[symbol] * (1 - stop_loss_percentage)
            if df.iloc[-1]['close'] < stop_loss_price:
                logging.warning(f"Stop-loss triggered for {symbol} at {df.iloc[-1]['close']:.4f}")
                execute_sell_order(symbol, get_symbol_balance(symbol))
                del buy_prices[symbol]  # Remove from tracking after selling
                continue  # Skip further checks if stop-loss is triggered
        
        if buy_signal:
            execute_buy_order(symbol, usdt_amount)
            buy_prices[symbol] = df.iloc[-1]['close']
        if sell_signal:
            execute_sell_order(symbol, get_symbol_balance(symbol))
        
        plot_trading_signals(symbol, df, buy_signal, sell_signal)

if __name__ == "__main__":
    while True:
        trade()
        time.sleep(60)
