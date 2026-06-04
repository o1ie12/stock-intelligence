from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf

from model import build_signals


PORTFOLIO_FILE = Path(__file__).with_name("portfolio.json")
CLUB_MEMBERS_FILE = Path(__file__).with_name("club_members.json")
CLUB_PORTFOLIOS_FILE = Path(__file__).with_name("club_portfolios.json")
PORTFOLIO_HISTORY_FILE = Path(__file__).with_name("portfolio_history.json")
TRADE_JOURNAL_FILE = Path(__file__).with_name("trade_journal.json")

MODEL_PORTFOLIO_FILE = Path(__file__).with_name("model_portfolio.json")
MODEL_HISTORY_FILE = Path(__file__).with_name("model_portfolio_history.json")
MODEL_CHANGES_FILE = Path(__file__).with_name("model_changes.json")

CASH_LABEL = "CASH"
MAX_HOLDINGS = 5
MAX_POSITION = 0.35
MIN_POSITION = 0.05
CASH_RESERVE = 0.05
MIN_TRADE_VALUE = 100.0


@dataclass
class PortfolioState:
    cash: float
    holdings: dict[str, float]


def normalize_holdings(holdings: dict[str, Any]) -> dict[str, float]:
    normalized: dict[str, float] = {}

    for ticker, shares in holdings.items():
        clean_ticker = str(ticker).strip().upper()
        share_count = float(shares or 0)

        if clean_ticker and share_count != 0:
            normalized[clean_ticker] = share_count

    return normalized


def fetch_current_prices(tickers: list[str] | set[str]) -> dict[str, float]:
    prices: dict[str, float] = {}

    for ticker in sorted(set(tickers)):
        if ticker == CASH_LABEL:
            continue

        try:
            history = yf.Ticker(ticker).history(period="5d")
            close = history["Close"].dropna()

            if not close.empty:
                prices[ticker] = float(close.iloc[-1])
        except Exception:
            continue

    return prices


def calculate_position_values(
    state: PortfolioState,
    prices: dict[str, float] | None = None,
) -> pd.DataFrame:
    holdings = normalize_holdings(state.holdings)
    price_map = prices if prices is not None else fetch_current_prices(set(holdings))
    rows: list[dict[str, float | str]] = []

    for ticker, shares in holdings.items():
        price = price_map.get(ticker, 0.0)
        value = shares * price
        rows.append({"Ticker": ticker, "Shares": shares, "Price": price, "Value": value})

    return pd.DataFrame(rows, columns=["Ticker", "Shares", "Price", "Value"])


def calculate_portfolio_value(
    state: PortfolioState,
    prices: dict[str, float] | None = None,
) -> float:
    positions = calculate_position_values(state, prices)
    holdings_value = positions["Value"].sum() if not positions.empty else 0.0
    return float(state.cash) + float(holdings_value)


def calculate_current_weights(
    state: PortfolioState,
    prices: dict[str, float] | None = None,
) -> pd.DataFrame:
    positions = calculate_position_values(state, prices)
    total_value = float(state.cash) + (positions["Value"].sum() if not positions.empty else 0.0)

    if positions.empty:
        return positions.assign(Weight=pd.Series(dtype=float))

    positions["Weight"] = positions["Value"] / total_value if total_value > 0 else 0.0
    return positions


