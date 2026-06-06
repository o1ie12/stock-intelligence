import yfinance as yf
import pandas as pd
import time
from typing import Dict, List, Optional, Tuple
from universe_config import get_universe, DEFAULT_UNIVERSE

# Configuration
UNIVERSE_TYPE = DEFAULT_UNIVERSE  # Can be "sp500", "semiconductor", or "custom"

def fetch_stock(ticker, max_retries: int = 2) -> Optional[Dict]:
    """
    Fetch stock data with robust error handling and retry logic.
    
    Args:
        ticker: Stock ticker symbol
        max_retries: Maximum number of retry attempts for API failures
    
    Returns:
        Dictionary with stock data or None if fetching fails
    """
    for attempt in range(max_retries + 1):
        try:
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
        except Exception as e:
            if attempt < max_retries:
                # Wait briefly before retry (exponential backoff)
                time.sleep(0.1 * (2 ** attempt))
                continue
            else:
                print(f"Failed to fetch data for {ticker} after {max_retries + 1} attempts: {e}")
                return None
    
    return None

def build_signals(universe_type: str = UNIVERSE_TYPE) -> Tuple[pd.DataFrame, Dict]:
    """
    Build stock signals using the specified universe with robust error handling.
    
    Args:
        universe_type: Type of universe to use ("sp500", "semiconductor", or "custom")
    
    Returns:
        Tuple of (DataFrame with signals, Dictionary with execution statistics)
    """
    start_time = time.time()
    
    # Get universe from configuration
    stocks = get_universe(universe_type)
    
    data = []
    missing_pe = []
    missing_roe = []
    api_failures = []
    insufficient_data = []
    
    print(f"Fetching data for {len(stocks)} stocks from {universe_type} universe...")
    
    for s in stocks:
        try:
            r = fetch_stock(s)
            if r:
                # Track missing data
                if r["PE"] is None or (isinstance(r["PE"], float) and pd.isna(r["PE"])):
                    missing_pe.append(s)
                if r["ROE"] is None or (isinstance(r["ROE"], float) and pd.isna(r["ROE"])):
                    missing_roe.append(s)
                
                data.append(r)
            else:
                # Track failures
                insufficient_data.append(s)
        except Exception as e:
            api_failures.append(s)
            print(f"Exception fetching {s}: {e}")
    
    df = pd.DataFrame(data)
    
    # Clean data with robust handling
    df["ROE"] = df["ROE"].fillna(0)
    df["PE"] = df["PE"].fillna(999)
    df["Momentum"] = df["Momentum"].fillna(0)
    
    # Remove rows where all critical data is missing
    initial_count = len(df)
    df = df[(df["ROE"] != 0) | (df["PE"] != 999) | (df["Momentum"] != 0)]
    removed_all_missing = initial_count - len(df)
    
    # Factor ranks (cross-sectional)
    df["ROE_Rank"] = df["ROE"].rank(pct=True)
    df["PE_Rank"] = df["PE"].rank(pct=True, ascending=False)
    df["Momentum_Rank"] = df["Momentum"].rank(pct=True)
    
    # Final score (preserving original weights)
    df["Score"] = (
        df["ROE_Rank"] * 0.4 +
        df["Momentum_Rank"] * 0.4 +
        df["PE_Rank"] * 0.2
    )
    
    # Calculate execution time
    execution_time = time.time() - start_time
    
    # Build statistics
    stats = {
        "universe_type": universe_type,
        "total_universe_size": len(stocks),
        "successfully_scored": len(df),
        "excluded_missing_pe": len(missing_pe),
        "excluded_missing_roe": len(missing_roe),
        "api_failures": len(api_failures),
        "insufficient_data": len(insufficient_data),
        "removed_all_missing": removed_all_missing,
        "final_universe_size": len(df),
        "execution_time_seconds": round(execution_time, 2),
        "missing_pe_tickers": missing_pe[:10],  # First 10 for reporting
        "missing_roe_tickers": missing_roe[:10],  # First 10 for reporting
        "api_failure_tickers": api_failures[:10],  # First 10 for reporting
    }
    
    # Print execution report
    print("\n=== SIGNAL GENERATION REPORT ===")
    print(f"Universe Type: {stats['universe_type']}")
    print(f"Total Universe Size: {stats['total_universe_size']}")
    print(f"Successfully Scored: {stats['successfully_scored']}")
    print(f"Excluded (Missing PE): {stats['excluded_missing_pe']}")
    print(f"Excluded (Missing ROE): {stats['excluded_missing_roe']}")
    print(f"API Failures: {stats['api_failures']}")
    print(f"Insufficient Data: {stats['insufficient_data']}")
    print(f"Removed (All Missing): {stats['removed_all_missing']}")
    print(f"Final Universe Size: {stats['final_universe_size']}")
    print(f"Execution Time: {stats['execution_time_seconds']} seconds")
    
    if stats['missing_pe_tickers']:
        print(f"\nSample Missing PE Tickers: {stats['missing_pe_tickers']}")
    if stats['missing_roe_tickers']:
        print(f"Sample Missing ROE Tickers: {stats['missing_roe_tickers']}")
    if stats['api_failure_tickers']:
        print(f"Sample API Failure Tickers: {stats['api_failure_tickers']}")
    
    return df, stats


# Backward compatibility wrapper
def build_signals_legacy():
    """
    Legacy wrapper for backward compatibility.
    Returns only the DataFrame without statistics.
    """
    df, _ = build_signals()
    return df