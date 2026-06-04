import yfinance as yf
import pandas as pd

stocks = ["NVDA", "AMD", "TSM", "ASML"]

def fetch_stock(ticker):
    t = yf.Ticker(ticker)
    info = t.info
    hist = t.history(period="6mo")

    if len(hist) < 2:
        return None

    momentum = (hist["Close"].iloc[-1] / hist["Close"].iloc[0]) - 1

    return {
        "Ticker": ticker,
        "ROE": info.get("returnOnEquity"),
        "PE": info.get("trailingPE"),
        "Momentum": momentum
    }

def build_signals():
    data = []

    for s in stocks:
        try:
            r = fetch_stock(s)
            if r:
                data.append(r)
        except:
            pass

    df = pd.DataFrame(data)

    # clean
    df["ROE"] = df["ROE"].fillna(0)
    df["PE"] = df["PE"].fillna(999)
    df["Momentum"] = df["Momentum"].fillna(0)

    # factor ranks (cross-sectional)
    df["ROE_Rank"] = df["ROE"].rank(pct=True)
    df["PE_Rank"] = df["PE"].rank(pct=True, ascending=False)
    df["Momentum_Rank"] = df["Momentum"].rank(pct=True)

    # final score
    df["Score"] = (
        df["ROE_Rank"] * 0.4 +
        df["Momentum_Rank"] * 0.4 +
        df["PE_Rank"] * 0.2
    )

    return df