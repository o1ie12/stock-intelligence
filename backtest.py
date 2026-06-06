import pandas as pd
import yfinance as yf

from model import fetch_stock
from portfolio_engine import build_shared_portfolio
from universe_config import get_universe, DEFAULT_UNIVERSE

# Configuration
UNIVERSE_TYPE = DEFAULT_UNIVERSE  # Can be "sp500", "semiconductor", or "custom"

# Get universe from configuration
stocks = get_universe(UNIVERSE_TYPE)

benchmark = "SPY"


def get_price_data(tickers):
    data = {}

    for ticker in tickers:
        try:
            close = yf.Ticker(ticker).history(period="2y")["Close"]
            if not close.empty:
                data[ticker] = close
        except Exception:
            continue

    return pd.DataFrame(data)


def get_backtest_weights(tickers, max_holdings=5, max_position=0.35, min_position=0.05, cash_reserve=0.05):
    """
    Use shared portfolio construction for backtest to ensure consistency.
    This replaces the old build_score_frame + manual weighting logic.
    """
    target_portfolio = build_shared_portfolio(
        tickers=tickers,
        cash_reserve=cash_reserve,
        max_holdings=max_holdings,
        max_position=max_position,
        min_position=min_position
    )
    
    # Convert to weight series for backtest compatibility
    if target_portfolio.empty:
        return pd.Series(dtype=float)
    
    weights_df = target_portfolio[target_portfolio["Ticker"] != "CASH"]
    if weights_df.empty:
        return pd.Series(dtype=float)
    
    weights = weights_df.set_index("Ticker")["Target Weight"]
    return weights


prices = get_price_data(stocks)
returns = prices.pct_change().dropna()

spy = yf.Ticker(benchmark).history(period="2y")["Close"]
spy_returns = spy.pct_change().dropna()
spy_cum = (1 + spy_returns).cumprod()

# monthly rebalance points
rebalance_dates = prices.resample("BME").last().index

portfolio_value = 1.0
portfolio_return_periods = []

# Use shared portfolio construction for consistency
weights = get_backtest_weights(stocks)
weights = weights.reindex(returns.columns).fillna(0)

for i in range(2, len(rebalance_dates)):
    start = rebalance_dates[i - 1]
    end = rebalance_dates[i]

    if weights.empty:
        continue

    period_returns = returns.loc[(returns.index > start) & (returns.index <= end)].fillna(0)

    if period_returns.empty:
        continue

    portfolio_returns_for_period = period_returns.dot(weights)
    portfolio_return_periods.append(portfolio_returns_for_period)

    growth = (1 + portfolio_returns_for_period).prod()
    portfolio_value *= growth

if portfolio_return_periods:
    portfolio_returns = pd.concat(portfolio_return_periods).sort_index()
    portfolio_curve = (1 + portfolio_returns).cumprod()
else:
    portfolio_returns = pd.Series(dtype=float)
    portfolio_curve = pd.Series(dtype=float)

aligned_spy_returns = spy_returns.reindex(portfolio_returns.index).fillna(0)
spy_cum = (1 + aligned_spy_returns).cumprod()
portfolio_returns = portfolio_returns.reindex(spy_cum.index).dropna()
portfolio_curve = (1 + portfolio_returns).cumprod()
spy_cum = spy_cum.reindex(portfolio_curve.index).dropna()

if not portfolio_curve.empty:
    portfolio_value = portfolio_curve.iloc[-1]

running_max = portfolio_curve.cummax()
drawdown = (portfolio_curve / running_max) - 1
max_drawdown = drawdown.min() if not drawdown.empty else 0

volatility = portfolio_returns.std() * (252 ** 0.5) if not portfolio_returns.empty else 0
sharpe = (portfolio_returns.mean() * 252) / volatility if volatility else 0

results = pd.DataFrame({
    "portfolio": portfolio_curve,
    "spy": spy_cum,
})
results.to_csv("equity_curve_comparison.csv")

print("\n===== STRATEGY SUMMARY =====")
print("Final Portfolio Value:", portfolio_value)
print("SPY Final Value:", spy_cum.iloc[-1] if not spy_cum.empty else 0)
print("Excess Return:", portfolio_value - spy_cum.iloc[-1] if not spy_cum.empty else 0)
print("Max Drawdown:", max_drawdown)
print("Annual Volatility:", volatility)
print("Sharpe Ratio:", sharpe)
print("Equity Curve CSV:", "equity_curve_comparison.csv")
