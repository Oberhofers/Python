import requests
import pandas as pd
import time

# Replace with your Bitpanda API key
API_KEY = "your_bitpanda_api_key"
BASE_URL = "https://api.bitpanda.com/v1"
HEADERS = {"Authorization": f"Bearer {API_KEY}"}

# Switch between live trading and simulation
LIVE_TRADING_MODE = False  # Set this to True for live trading, False for simulation

# Trade performance tracking
trade_history = []  # List to track past trades
total_wins = 0
total_losses = 0
total_profit = 0.0

# Simulate an order (for simulation mode)
def simulate_order(asset_symbol, fiat, amount, action="buy", price=None):
    print(f"Simulated {action.capitalize()} order: {amount} {fiat} worth of {asset_symbol}")
    return {"action": action, "symbol": asset_symbol, "amount": amount, "price": price}

# Place a market order (for live trading mode)
def place_market_order(asset_symbol, fiat, amount, action="buy"):
    global total_wins, total_losses, total_profit
    if LIVE_TRADING_MODE:
        order_type = "buy" if action == "buy" else "sell"
        url = f"{BASE_URL}/orders"
        payload = {
            "type": "MARKET",
            "instrument_code": f"{asset_symbol}_{fiat}",
            "amount": amount,
            "side": order_type,
        }
        response = requests.post(url, headers=HEADERS, json=payload)
        if response.status_code == 200:
            order = response.json()
            print(f"{action.capitalize()} order successful: {order}")
            return order
        else:
            print(f"Error placing {action} order: {response.status_code} - {response.text}")
            return None
    else:
        # Simulate the order if in simulation mode
        if action == "buy":
            # For simulation, we assume the price is passed (e.g., current market price)
            price = 100  # This should be fetched dynamically based on market conditions
            print(f"Simulated buy at price {price}")
            return simulate_order(asset_symbol, fiat, amount, action, price)
        elif action == "sell":
            price = 110  # Again, fetch the actual price in a real scenario
            print(f"Simulated sell at price {price}")
            # Track the outcome (win or loss) based on price comparison
            trade_history.append({"symbol": asset_symbol, "buy_price": 100, "sell_price": price, "amount": amount})
            profit_or_loss = (price - 100) * amount  # Example calculation: profit/loss = (sell price - buy price) * amount
            if profit_or_loss > 0:
                total_wins += 1
                total_profit += profit_or_loss
            else:
                total_losses += 1
                total_profit += profit_or_loss
            print(f"Simulated trade outcome: Profit/Loss = {profit_or_loss}")
            return simulate_order(asset_symbol, fiat, amount, action, price)

# Fetch all tradable assets
def fetch_all_assets():
    url = f"{BASE_URL}/assets"
    response = requests.get(url, headers=HEADERS)
    if response.status_code == 200:
        assets = response.json()
        tradable_assets = [asset for asset in assets if asset.get("tradable")]
        return tradable_assets
    else:
        print(f"Error fetching assets: {response.status_code} - {response.text}")
        return []

# Fetch historical data
def fetch_historical_data(asset_symbol, fiat="EUR", period="5m", limit=300):
    url = f"{BASE_URL}/candlesticks/{asset_symbol}_{fiat}"
    params = {"period": period, "limit": limit}
    response = requests.get(url, headers=HEADERS, params=params)
    if response.status_code == 200:
        data = response.json().get("candlesticks", [])
        df = pd.DataFrame(data, columns=["time", "open", "high", "low", "close", "volume"])
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df["close"] = df["close"].astype(float)
        return df
    else:
        print(f"Error fetching historical data for {asset_symbol}: {response.status_code} - {response.text}")
        return pd.DataFrame()

# Calculate indicators
def calculate_indicators(df):
    df["SMA20"] = df["close"].rolling(window=20).mean()
    df["SMA50"] = df["close"].rolling(window=50).mean()
    df["RSI"] = calculate_rsi(df["close"])
    df["BB_upper"], df["BB_lower"] = calculate_bollinger_bands(df["close"])
    return df

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_bollinger_bands(series, window=20, num_std_dev=2):
    sma = series.rolling(window=window).mean()
    std_dev = series.rolling(window=window).std()
    upper_band = sma + num_std_dev * std_dev
    lower_band = sma - num_std_dev * std_dev
    return upper_band, lower_band

# Intelligent live trading
def live_trading(asset_symbol, fiat, trade_amount):
    print(f"Fetching historical data for {asset_symbol}...")
    historical_data = fetch_historical_data(asset_symbol, fiat)
    if historical_data.empty:
        print(f"No data available for {asset_symbol}.")
        return

    print("Calculating indicators...")
    historical_data = calculate_indicators(historical_data)

    # Check the latest price and indicators
    latest_data = historical_data.iloc[-1]
    current_price = latest_data["close"]
    sma20 = latest_data["SMA20"]
    sma50 = latest_data["SMA50"]
    rsi = latest_data["RSI"]
    bb_upper = latest_data["BB_upper"]
    bb_lower = latest_data["BB_lower"]

    # Buy condition: RSI < 30 and price below lower Bollinger Band
    if rsi < 30 and current_price < bb_lower:
        print(f"Buying {asset_symbol} - Current Price: {current_price}, RSI: {rsi}")
        place_market_order(asset_symbol, fiat, trade_amount, action="buy")

    # Sell condition: RSI > 70 or price above upper Bollinger Band
    elif rsi > 70 or current_price > bb_upper:
        print(f"Selling {asset_symbol} - Current Price: {current_price}, RSI: {rsi}")
        place_market_order(asset_symbol, fiat, trade_amount, action="sell")

# Main function
def main():
    print("Fetching all tradable assets...")
    assets = fetch_all_assets()
    if not assets:
        print("No tradable assets found.")
        return

    print(f"Found {len(assets)} tradable assets.")
    trade_amount = 10  # EUR to trade per transaction

    while True:
        for asset in assets:
            asset_symbol = asset.get("symbol")
            asset_name = asset.get("name")
            print(f"Checking trading opportunities for {asset_name} ({asset_symbol})...")
            live_trading(asset_symbol, "EUR", trade_amount)

            # Respect API rate limits
            time.sleep(1)

        # Repeat the process every 5 minutes
        print("Waiting for the next cycle...")
        time.sleep(300)

        # Display the current win/loss status
        print(f"Total Wins: {total_wins}, Total Losses: {total_losses}, Total Profit: {total_profit}")

if __name__ == "__main__":
    main()
