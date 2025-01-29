import ccxt
import pandas as pd
import pandas_ta as ta
import time

# Set up your Binance API keys
api_key = os.getenv('BINANCE_API_KEY')
api_secret = os.getenv('BINANCE_API_SECRET')
# Initialize Binance client
exchange = ccxt.binance({
    'apiKey': API_KEY,
    'secret': API_SECRET,
    'enableRateLimit': True,
})

# Trading parameters
symbol = 'BTC/USDT'
timeframe = '1h'  # 1-hour candlesticks
risk_per_trade = 0.01  # Risk 1% of account balance per trade
stop_loss_pct = 0.02  # 2% stop-loss
take_profit_pct = 0.05  # 5% take-profit

def fetch_ohlcv(symbol, timeframe, limit=100):
    """Fetch OHLCV (Open, High, Low, Close, Volume) data."""
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

def calculate_indicators(df):
    """Calculate technical indicators."""
    df['ema'] = ta.ema(df['close'], length=20)  # 20-period EMA
    df['rsi'] = ta.rsi(df['close'], length=14)  # 14-period RSI
    return df

def get_account_balance():
    """Fetch account balance in USDT."""
    balance = exchange.fetch_balance()
    return balance['total']['USDT']

def place_order(symbol, side, amount):
    """Place a market order."""
    try:
        order = exchange.create_market_order(symbol, side, amount)
        print(f"Order placed: {order}")
        return order
    except Exception as e:
        print(f"Error placing order: {e}")
        return None

def run_bot():
    print("Starting intelligent trading bot...")
    while True:
        try:
            # Fetch OHLCV data
            df = fetch_ohlcv(symbol, timeframe)
            df = calculate_indicators(df)

            # Get the latest data point
            latest = df.iloc[-1]
            price = latest['close']
            ema = latest['ema']
            rsi = latest['rsi']

            # Fetch account balance
            balance = get_account_balance()
            trade_amount = (balance * risk_per_trade) / price  # Calculate position size

            # Trading logic
            if rsi < 30 and price > ema:  # Buy signal: Oversold and price above EMA
                print(f"Buy signal detected! RSI: {rsi}, Price: {price}, EMA: {ema}")
                place_order(symbol, 'buy', trade_amount)

                # Set stop-loss and take-profit
                stop_loss_price = price * (1 - stop_loss_pct)
                take_profit_price = price * (1 + take_profit_pct)
                print(f"Stop-loss: {stop_loss_price}, Take-profit: {take_profit_price}")

            elif rsi > 70 or price < ema:  # Sell signal: Overbought or price below EMA
                print(f"Sell signal detected! RSI: {rsi}, Price: {price}, EMA: {ema}")
                place_order(symbol, 'sell', trade_amount)

            else:
                print(f"No trading signal. RSI: {rsi}, Price: {price}, EMA: {ema}")

            # Wait before the next iteration
            print("Waiting for the next candlestick...")
            time.sleep(60 * 60)  # Wait for 1 hour (adjust based on timeframe)

        except Exception as e:
            print(f"An error occurred: {e}")
            time.sleep(60)  # Wait before retrying

if __name__ == "__main__":
    run_bot()
