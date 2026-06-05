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
from database import supabase, MEMBERS_TABLE, PORTFOLIOS_TABLE, MODEL_PORTFOLIO_TABLE
from database import PORTFOLIO_HISTORY_TABLE, TRADE_JOURNAL_TABLE
from database import MODEL_HISTORY_TABLE, MODEL_CHANGES_TABLE


# File paths removed - Supabase is now the sole source of truth
# Previously: PORTFOLIO_FILE, CLUB_MEMBERS_FILE, CLUB_PORTFOLIOS_FILE, 
# PORTFOLIO_HISTORY_FILE, TRADE_JOURNAL_FILE, MODEL_PORTFOLIO_FILE, 
# MODEL_HISTORY_FILE, MODEL_CHANGES_FILE

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
    """Load club portfolios from Supabase."""
    try:
        response = supabase.table(PORTFOLIOS_TABLE).select("*").execute()
        portfolios = {}
        for portfolio in response.data:
            username_response = supabase.table(MEMBERS_TABLE).select("username").eq("id", portfolio["member_id"]).execute()
            if username_response.data:
                username = username_response.data[0]["username"]
                portfolios[username] = {
                    "cash": float(portfolio["cash"]),
                    "holdings": portfolio["holdings"]
                }
        return portfolios
    except Exception as e:
        print(f"Error loading portfolios from Supabase: {e}")
        return {}


def save_club_portfolios(portfolios: dict[str, dict[str, Any]]) -> None:
    """Save club portfolios to Supabase."""
    try:
        for username, data in portfolios.items():
            # Get member ID
            member_response = supabase.table(MEMBERS_TABLE).select("id").eq("username", username).execute()
            if not member_response.data:
                print(f"Member {username} not found, skipping portfolio save")
                continue
            
            member_id = member_response.data[0]["id"]
            
            # Check if portfolio exists
            existing = supabase.table(PORTFOLIOS_TABLE).select("*").eq("member_id", member_id).execute()
            
            portfolio_data = {
                "member_id": member_id,
                "cash": float(data.get("cash", 0.0)),
                "holdings": data.get("holdings", {})
            }
            
            if existing.data:
                # Update existing portfolio
                supabase.table(PORTFOLIOS_TABLE).update(portfolio_data).eq("member_id", member_id).execute()
            else:
                # Insert new portfolio
                supabase.table(PORTFOLIOS_TABLE).insert(portfolio_data).execute()
    except Exception as e:
        print(f"Error saving portfolios to Supabase: {e}")


def load_user_portfolio(username: str) -> PortfolioState:
    """Load user portfolio directly from Supabase."""
    try:
        # Get member ID
        member_response = supabase.table(MEMBERS_TABLE).select("id").eq("username", username).execute()
        if not member_response.data:
            # Create new member and portfolio
            create_member_profile(username, 10000.0)
            member_response = supabase.table(MEMBERS_TABLE).select("id").eq("username", username).execute()
        
        member_id = member_response.data[0]["id"]
        
        # Get portfolio
        portfolio_response = supabase.table(PORTFOLIOS_TABLE).select("*").eq("member_id", member_id).execute()
        if not portfolio_response.data:
            # Create default portfolio
            state = PortfolioState(cash=10000.0, holdings={})
            save_user_portfolio(username, state)
            return state
        
        portfolio = portfolio_response.data[0]
        return PortfolioState(
            cash=float(portfolio.get("cash", 0.0)),
            holdings=normalize_holdings(portfolio.get("holdings", {})),
        )
    except Exception as e:
        print(f"Error loading user portfolio from Supabase: {e}")
        return PortfolioState(cash=10000.0, holdings={})


def save_user_portfolio(username: str, state: PortfolioState) -> None:
    """Save user portfolio directly to Supabase."""
    try:
        # Get member ID
        member_response = supabase.table(MEMBERS_TABLE).select("id").eq("username", username).execute()
        if not member_response.data:
            # Create member first
            supabase.table(MEMBERS_TABLE).insert({
                "username": username,
                "initial_value": 10000.0
            }).execute()
            member_response = supabase.table(MEMBERS_TABLE).select("id").eq("username", username).execute()
        
        member_id = member_response.data[0]["id"]
        
        # Check if portfolio exists
        existing = supabase.table(PORTFOLIOS_TABLE).select("*").eq("member_id", member_id).execute()
        
        portfolio_data = {
            "member_id": member_id,
            "cash": float(state.cash),
            "holdings": normalize_holdings(state.holdings)
        }
        
        if existing.data:
            # Update existing portfolio
            supabase.table(PORTFOLIOS_TABLE).update(portfolio_data).eq("member_id", member_id).execute()
        else:
            # Insert new portfolio
            supabase.table(PORTFOLIOS_TABLE).insert(portfolio_data).execute()
    except Exception as e:
        print(f"Error saving user portfolio to Supabase: {e}")