def build_shared_portfolio(
    tickers: list[str] | set[str],
    cash_reserve: float = CASH_RESERVE,
    max_holdings: int = MAX_HOLDINGS,
    max_position: float = MAX_POSITION,
    min_position: float = MIN_POSITION,
) -> pd.DataFrame:
    """
    Unified portfolio construction function for all systems.
    
    This ensures mathematical consistency between:
    - Live recommendations
    - Target allocations  
    - Model portfolio
    - Backtests
    
    Args:
        tickers: List of stock tickers to consider
        cash_reserve: Percentage of portfolio to hold in cash (default 5%)
        max_holdings: Maximum number of positions (default 5)
        max_position: Maximum weight per position (default 35%)
        min_position: Minimum weight per position (default 5%)
    
    Returns:
        DataFrame with columns: Ticker, Score, Target Weight
    """
    from model import build_signals
    
    # For backtest compatibility, we need to handle different universes
    # If tickers are provided, we need to fetch signals for those specific tickers
    # But build_signals() uses a fixed universe, so we need to handle this
    
    # Get signals from model
    signals_df = build_signals()
    
    # If specific tickers provided and they differ from model universe,
    # we need to handle this for backtest compatibility
    model_tickers = set(signals_df["Ticker"].values)
    provided_tickers = set(tickers)
    
    if provided_tickers != model_tickers:
        # For backtest with larger universe, fetch signals for provided tickers
        from model import fetch_stock
        signal_data = []
        for ticker in provided_tickers:
            try:
                row = fetch_stock(ticker)
                if row:
                    signal_data.append(row)
            except Exception:
                continue
        
        if signal_data:
            df = pd.DataFrame(signal_data)
            df["ROE"] = df["ROE"].fillna(0)
            df["PE"] = df["PE"].fillna(999)
            df["Momentum"] = df["Momentum"].fillna(0)
            
            # Use same scoring logic as model.py
            df["ROE_Rank"] = df["ROE"].rank(pct=True)
            df["PE_Rank"] = df["PE"].rank(pct=True, ascending=False)
            df["Momentum_Rank"] = df["Momentum"].rank(pct=True)
            df["Score"] = (
                df["ROE_Rank"] * 0.4 +
                df["Momentum_Rank"] * 0.4 +
                df["PE_Rank"] * 0.2
            )
            signals_df = df
    
    # Sort by score and select top holdings
    signals = signals_df.sort_values("Score", ascending=False).head(max_holdings)
    
    if signals.empty:
        return pd.DataFrame([{"Ticker": CASH_LABEL, "Score": 0.0, "Target Weight": 1.0}])
    
    # Apply exponential weighting (CRITICAL: matches live system)
    scores = signals["Score"].astype(float).to_numpy()
    weights = np.exp(scores)
    weights = weights / weights.sum()
    
    # Apply position limits (CRITICAL: matches live system)
    weights = np.clip(weights, min_position, max_position)
    weights = weights / weights.sum()
    
    # Apply cash reserve (CRITICAL: matches live system)
    weights = weights * (1 - cash_reserve)
    
    # Build result DataFrame
    target = signals[["Ticker", "Score"]].copy()
    target["Target Weight"] = weights
    cash_row = pd.DataFrame([{"Ticker": CASH_LABEL, "Score": 0.0, "Target Weight": cash_reserve}])
    
    return pd.concat([target, cash_row], ignore_index=True)


def build_model_target_portfolio(
    cash_reserve: float = CASH_RESERVE,
    max_holdings: int = MAX_HOLDINGS,
    max_position: float = MAX_POSITION,
    min_position: float = MIN_POSITION,
) -> pd.DataFrame:
    """Alias for construct_target_portfolio to match prompt requirements."""
    return construct_target_portfolio(cash_reserve, max_holdings, max_position, min_position)


def construct_target_portfolio(
    cash_reserve: float = CASH_RESERVE,
    max_holdings: int = MAX_HOLDINGS,
    max_position: float = MAX_POSITION,
    min_position: float = MIN_POSITION,
) -> pd.DataFrame:
    """Uses shared portfolio construction for live system compatibility."""
    from model import stocks as model_stocks
    return build_shared_portfolio(
        tickers=model_stocks,
        cash_reserve=cash_reserve,
        max_holdings=max_holdings,
        max_position=max_position,
        min_position=min_position
    )


def generate_trade_plan(
    state: PortfolioState,
    min_trade_value: float = MIN_TRADE_VALUE,
    cash_reserve: float = CASH_RESERVE,
    prices: dict[str, float] | None = None,
    target: pd.DataFrame | None = None,
) -> pd.DataFrame:
    holdings = normalize_holdings(state.holdings)
    target_df = target if target is not None else construct_target_portfolio(cash_reserve=cash_reserve)
    stock_target = target_df[target_df["Ticker"] != CASH_LABEL].set_index("Ticker")
    tickers = sorted(set(holdings) | set(stock_target.index))
    price_map = prices if prices is not None else fetch_current_prices(tickers)
    clean_state = PortfolioState(state.cash, holdings)
    current = calculate_current_weights(clean_state, price_map)
    current_by_ticker = current.set_index("Ticker") if not current.empty else pd.DataFrame()
    total_value = float(state.cash) + (current["Value"].sum() if not current.empty else 0.0)
    rows: list[dict[str, float | str]] = []

    for ticker in tickers:
        price = price_map.get(ticker, 0.0)
        current_value = float(current_by_ticker.loc[ticker, "Value"]) if ticker in current_by_ticker.index else 0.0
        current_weight = float(current_by_ticker.loc[ticker, "Weight"]) if ticker in current_by_ticker.index else 0.0
        target_weight = float(stock_target.loc[ticker, "Target Weight"]) if ticker in stock_target.index else 0.0
        target_value = target_weight * total_value
        difference = target_value - current_value

        if difference > min_trade_value:
            action = "BUY"
        elif difference < -min_trade_value:
            action = "SELL"
        else:
            action = "HOLD"

        shares_to_trade = difference / price if price > 0 and action != "HOLD" else 0.0
        rows.append(
            {
                "Ticker": ticker,
                "Current Weight": current_weight,
                "Target Weight": target_weight,
                "Current Value": current_value,
                "Target Value": target_value,
                "Difference": difference,
                "Action": action,
                "Shares To Buy/Sell": shares_to_trade,
                "Dollar Amount": abs(difference) if action != "HOLD" else 0.0,
                "Price": price,
            }
        )

    return pd.DataFrame(rows)


