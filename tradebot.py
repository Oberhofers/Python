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

# Configure the root logger
logging.basicConfig(
    level=logging.DEBUG,  # Adjust to DEBUG for detailed logs
    handlers=[handler]
)

# Test logging
logging.info("Logging system initialized successfully!")

# Set up your Binance API keys
api_key = os.getenv('BINANCE_API_KEY')
api_secret = os.getenv('BINANCE_API_SECRET')

client = Client(api_key, api_secret)

# Trading parameters
symbols = ['DOGEUSDT', 'SHIBUSDT', 'SPELLUSDT', 'ANIMEUSDT']
usdt_amount = 10  # Amount in USDT to trade
lookback = 100  # Lookback period for historical data
bollinger_window = 20  # Lookback period for Bollinger Bands
bollinger_std_dev = 2  # Standard deviation for Bollinger Bands
cooldown_period = 60  # Cooldown period in seconds
last_buy_time = {symbol: 0 for symbol in symbols}  # Track last buy time for each symbol

# Fetch USDT balance
usdt_balance = client.get_asset_balance(asset='USDT')
logging.info(f"USDT Balance: {usdt_balance}")

def plot_trading_signals(symbol, df, buy_signals, sell_signals):
    """Plot the price with Bollinger Bands and buy/sell signals."""
    plt.figure(figsize=(14, 8))
    plt.plot(df.index, df['close'], label='Close Price', color='black', alpha=0.5)
    plt.plot(df.index, df['upper_band'], label='Upper Band', color='red', linestyle='--')
    plt.plot(df.index, df['lower_band'], label='Lower Band', color='green', linestyle='--')
    plt.plot(df.index, df['SMA'], label='SMA', color='blue', linestyle='-.')

    # Mark buy and sell signals
    plt.scatter(
        df.index[buy_signals],
        df['close'].iloc[buy_signals],
        marker='^',
        color='green',
        label='Buy Signal',
        alpha=1
    )
    plt.scatter(
        df.index[sell_signals],
        df['close'].iloc[sell_signals],
        marker='v',
        color='red',
        label='Sell Signal',
        alpha=1
    )

    plt.title(f'{symbol} Price with Bollinger Bands and Trading Signals')
    plt.xlabel('Time')
    plt.ylabel('Price (USDT)')
    plt.legend()
    plt.grid()
    
    # Save the plot
    save_path = f'{symbol}_trading_signals.png'
    plt.savefig(save_path)
    logging.info(f"Saved trading signals plot to {save_path}")
    plt.close()

# Helper functions
def get_ohlcv(symbol, interval='1h', lookback=100):
    """Fetch historical OHLCV data."""
    klines = client.get_historical_klines(symbol, interval, f"{lookback} hours ago UTC")
    ohlcv = []
    for kline in klines:
        ohlcv.append([float(x) for x in kline[:5]])  # Open, High, Low, Close, Volume
    return pd.DataFrame(ohlcv, columns=['open', 'high', 'low', 'close', 'volume'])

def calculate_bollinger_bands(df, window=20, std_dev=2):
    """Calculate Bollinger Bands."""
    df = df.copy()  # Ensure we're working with a copy
    df.loc[:, 'SMA'] = df['close'].rolling(window=window).mean()
    df.loc[:, 'STD'] = df['close'].rolling(window=window).std()
    df.loc[:, 'upper_band'] = df['SMA'] + (df['STD'] * std_dev)
    df.loc[:, 'lower_band'] = df['SMA'] - (df['STD'] * std_dev)
    return df

def calculate_rsi(df, window=14):
    """Calculate the Relative Strength Index (RSI)."""
    df = df.copy()  # Ensure we're working with a copy
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    df.loc[:, 'RSI'] = 100 - (100 / (1 + rs))
    return df

def is_uptrend(df, sma_period=50):
    """Check if the asset is in an uptrend."""
    df = df.copy()  # Ensure we're working with a copy
    df.loc[:, 'SMA'] = df['close'].rolling(window=sma_period).mean()
    return df['close'].iloc[-1] > df['SMA'].iloc[-1]

def is_too_volatile(df, threshold=5):
    """Check if price changes are too volatile."""
    recent_change = abs(df['close'].iloc[-1] - df['close'].iloc[-2]) / df['close'].iloc[-2] * 100
    return recent_change > threshold