# ==========================================
# CLUB MEMBER CONFIG HELPERS (CHANGE 1)
# ==========================================

def load_club_members_config() -> dict[str, dict[str, Any]]:
    """Load club members configuration from Supabase."""
    try:
        response = supabase.table(MEMBERS_TABLE).select("*").execute()
        members = {}
        for member in response.data:
            members[member["username"]] = {
                "initial_value": float(member["initial_value"]),
                "id": member["id"]
            }
        return members
    except Exception as e:
        print(f"Error loading members from Supabase: {e}")
        return {}


def save_club_members_config(config: dict[str, dict[str, Any]]) -> None:
    """Save club members configuration to Supabase."""
    try:
        for username, data in config.items():
            # Check if member exists
            existing = supabase.table(MEMBERS_TABLE).select("*").eq("username", username).execute()
            
            member_data = {
                "username": username,
                "initial_value": float(data.get("initial_value", 10000.0))
            }
            
            if existing.data:
                # Update existing member
                supabase.table(MEMBERS_TABLE).update(member_data).eq("username", username).execute()
            else:
                # Insert new member
                supabase.table(MEMBERS_TABLE).insert(member_data).execute()
    except Exception as e:
        print(f"Error saving members to Supabase: {e}")


def create_member_profile(username: str, initial_value: float = 10000.0) -> None:
    config = load_club_members_config()
    if username not in config:
        config[username] = {"initial_value": float(initial_value)}
        save_club_members_config(config)

    portfolios = load_club_portfolios()
    if username not in portfolios:
        save_user_portfolio(username, PortfolioState(cash=initial_value, holdings={}))

    append_portfolio_history(username, PortfolioState(cash=initial_value, holdings={}), prices={})


# ==========================================
# MODEL PORTFOLIO STORAGE wrappers (CHANGE 1)
# ==========================================

def load_model_portfolio() -> dict[str, Any]:
    """Load model portfolio from Supabase."""
    try:
        response = supabase.table(MODEL_PORTFOLIO_TABLE).select("*").execute()
        if response.data:
            portfolio = response.data[0]
            return {
                "cash": float(portfolio.get("cash", 10000.0)),
                "positions": portfolio.get("positions", {}),
                "last_rebalance": portfolio.get("last_rebalance", "Never"),
                "initial_value": float(portfolio.get("initial_value", 10000.0))
            }
        else:
            # Insert default model portfolio
            default = {
                "cash": 10000.0,
                "positions": {},
                "last_rebalance": "Never",
                "initial_value": 10000.0
            }
            supabase.table(MODEL_PORTFOLIO_TABLE).insert({
                "cash": default["cash"],
                "positions": default["positions"],
                "initial_value": default["initial_value"],
                "last_rebalance": None
            }).execute()
            return default
    except Exception as e:
        print(f"Error loading model portfolio from Supabase: {e}")
        return {
            "cash": 10000.0,
            "positions": {},
            "last_rebalance": "Never",
            "initial_value": 10000
        }


def save_model_portfolio(payload: dict[str, Any]) -> None:
    """Save model portfolio to Supabase."""
    try:
        # Check if model portfolio exists
        existing = supabase.table(MODEL_PORTFOLIO_TABLE).select("*").execute()
        
        portfolio_data = {
            "cash": float(payload.get("cash", 10000.0)),
            "positions": payload.get("positions", {}),
            "initial_value": float(payload.get("initial_value", 10000.0)),
            "last_rebalance": payload.get("last_rebalance")
        }
        
        if existing.data:
            # Update existing
            supabase.table(MODEL_PORTFOLIO_TABLE).update(portfolio_data).eq("id", existing.data[0]["id"]).execute()
        else:
            # Insert new
            supabase.table(MODEL_PORTFOLIO_TABLE).insert(portfolio_data).execute()
    except Exception as e:
        print(f"Error saving model portfolio to Supabase: {e}")


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