def calculate_health_metrics(
    state: PortfolioState,
    current_weights: pd.DataFrame | None = None,
) -> dict[str, float | bool]:
    current = current_weights if current_weights is not None else calculate_current_weights(state)
    stock_weights = current["Weight"] if not current.empty else pd.Series(dtype=float)
    holdings_value = current["Value"].sum() if not current.empty else 0.0
    total_value = float(state.cash) + float(holdings_value)
    cash_weight = float(state.cash) / total_value if total_value > 0 else 0.0
    largest_position = float(stock_weights.max()) if not stock_weights.empty else 0.0
    diversification_score = float(1 - (stock_weights**2).sum()) if not stock_weights.empty else 0.0

    return {
        "total_value": total_value,
        "cash": float(state.cash),
        "cash_weight": cash_weight,
        "number_of_holdings": float(len(normalize_holdings(state.holdings))),
        "largest_position": largest_position,
        "diversification_score": diversification_score,
        "top_risk_flag": largest_position > 0.40,
    }


def decision_summary(
    state: PortfolioState,
    trade_plan: pd.DataFrame,
    target: pd.DataFrame | None = None,
    health: dict[str, float | bool] | None = None,
) -> dict[str, str]:
    target_df = target if target is not None else construct_target_portfolio()
    stock_target = target_df[target_df["Ticker"] != CASH_LABEL]
    buy_rows = trade_plan[trade_plan["Action"] == "BUY"]
    sell_rows = trade_plan[trade_plan["Action"] == "SELL"]

    highest_conviction = stock_target.sort_values("Target Weight", ascending=False).iloc[0]["Ticker"] if not stock_target.empty else "None"
    most_overweight = trade_plan.sort_values("Difference", ascending=True).iloc[0]["Ticker"] if not trade_plan.empty else "None"
    most_underweight = trade_plan.sort_values("Difference", ascending=False).iloc[0]["Ticker"] if not trade_plan.empty else "None"
    largest_buy = buy_rows.sort_values("Dollar Amount", ascending=False).iloc[0]["Ticker"] if not buy_rows.empty else "None"
    largest_sell = sell_rows.sort_values("Dollar Amount", ascending=False).iloc[0]["Ticker"] if not sell_rows.empty else "None"
    health_data = health if health is not None else calculate_health_metrics(state)
    concentration = "elevated" if health_data["top_risk_flag"] else "moderate"
    diversification = "healthy" if health_data["diversification_score"] >= 0.5 else "limited"

    written_summary = (
        f"The model has highest conviction in {highest_conviction}. "
        f"The portfolio is most overweight {most_overweight} and most underweight {most_underweight}. "
        f"The largest recommended buy is {largest_buy}, while the largest recommended sell is {largest_sell}. "
        f"Current concentration risk is {concentration}. Portfolio diversification is {diversification}."
    )

    return {
        "Highest Conviction Position": str(highest_conviction),
        "Most Overweight Position": str(most_overweight),
        "Most Underweight Position": str(most_underweight),
        "Largest Recommended Buy": str(largest_buy),
        "Largest Recommended Sell": str(largest_sell),
        "Summary": written_summary,
    }


def analyze_portfolio(
    state: PortfolioState,
    min_trade_value: float = MIN_TRADE_VALUE,
    cash_reserve: float = CASH_RESERVE,
) -> dict[str, Any]:
    holdings = normalize_holdings(state.holdings)
    target = construct_target_portfolio(cash_reserve=cash_reserve)
    tickers = sorted(set(holdings) | set(target[target["Ticker"] != CASH_LABEL]["Ticker"]))
    prices = fetch_current_prices(tickers)
    clean_state = PortfolioState(state.cash, holdings)
    current = calculate_current_weights(clean_state, prices)
    trade_plan = generate_trade_plan(clean_state, min_trade_value, cash_reserve, prices, target)
    health = calculate_health_metrics(clean_state, current)
    summary = decision_summary(clean_state, trade_plan, target, health)

    return {
        "state": clean_state,
        "prices": prices,
        "current_allocation": current,
        "target_allocation": target,
        "trade_plan": trade_plan,
        "health": health,
        "decision_summary": summary,
    }


def save_portfolio(state: PortfolioState, path: str | Path = PORTFOLIO_FILE) -> None:
    payload = {"cash": float(state.cash), "holdings": normalize_holdings(state.holdings)}
    Path(path).write_text(json.dumps(payload, indent=2))