def calculate_quantity_in_usdt(symbol, usdt_amount):
    """Calculate the quantity to buy or sell based on USDT amount."""
    symbol_info = client.get_symbol_info(symbol)
    lot_size_filter = next(filter(lambda x: x['filterType'] == 'LOT_SIZE', symbol_info['filters']))
    min_qty = float(lot_size_filter['minQty'])
    step_size = float(lot_size_filter['stepSize'])
    symbol_price = float(client.get_symbol_ticker(symbol=symbol)['price'])
    quantity = usdt_amount / symbol_price
    quantity = (quantity // step_size) * step_size
    return max(quantity, min_qty)

# Trading logic
def check_buy_signal(symbol, df, threshold=1.05):
    """Check buy signal using Bollinger Bands, RSI, and trend filters."""
    lower_band = df['lower_band'].iloc[-1]
    close_price = df['close'].iloc[-1]
    rsi = df['RSI'].iloc[-1]
   
    if close_price < lower_band * threshold and is_uptrend(df) and rsi > 20 and not is_too_volatile(df):
        return True
    return False

def check_sell_signal(symbol, df):
    """Check sell signal using Bollinger Bands."""
    upper_band = df['upper_band'].iloc[-1]
    close_price = df['close'].iloc[-1]
    return close_price > upper_band

def place_buy_order(symbol, quantity):
    """Place a market buy order with a stop-loss."""
    try:
        # Place a market buy order
        order = client.order_market_buy(symbol=symbol, quantity=quantity)
        buy_price = float(order['fills'][0]['price'])
        stop_loss_price = buy_price * 0.98  # 2% stop-loss

        # Place a stop-loss limit order
        stop_loss_order = client.create_order(
            symbol=symbol,
            side='SELL',
            type='STOP_LOSS_LIMIT',
            quantity=quantity,
            price=round(stop_loss_price, 2),        # Limit price
            stopPrice=round(stop_loss_price, 2),   # Trigger price
            timeInForce='GTC'                      # Mandatory parameter
        )

        logging.info(f"Buy order placed for {symbol}: {order}")
        logging.info(f"Stop-loss order placed for {symbol} at {stop_loss_price}")
    except Exception as e:
        logging.error(f"Error placing buy order for {symbol}: {e}")

def place_sell_order(symbol):
    """Place a market sell order."""
    try:
        # Get the free balance of the asset
        asset = symbol.replace('USDT', '')
        asset_balance = float(client.get_asset_balance(asset=asset)['free'])
        
        # Get symbol info for precision details
        symbol_info = client.get_symbol_info(symbol)
        lot_size_filter = next(filter(lambda x: x['filterType'] == 'LOT_SIZE', symbol_info['filters']))
        min_qty = float(lot_size_filter['minQty'])
        step_size = float(lot_size_filter['stepSize'])

        # Adjust the quantity to match the step size and minimum quantity
        quantity = (asset_balance // step_size) * step_size
        quantity = round(quantity, len(str(step_size).split('.')[1]))  # Ensure proper precision

        if quantity >= min_qty:
            # Place the sell order
            order = client.order_market_sell(symbol=symbol, quantity=quantity)
            logging.info(f"Sell order placed for {symbol}: {order}")
        else:
            logging.warning(f"Insufficient balance to sell {symbol}. Available: {asset_balance}, Required: {min_qty}")

    except Exception as e:
        logging.error(f"Error placing sell order for {symbol}: {e}")

# Main trading loop
def trade():
    """Main trading loop."""
    for symbol in symbols:
        # Fetch OHLCV data
        df = get_ohlcv(symbol, lookback=lookback)
        
        # Calculate indicators
        df = calculate_bollinger_bands(df, window=bollinger_window, std_dev=bollinger_std_dev)
        df = calculate_rsi(df)
        
        # Generate buy and sell signals
        buy_signals = [i for i in range(len(df)) if check_buy_signal(symbol, df.iloc[:i+1])]
        sell_signals = [i for i in range(len(df)) if check_sell_signal(symbol, df.iloc[:i+1])]
        
        logging.debug(f"{symbol}: Buy signal = {check_buy_signal(symbol, df)}")
        logging.debug(f"{symbol}: Sell signal = {check_sell_signal(symbol, df)}")
        
        # Place buy order if conditions are met
        if check_buy_signal(symbol, df) and (time.time() - last_buy_time[symbol]) > cooldown_period:
            quantity = calculate_quantity_in_usdt(symbol, usdt_amount)
            place_buy_order(symbol, quantity)
            last_buy_time[symbol] = time.time()

        # Place sell order if conditions are met
        elif check_sell_signal(symbol, df):
            place_sell_order(symbol)
        
        # Plot trading signals
        plot_trading_signals(symbol, df, buy_signals, sell_signals)

# Run the bot
if __name__ == "__main__":
    while True:
        try:
            trade()
            time.sleep(60)  # Run every minute
        except Exception as e:
            logging.error(f"Error in main loop: {e}")
            time.sleep(60)