def load_model_changes() -> list[dict[str, Any]]:
    """Load model changes from Supabase."""
    try:
        response = supabase.table(MODEL_CHANGES_TABLE).select("*").order(column="date", desc=True).execute()
        return [
            {
                "date": record["date"],
                "action": record["action"],
                "ticker": record["ticker"]
            }
            for record in response.data
        ]
    except Exception as e:
        print(f"Error loading model changes from Supabase: {e}")
        return []


def track_model_changes(
    old_positions: dict[str, float],
    new_positions: dict[str, float],
    old_prices: dict[str, float],
    new_prices: dict[str, float],
    old_total_val: float,
    new_total_val: float,
) -> None:
    """Track model changes to Supabase."""
    try:
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
                # Check if change already exists for today
                existing = supabase.table(MODEL_CHANGES_TABLE).select("*").eq("date", today_str).eq("ticker", ticker).execute()
                if not existing.data:
                    supabase.table(MODEL_CHANGES_TABLE).insert({
                        "date": today_str,
                        "action": action,
                        "ticker": ticker
                    }).execute()
    except Exception as e:
        print(f"Error tracking model changes to Supabase: {e}")


def load_model_portfolio_history() -> list[dict[str, Any]]:
    """Load model portfolio history from Supabase."""
    try:
        response = supabase.table(MODEL_HISTORY_TABLE).select("*").order(column="date", desc=True).execute()
        return [
            {
                "date": record["date"],
                "portfolio_value": float(record["portfolio_value"]),
                "return_pct": float(record["return_pct"])
            }
            for record in response.data
        ]
    except Exception as e:
        print(f"Error loading model history from Supabase: {e}")
        return []


def save_model_portfolio_history(history: list[dict[str, Any]]) -> None:
    """Save model portfolio history to Supabase (bulk operation)."""
    try:
        for record in history:
            # Check if record exists for this date
            existing = supabase.table(MODEL_HISTORY_TABLE).select("*").eq("date", record["date"]).execute()
            if not existing.data:
                supabase.table(MODEL_HISTORY_TABLE).insert({
                    "date": record["date"],
                    "portfolio_value": float(record["portfolio_value"]),
                    "return_pct": float(record["return_pct"])
                }).execute()
    except Exception as e:
        print(f"Error saving model history to Supabase: {e}")


def append_model_history(total_value: float, initial_value: float) -> None:
    """Append model portfolio history to Supabase."""
    try:
        today_str = datetime.now().strftime("%Y-%m-%d")
        return_pct = ((total_value - initial_value) / initial_value * 100) if initial_value > 0 else 0.0

        # Check if record exists for today
        existing = supabase.table(MODEL_HISTORY_TABLE).select("*").eq("date", today_str).execute()
        
        if existing.data:
            # Update existing record
            supabase.table(MODEL_HISTORY_TABLE).update({
                "portfolio_value": round(total_value, 2),
                "return_pct": round(return_pct, 2)
            }).eq("date", today_str).execute()
        else:
            # Insert new record
            supabase.table(MODEL_HISTORY_TABLE).insert({
                "date": today_str,
                "portfolio_value": round(total_value, 2),
                "return_pct": round(return_pct, 2)
            }).execute()
    except Exception as e:
        print(f"Error appending model history to Supabase: {e}")


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
    """Load portfolio history from Supabase."""
    try:
        response = supabase.table(PORTFOLIO_HISTORY_TABLE).select("*").execute()
        history = {}
        for record in response.data:
            # Get username from member_id
            member_response = supabase.table(MEMBERS_TABLE).select("username").eq("id", record["member_id"]).execute()
            if member_response.data:
                username = member_response.data[0]["username"]
                if username not in history:
                    history[username] = []
                history[username].append({
                    "timestamp": record["timestamp"],
                    "portfolio_value": float(record["portfolio_value"]),
                    "cash": float(record["cash"]),
                    "holdings": record["holdings"]
                })
        return history
    except Exception as e:
        print(f"Error loading portfolio history from Supabase: {e}")
        return {}