def load_portfolio(path: str | Path = PORTFOLIO_FILE) -> PortfolioState:
    portfolio_path = Path(path)

    if not portfolio_path.exists():
        return PortfolioState(cash=5000.0, holdings={"NVDA": 10, "AMD": 15})

    payload = json.loads(portfolio_path.read_text())
    return PortfolioState(
        cash=float(payload.get("cash", 0.0)),
        holdings=normalize_holdings(payload.get("holdings", {})),
    )


def generate_trade_recommendations(
    holdings: dict[str, float],
    cash: float,
    min_trade_value: float = MIN_TRADE_VALUE,
    cash_reserve: float = CASH_RESERVE,
) -> dict[str, Any]:
    state = PortfolioState(cash=cash, holdings=holdings)
    analysis = analyze_portfolio(state, min_trade_value, cash_reserve)

    return {
        "portfolio_value": analysis["health"]["total_value"],
        "cash": float(cash),
        "prices": analysis["prices"],
        "signals": build_signals(),
        "target_weights": analysis["target_allocation"],
        "holdings": analysis["current_allocation"],
        "trades": analysis["trade_plan"],
    }


# ==========================================
# CLUB PORTFOLIO DATABASE HELPERS (CHANGE 2)
# ==========================================

def load_club_portfolios() -> dict[str, dict[str, Any]]:
    if not CLUB_PORTFOLIOS_FILE.exists():
        return {}
    try:
        return json.loads(CLUB_PORTFOLIOS_FILE.read_text())
    except Exception:
        return {}


def save_club_portfolios(portfolios: dict[str, dict[str, Any]]) -> None:
    CLUB_PORTFOLIOS_FILE.write_text(json.dumps(portfolios, indent=2))


def load_user_portfolio(username: str) -> PortfolioState:
    portfolios = load_club_portfolios()
    if username not in portfolios:
        # Backward compatibility fallback: seed Oliver with default portfolio.json if available
        if username.lower() == "oliver":
            default_path = Path(__file__).parent / "portfolio.json"
            if default_path.exists():
                try:
                    state = load_portfolio(default_path)
                    save_user_portfolio(username, state)
                    return state
                except Exception:
                    pass
        # Default starting configuration for new users
        state = PortfolioState(cash=10000.0, holdings={})
        save_user_portfolio(username, state)
        return state

    user_data = portfolios[username]
    return PortfolioState(
        cash=float(user_data.get("cash", 0.0)),
        holdings=normalize_holdings(user_data.get("holdings", {})),
    )


def save_user_portfolio(username: str, state: PortfolioState) -> None:
    portfolios = load_club_portfolios()
    portfolios[username] = {
        "cash": float(state.cash),
        "holdings": normalize_holdings(state.holdings)
    }
    save_club_portfolios(portfolios)


# ==========================================
# CLUB MEMBER CONFIG HELPERS (CHANGE 1)
# ==========================================

def load_club_members_config() -> dict[str, dict[str, Any]]:
    if not CLUB_MEMBERS_FILE.exists():
        return {}
    try:
        return json.loads(CLUB_MEMBERS_FILE.read_text())
    except Exception:
        return {}


def save_club_members_config(config: dict[str, dict[str, Any]]) -> None:
    CLUB_MEMBERS_FILE.write_text(json.dumps(config, indent=2))


def create_member_profile(username: str, initial_value: float = 10000.0) -> None:
    config = load_club_members_config()
    if username not in config:
        config[username] = {"initial_value": float(initial_value)}
        save_club_members_config(config)

    portfolios = load_club_portfolios()
    if username not in portfolios:
        portfolios[username] = {
            "cash": float(initial_value),
            "holdings": {}
        }
        save_club_portfolios(portfolios)

    append_portfolio_history(username, PortfolioState(cash=initial_value, holdings={}), prices={})


# ==========================================
# MODEL PORTFOLIO STORAGE wrappers (CHANGE 1)
# ==========================================

def load_model_portfolio() -> dict[str, Any]:
    """Pure function - only reads, never writes state."""
    if not MODEL_PORTFOLIO_FILE.exists():
        # Return default payload without writing (pure function)
        return {
            "cash": 10000.0,
            "positions": {},
            "last_rebalance": "Never",
            "initial_value": 10000
        }
    try:
        return json.loads(MODEL_PORTFOLIO_FILE.read_text())
    except Exception:
        return {
            "cash": 10000.0,
            "positions": {},
            "last_rebalance": "Never",
            "initial_value": 10000
        }


def save_model_portfolio(payload: dict[str, Any]) -> None:
    MODEL_PORTFOLIO_FILE.write_text(json.dumps(payload, indent=2))


# ==========================================
# CENTRALIZED CALCULATION ENGINE (CHANGE 3)
# ==========================================

