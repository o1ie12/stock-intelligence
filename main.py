import yfinance as yf
import pandas as pd
from universe_config import get_universe, DEFAULT_UNIVERSE

# Configuration
UNIVERSE_TYPE = DEFAULT_UNIVERSE  # Can be "sp500", "semiconductor", or "custom"

# Get universe from configuration
stocks = get_universe(UNIVERSE_TYPE)

data = []

for symbol in stocks:
    try:
        ticker = yf.Ticker(symbol)

        info = ticker.info

        history = ticker.history(period="6mo")

        if len(history) < 2:
            continue

        current_price = history["Close"].iloc[-1]
        old_price = history["Close"].iloc[0]

        momentum = (current_price / old_price) - 1

        data.append({
            "Ticker": symbol,
            "PE": info.get("trailingPE"),
            "Market Cap": info.get("marketCap"),
            "ROE": info.get("returnOnEquity"),
            "Momentum": momentum
        })

    except Exception as e:
        print(f"Error with {symbol}: {e}")

# Create DataFrame
df = pd.DataFrame(data)

# Replace missing values
df["ROE"] = df["ROE"].fillna(0)
df["Momentum"] = df["Momentum"].fillna(0)

# For PE, missing values get a large number (bad valuation)
df["PE"] = df["PE"].fillna(999)

# Factor rankings
df["ROE Rank"] = df["ROE"].rank(pct=True)

df["Momentum Rank"] = df["Momentum"].rank(pct=True)

# Lower PE is better
df["PE Rank"] = df["PE"].rank(
    pct=True,
    ascending=False
)

# Final weighted score
df["Score"] = (
    df["ROE Rank"] * 0.4 +
    df["Momentum Rank"] * 0.4 +
    df["PE Rank"] * 0.2
)

# Sort highest score first
df = df.sort_values(
    "Score",
    ascending=False
)

# Save results
df.to_csv(
    "stock_rankings.csv",
    index=False
)

print("\n=== STOCK RANKINGS ===\n")
print(
    df[
        [
            "Ticker",
            "PE",
            "ROE",
            "Momentum",
            "Score"
        ]
    ]
)

print("\nSaved to stock_rankings.csv")