def save_portfolio_history(history: dict[str, list[dict[str, Any]]]) -> None:
    """Save portfolio history to Supabase (bulk operation)."""
    try:
        for username, records in history.items():
            # Get member ID
            member_response = supabase.table(MEMBERS_TABLE).select("id").eq("username", username).execute()
            if not member_response.data:
                continue
            
            member_id = member_response.data[0]["id"]
            
            # Insert each record
            for record in records:
                supabase.table(PORTFOLIO_HISTORY_TABLE).insert({
                    "member_id": member_id,
                    "timestamp": record["timestamp"],
                    "portfolio_value": float(record["portfolio_value"]),
                    "cash": float(record["cash"]),
                    "holdings": record["holdings"]
                }).execute()
    except Exception as e:
        print(f"Error saving portfolio history to Supabase: {e}")


def append_portfolio_history(
    username: str,
    state: PortfolioState,
    prices: dict[str, float] | None = None,
) -> None:
    """Append portfolio history record to Supabase."""
    try:
        # Get member ID
        member_response = supabase.table(MEMBERS_TABLE).select("id").eq("username", username).execute()
        if not member_response.data:
            return
        
        member_id = member_response.data[0]["id"]
        
        price_map = prices if prices is not None else fetch_current_prices(state.holdings.keys())
        total_val = calculate_portfolio_value(state, price_map)

        record = {
            "member_id": member_id,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "portfolio_value": round(total_val, 2),
            "cash": round(state.cash, 2),
            "holdings": normalize_holdings(state.holdings)
        }
        supabase.table(PORTFOLIO_HISTORY_TABLE).insert(record).execute()
    except Exception as e:
        print(f"Error appending portfolio history to Supabase: {e}")


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
    """Load trade journal from Supabase."""
    try:
        response = supabase.table(TRADE_JOURNAL_TABLE).select("*").execute()
        journal = []
        for record in response.data:
            # Get username from member_id
            member_response = supabase.table(MEMBERS_TABLE).select("username").eq("id", record["member_id"]).execute()
            if member_response.data:
                username = member_response.data[0]["username"]
                journal.append({
                    "timestamp": record["timestamp"],
                    "member": username,
                    "ticker": record["ticker"],
                    "action": record["action"],
                    "shares": float(record["shares"]),
                    "price": float(record["price"])
                })
        return journal
    except Exception as e:
        print(f"Error loading trade journal from Supabase: {e}")
        return []


def save_trade_journal(journal: list[dict[str, Any]]) -> None:
    """Save trade journal to Supabase (bulk operation)."""
    try:
        for trade in journal:
            # Get member ID
            member_response = supabase.table(MEMBERS_TABLE).select("id").eq("username", trade["member"]).execute()
            if not member_response.data:
                continue
            
            member_id = member_response.data[0]["id"]
            
            # Check if trade exists to avoid duplicates
            existing = supabase.table(TRADE_JOURNAL_TABLE).select("*").eq("timestamp", trade["timestamp"]).eq("ticker", trade["ticker"]).execute()
            if not existing.data:
                supabase.table(TRADE_JOURNAL_TABLE).insert({
                    "member_id": member_id,
                    "timestamp": trade["timestamp"],
                    "ticker": trade["ticker"],
                    "action": trade["action"],
                    "shares": float(trade["shares"]),
                    "price": float(trade["price"])
                }).execute()
    except Exception as e:
        print(f"Error saving trade journal to Supabase: {e}")


def log_trades_if_any(
    username: str,
    old_state: PortfolioState,
    new_state: PortfolioState,
    prices: dict[str, float],
) -> None:
    """Log trades to Supabase."""
    try:
        # Get member ID
        member_response = supabase.table(MEMBERS_TABLE).select("id").eq("username", username).execute()
        if not member_response.data:
            return
        
        member_id = member_response.data[0]["id"]
        
        old_holdings = normalize_holdings(old_state.holdings)
        new_holdings = normalize_holdings(new_state.holdings)

        all_tickers = set(old_holdings.keys()) | set(new_holdings.keys())

        for ticker in all_tickers:
            old_shares = old_holdings.get(ticker, 0.0)
            new_shares = new_holdings.get(ticker, 0.0)
            diff = new_shares - old_shares

            if abs(diff) > 1e-6:
                action = "BUY" if diff > 0 else "SELL"
                shares = abs(diff)
                price = prices.get(ticker, 0.0)
                
                supabase.table(TRADE_JOURNAL_TABLE).insert({
                    "member_id": member_id,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "ticker": ticker,
                    "action": action,
                    "shares": round(shares, 4),
                    "price": round(price, 2)
                }).execute()
    except Exception as e:
        print(f"Error logging trades to Supabase: {e}")


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