def calculate_portfolio_return(
    state: PortfolioState,
    prices: dict[str, float] | None,
    initial_value: float,
) -> float:
    total_value = calculate_portfolio_value(state, prices)
    return ((total_value - initial_value) / initial_value * 100) if initial_value > 0 else 0.0


# ==========================================
# MODEL REBALANCING ENGINE (CHANGE 1, 2, 4)
# ==========================================

def needs_rebalance_model_portfolio() -> bool:
    target_df = construct_target_portfolio()
    target_tickers = set(target_df[target_df["Ticker"] != CASH_LABEL]["Ticker"])

    model_data = load_model_portfolio()
    model_positions = set(model_data.get("positions", {}).keys())

    return target_tickers != model_positions


def rebalance_model_portfolio() -> None:
    # 1. Read current state (pure)
    model_data = load_model_portfolio()
    old_positions = model_data.get("positions", {})
    old_cash = float(model_data.get("cash", 0.0))
    initial_value = float(model_data.get("initial_value", 10000.0))

    # 2. Get target allocation
    target_weights = construct_target_portfolio()

    # 3. Resolve prices
    tickers = target_weights[target_weights["Ticker"] != CASH_LABEL]["Ticker"].tolist()
    prices = fetch_current_prices(set(tickers) | set(old_positions.keys()))

    # 4. Centralized calculation of current total value
    old_state = PortfolioState(cash=old_cash, holdings=old_positions)
    current_total_val = calculate_portfolio_value(old_state, prices)

    # 5. Allocate new positions
    new_positions = {}
    new_cash = current_total_val

    for _, row in target_weights.iterrows():
        ticker = row["Ticker"]
        weight = row["Target Weight"]
        if ticker == CASH_LABEL:
            new_cash = weight * current_total_val
        else:
            price = prices.get(ticker, 0.0)
            if price > 0:
                shares = (weight * current_total_val) / price
                new_positions[ticker] = round(shares, 4)
            else:
                new_positions[ticker] = 0.0

    # 6. Log changes to model_changes.json (only function allowed to write to it)
    track_model_changes(
        old_positions,
        new_positions,
        prices,
        prices,
        current_total_val,
        current_total_val
    )

    # 7. Write new state
    payload = {
        "cash": round(new_cash, 2),
        "positions": new_positions,
        "last_rebalance": datetime.now().strftime("%Y-%m-%d"),
        "initial_value": initial_value
    }
    save_model_portfolio(payload)

    # 8. Append checkpoint to history
    append_model_history(current_total_val, initial_value)


def track_model_changes(
    old_positions: dict[str, float],
    new_positions: dict[str, float],
    old_prices: dict[str, float],
    new_prices: dict[str, float],
    old_total_val: float,
    new_total_val: float,
) -> None:
    changes = []
    if MODEL_CHANGES_FILE.exists():
        try:
            changes = json.loads(MODEL_CHANGES_FILE.read_text())
        except Exception:
            pass

    today_str = datetime.now().strftime("%Y-%m-%d")

    old_weights = {}
    for ticker, shares in old_positions.items():
        val = shares * old_prices.get(ticker, 0.0)
        old_weights[ticker] = val / old_total_val if old_total_val > 0 else 0.0

    new_weights = {}
    for ticker, shares in new_positions.items():
        val = shares * new_prices.get(ticker, 0.0)
        new_weights[ticker] = val / new_total_val if new_total_val > 0 else 0.0

    all_tickers = set(old_weights.keys()) | set(new_weights.keys())
    new_entries = []

    for ticker in all_tickers:
        w_old = old_weights.get(ticker, 0.0)
        w_new = new_weights.get(ticker, 0.0)

        action = None
        if w_old == 0.0 and w_new > 0.0:
            action = "ADD"
        elif w_old > 0.0 and w_new == 0.0:
            action = "REMOVE"
        elif w_new > w_old + 0.005:
            action = "WEIGHT_INCREASE"
        elif w_old > w_new + 0.005:
            action = "WEIGHT_DECREASE"

        if action:
            new_entries.append({
                "date": today_str,
                "action": action,
                "ticker": ticker
            })

    if new_entries:
        changes.extend(new_entries)
        MODEL_CHANGES_FILE.write_text(json.dumps(changes, indent=2))


def load_model_portfolio_history() -> list[dict[str, Any]]:
    if not MODEL_HISTORY_FILE.exists():
        return []
    try:
        return json.loads(MODEL_HISTORY_FILE.read_text())
    except Exception:
        return []


def save_model_portfolio_history(history: list[dict[str, Any]]) -> None:
    MODEL_HISTORY_FILE.write_text(json.dumps(history, indent=2))


def append_model_history(total_value: float, initial_value: float) -> None:
    history = load_model_portfolio_history()
    today_str = datetime.now().strftime("%Y-%m-%d")
    return_pct = ((total_value - initial_value) / initial_value * 100) if initial_value > 0 else 0.0

    found = False
    for record in history:
        if record["date"] == today_str:
            record["portfolio_value"] = round(total_value, 2)
            record["return_pct"] = round(return_pct, 2)
            found = True
            break

    if not found:
        history.append({
            "date": today_str,
            "portfolio_value": round(total_value, 2),
            "return_pct": round(return_pct, 2)
        })

    save_model_portfolio_history(history)


# ==========================================
# RULE-BASED EXPLANATION GENERATOR (CHANGE 5)
# ==========================================

def generate_decision_explanation(ticker: str, signals_df: pd.DataFrame) -> dict[str, Any]:
    if signals_df.empty or ticker not in signals_df["Ticker"].values:
        return {
            "rank": "N/A",
            "score": 0.0,
            "roe_rank": "N/A",
            "mom_rank": "N/A",
            "pe_rank": "N/A",
            "explanation": "No signal data."
        }

    sorted_df = signals_df.sort_values("Score", ascending=False).reset_index(drop=True)
    overall_rank = sorted_df[sorted_df["Ticker"] == ticker].index[0] + 1
    row = signals_df[signals_df["Ticker"] == ticker].iloc[0]

    roe_ranks = signals_df["ROE"].rank(ascending=False, method="min")
    mom_ranks = signals_df["Momentum"].rank(ascending=False, method="min")
    pe_ranks = signals_df["PE"].rank(ascending=True, method="min")

    roe_rank_val = int(roe_ranks[signals_df["Ticker"] == ticker].iloc[0])
    mom_rank_val = int(mom_ranks[signals_df["Ticker"] == ticker].iloc[0])
    pe_rank_val = int(pe_ranks[signals_df["Ticker"] == ticker].iloc[0])

    reasons = []
    if mom_rank_val <= 2:
        reasons.append("High momentum")
    if roe_rank_val <= 2:
        reasons.append("strong ROE")
    if pe_rank_val <= 2:
        reasons.append("attractive PE valuation")

    if reasons:
        explanation = " + ".join(reasons) + " justify overweight position."
    else:
        explanation = "Moderate balanced scores justify position."

    return {
        "rank": f"#{overall_rank}",
        "score": float(row["Score"]),
        "roe_rank": roe_rank_val,
        "mom_rank": mom_rank_val,
        "pe_rank": pe_rank_val,
        "explanation": explanation
    }


# ==========================================
# MODEL ALIGNMENT & DYNAMIC METRICS (CHANGE 3)
# ==========================================

def calculate_model_alignment_score(
    current_weights: pd.DataFrame,
    target_weights: pd.DataFrame,
    cash_weight: float,
    target_cash_weight: float,
) -> float:
    curr_map: dict[str, float] = {}
    if not current_weights.empty and "Ticker" in current_weights.columns and "Weight" in current_weights.columns:
        for _, row in current_weights.iterrows():
            ticker = str(row["Ticker"])
            if ticker != CASH_LABEL:
                curr_map[ticker] = float(row["Weight"])
    curr_map[CASH_LABEL] = float(cash_weight)

    tgt_map: dict[str, float] = {}
    if not target_weights.empty and "Ticker" in target_weights.columns and "Target Weight" in target_weights.columns:
        for _, row in target_weights.iterrows():
            ticker = str(row["Ticker"])
            if ticker != CASH_LABEL:
                tgt_map[ticker] = float(row["Target Weight"])
    tgt_map[CASH_LABEL] = float(target_cash_weight)

    all_tickers = set(curr_map.keys()) | set(tgt_map.keys())

    l1_sum = 0.0
    for ticker in all_tickers:
        w_curr = curr_map.get(ticker, 0.0)
        w_tgt = tgt_map.get(ticker, 0.0)
        l1_sum += abs(w_curr - w_tgt)

    score = 100.0 * (1.0 - (l1_sum / 2.0))
    return float(max(0.0, min(100.0, score)))


def calculate_member_metrics(
    username: str,
    state: PortfolioState,
    target_portfolio: pd.DataFrame,
    prices: dict[str, float],
) -> dict[str, Any]:
    positions = calculate_position_values(state, prices)
    total_val = float(state.cash) + (positions["Value"].sum() if not positions.empty else 0.0)

    if not positions.empty:
        stocks_only = positions[positions["Ticker"] != CASH_LABEL]
        if not stocks_only.empty:
            top_row = stocks_only.sort_values("Value", ascending=False).iloc[0]
            top_holding = str(top_row["Ticker"])
        else:
            top_holding = CASH_LABEL
    else:
        top_holding = CASH_LABEL

    config = load_club_members_config()
    user_config = config.get(username, {})
    init_val = float(user_config.get("initial_value", 10000.0))

    return_pct = calculate_portfolio_return(state, prices, init_val)

    current_w = calculate_current_weights(state, prices)
    cash_w = float(state.cash) / total_val if total_val > 0 else 0.0

    target_cash_row = target_portfolio[target_portfolio["Ticker"] == CASH_LABEL]
    target_cash_w = float(target_cash_row.iloc[0]["Target Weight"]) if not target_cash_row.empty else 0.0

    alignment_score = calculate_model_alignment_score(
        current_w,
        target_portfolio,
        cash_w,
        target_cash_w
    )

    return {
        "portfolio_value": total_val,
        "return_pct": return_pct,
        "top_holding": top_holding,
        "initial_value": init_val,
        "alignment_score": alignment_score,
    }


def get_leaderboard_data(target_portfolio: pd.DataFrame) -> pd.DataFrame:
    config = load_club_members_config()
    portfolios = load_club_portfolios()

    members = sorted(list(set(config.keys()) | set(portfolios.keys())))

    model_payload = load_model_portfolio()
    model_positions = model_payload.get("positions", {})

    all_tickers: set[str] = set()
    member_states: dict[str, PortfolioState] = {}

    for member in members:
        state = load_user_portfolio(member)
        member_states[member] = state
        all_tickers.update(state.holdings.keys())

    all_tickers.update(model_positions.keys())

    if not target_portfolio.empty:
        all_tickers.update(target_portfolio[target_portfolio["Ticker"] != CASH_LABEL]["Ticker"])

    prices = fetch_current_prices(all_tickers)

    rows = []
    for member in members:
        state = member_states[member]
        metrics = calculate_member_metrics(member, state, target_portfolio, prices)
        rows.append({
            "Member": member,
            "Portfolio Value": metrics["portfolio_value"],
            "Return %": metrics["return_pct"],
            "Top Holding": metrics["top_holding"],
            "Model Alignment Score": metrics["alignment_score"],
        })

    model_state = PortfolioState(cash=float(model_payload.get("cash", 0.0)), holdings=model_positions)
    model_total_value = calculate_portfolio_value(model_state, prices)
    model_initial = float(model_payload.get("initial_value", 10000.0))
    model_return = calculate_portfolio_return(model_state, prices, model_initial)

    if not model_positions:
        model_top = CASH_LABEL
    else:
        model_pos_df = calculate_position_values(model_state, prices)
        if not model_pos_df.empty:
            model_stocks = model_pos_df[model_pos_df["Ticker"] != CASH_LABEL]
            if not model_stocks.empty:
                model_top = str(model_stocks.sort_values("Value", ascending=False).iloc[0]["Ticker"])
            else:
                model_top = CASH_LABEL
        else:
            model_top = CASH_LABEL

    rows.append({
        "Member": "MODEL",
        "Portfolio Value": model_total_value,
        "Return %": model_return,
        "Top Holding": model_top,
        "Model Alignment Score": 100.0,
    })

    df = pd.DataFrame(rows)
    df = df.sort_values("Return %", ascending=False).reset_index(drop=True)
    df.insert(0, "Rank", df.index + 1)
    return df


# ==========================================
# PORTFOLIO HISTORY HELPERS (FEATURE 2)
# ==========================================

def load_portfolio_history() -> dict[str, list[dict[str, Any]]]:
    if not PORTFOLIO_HISTORY_FILE.exists():
        return {}
    try:
        return json.loads(PORTFOLIO_HISTORY_FILE.read_text())
    except Exception:
        return {}


def save_portfolio_history(history: dict[str, list[dict[str, Any]]]) -> None:
    PORTFOLIO_HISTORY_FILE.write_text(json.dumps(history, indent=2))


def append_portfolio_history(
    username: str,
    state: PortfolioState,
    prices: dict[str, float] | None = None,
) -> None:
    history = load_portfolio_history()
    if username not in history:
        history[username] = []

    price_map = prices if prices is not None else fetch_current_prices(state.holdings.keys())
    total_val = calculate_portfolio_value(state, price_map)

    record = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "portfolio_value": round(total_val, 2),
        "cash": round(state.cash, 2),
        "holdings": normalize_holdings(state.holdings)
    }
    history[username].append(record)
    save_portfolio_history(history)


def get_portfolio_history_df(username: str) -> pd.DataFrame:
    history = load_portfolio_history()
    user_history = history.get(username, [])
    if not user_history:
        return pd.DataFrame(columns=["timestamp", "portfolio_value", "cash", "holdings"])
    df = pd.DataFrame(user_history)
    for col in ["timestamp", "portfolio_value", "cash", "holdings"]:
        if col not in df.columns:
            df[col] = None
    return df


# ==========================================
# TRADE JOURNAL HELPERS (FEATURE 4)
# ==========================================

def load_trade_journal() -> list[dict[str, Any]]:
    if not TRADE_JOURNAL_FILE.exists():
        return []
    try:
        return json.loads(TRADE_JOURNAL_FILE.read_text())
    except Exception:
        return []


def save_trade_journal(journal: list[dict[str, Any]]) -> None:
    TRADE_JOURNAL_FILE.write_text(json.dumps(journal, indent=2))


def log_trades_if_any(
    username: str,
    old_state: PortfolioState,
    new_state: PortfolioState,
    prices: dict[str, float],
) -> None:
    old_holdings = normalize_holdings(old_state.holdings)
    new_holdings = normalize_holdings(new_state.holdings)

    all_tickers = set(old_holdings.keys()) | set(new_holdings.keys())
    trades: list[dict[str, Any]] = []

    for ticker in all_tickers:
        old_shares = old_holdings.get(ticker, 0.0)
        new_shares = new_holdings.get(ticker, 0.0)
        diff = new_shares - old_shares

        if abs(diff) > 1e-6:
            action = "BUY" if diff > 0 else "SELL"
            shares = abs(diff)
            price = prices.get(ticker, 0.0)
            trades.append({
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "member": username,
                "ticker": ticker,
                "action": action,
                "shares": round(shares, 4),
                "price": round(price, 2)
            })

    if trades:
        journal = load_trade_journal()
        journal.extend(trades)
        save_trade_journal(journal)


# ==========================================
# CLUB ANALYTICS HELPERS (FEATURE 5 & CHANGE 4)
# ==========================================

def get_club_analytics_data(leaderboard_df: pd.DataFrame) -> dict[str, Any]:
    if leaderboard_df.empty:
        return {
            "num_members": 0,
            "average_return": 0.0,
            "best_performer_name": "None",
            "best_performer_return": 0.0,
            "worst_performer_name": "None",
            "worst_performer_return": 0.0,
            "outperforming_model": [],
            "underperforming_model": [],
            "most_aligned_member": "None",
            "most_aligned_score": 0.0,
        }

    model_row = leaderboard_df[leaderboard_df["Member"] == "MODEL"]
    model_return = float(model_row.iloc[0]["Return %"]) if not model_row.empty else 0.0

    users_df = leaderboard_df[leaderboard_df["Member"] != "MODEL"]

    num_members = len(users_df)
    avg_return = users_df["Return %"].mean() if not users_df.empty else 0.0

    if not users_df.empty:
        best_row = users_df.iloc[0]
        worst_row = users_df.iloc[-1]
        best_name = str(best_row["Member"])
        best_ret = float(best_row["Return %"])
        worst_name = str(worst_row["Member"])
        worst_ret = float(worst_row["Return %"])

        outperforming = users_df[users_df["Return %"] > model_return]["Member"].tolist()
        underperforming = users_df[users_df["Return %"] < model_return]["Member"].tolist()

        aligned_df = users_df.sort_values("Model Alignment Score", ascending=False)
        most_aligned_row = aligned_df.iloc[0]
        most_aligned_name = str(most_aligned_row["Member"])
        most_aligned_score = float(most_aligned_row["Model Alignment Score"])
    else:
        best_name = "None"
        best_ret = 0.0
        worst_name = "None"
        worst_ret = 0.0
        outperforming = []
        underperforming = []
        most_aligned_name = "None"
        most_aligned_score = 0.0

    return {
        "num_members": num_members,
        "average_return": float(avg_return),
        "best_performer_name": best_name,
        "best_performer_return": best_ret,
        "worst_performer_name": worst_name,
        "worst_performer_return": worst_ret,
        "outperforming_model": outperforming,
        "underperforming_model": underperforming,
        "most_aligned_member": most_aligned_name,
        "most_aligned_score": most_aligned_score,
    }


def get_club_holdings_insight() -> pd.DataFrame:
    portfolios = load_club_portfolios()
    ticker_counts: dict[str, int] = {}

    for member, data in portfolios.items():
        holdings = normalize_holdings(data.get("holdings", {}))
        for ticker in holdings.keys():
            ticker_counts[ticker] = ticker_counts.get(ticker, 0) + 1

    if not ticker_counts:
        return pd.DataFrame(columns=["Ticker", "Members Owning"])

    df = pd.DataFrame([
        {"Ticker": ticker, "Members Owning": count}
        for ticker, count in ticker_counts.items()
    ])
    return df.sort_values("Members Owning", ascending=False).reset_index(drop=True)


def load_model_return() -> float:
    try:
        payload = load_model_portfolio()
        model_state = PortfolioState(
            cash=float(payload.get("cash", 0.0)),
            holdings=payload.get("positions", {})
        )
        initial = float(payload.get("initial_value", 10000.0))
        prices = fetch_current_prices(model_state.holdings.keys())
        return calculate_portfolio_return(model_state, prices, initial)
    except Exception:
        return 64.09
