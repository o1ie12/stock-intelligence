"""
Stock Universe Configuration

This module manages the stock universe configuration for the stock intelligence system.
It provides functions to load and manage different stock universes including the S&P 500.
"""

import pandas as pd
import yfinance as yf
from typing import List, Dict, Optional
import time


# Default universe configuration
DEFAULT_UNIVERSE = "sp500"  # Can be changed to "semiconductor" for faster testing

# Available universes
AVAILABLE_UNIVERSES = {
    "sp500": "S&P 500",
    "semiconductor": "Semiconductor (4 stocks)",
    "custom": "Custom universe"
}


def get_sp500_constituents() -> List[str]:
    """
    Fetch S&P 500 constituents from Wikipedia.
    
    Returns:
        List of S&P 500 stock tickers
    """
    try:
        # Read Wikipedia table
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        tables = pd.read_html(url)
        
        # The first table contains the S&P 500 constituents
        df = tables[0]
        
        # Extract ticker symbols
        tickers = df['Symbol'].tolist()
        
        # Clean tickers (remove dots and convert to uppercase)
        clean_tickers = [ticker.replace('.', '-') for ticker in tickers]
        
        return clean_tickers
    except Exception as e:
        print(f"Error fetching S&P 500 constituents from Wikipedia: {e}")
        print("Using fallback list of major S&P 500 stocks...")
        return get_fallback_sp500_list()


def get_fallback_sp500_list() -> List[str]:
    """
    Fallback list of major S&P 500 stocks if Wikipedia fails.
    This is a comprehensive but not exhaustive list of major S&P 500 constituents.
    
    Returns:
        List of major S&P 500 stock tickers
    """
    # This is a representative list of major S&P 500 stocks across sectors
    # In production, you'd want to use a reliable API or maintain this list regularly
    fallback_tickers = [
        # Technology
        "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "META", "NVDA", "AMD", "INTC", "CSCO",
        "ADBE", "CRM", "ORCL", "IBM", "ACN", "QCOM", "TXN", "AVGO", "NOW", "INTU",
        "SHOP", "SQ", "PYPL", "SNOW", "PLTR", "UBER", "LYFT", "DOCU", "ZM", "TEAM",
        
        # Healthcare
        "JNJ", "UNH", "PFE", "ABBV", "TMO", "ABT", "DHR", "MRK", "LLY", "BMY",
        "AMGN", "GILD", "MDT", "ISRG", "BDX", "CI", "CVS", "CNC", "HUM", "VRTX",
        "REGN", "MRNA", "BIIB", "ALXN", "ILMN", "IQV", "DGX", "LH", "EXAS", "INCY",
        
        # Financials
        "JPM", "BAC", "WFC", "C", "GS", "MS", "BLK", "SCHW", "AXP", "USB",
        "PNC", "TFC", "COF", "CBOE", "ICE", "MCO", "SPGI", "MMC", "AON", "AFL",
        "MET", "PRU", "LNC", "HIG", "ALL", "TRV", "CB", "WRB", "AIZ", "UNM",
        
        # Consumer Discretionary
        "TSLA", "AMZN", "HD", "MCD", "NKE", "SBUX", "LOW", "TJX", "BKNG", "MAR",
        "DG", "ROST", "F", "GM", "COST", "WMT", "TGT", "KR", "COST", "BJ",
        "HLT", "DRI", "CMG", "YUM", "MCD", "DPZ", "WING", "PLAY", "CHUY", "TXRH",
        
        # Consumer Staples
        "PG", "KO", "PEP", "COST", "WMT", "PM", "MO", "MDLZ", "K", "CL",
        "CLX", "KMB", "SYY", "CAG", "GIS", "HNZ", "CPB", "KHC", "STZ", "TSN",
        "ADM", "BG", "COTY", "EL", "REV", "IPG", "OMC", "WHR", "HPQ", "XRX",
        
        # Energy
        "XOM", "CVX", "COP", "SLB", "EOG", "PXD", "MPC", "PSX", "VLO", "OXY",
        "BKR", "HAL", "NOV", "FTI", "WMB", "ET", "KMI", "TRGP", "PAA", "EPD",
        
        # Industrials
        "BA", "CAT", "GE", "MMM", "HON", "UNP", "LMT", "RTX", "GD", "NOC",
        "UPS", "FDX", "CSX", "NSC", "UNP", "KSU", "EMR", "ITW", "ROP", "CMI",
        "DE", "AGCO", "CAT", "JOY", "MTW", "PNR", "DOV", "IR", "PH", "ROK",
        
        # Materials
        "LIN", "APD", "SHW", "ECL", "DOW", "DD", "NEM", "FCX", "AA", "ALB",
        "CE", "FMC", "PPG", "IP", "WY", "PKG", "AVY", "BMS", "OLN", "WLK",
        
        # Utilities
        "NEE", "DUK", "SO", "D", "EXC", "AEP", "SRE", "XEL", "WEC", "ED",
        "PEG", "EIX", "ETR", "AWK", "AES", "NRG", "CNP", "PPL", "PNW", "OKE",
        
        # Real Estate
        "AMT", "PLD", "CCI", "EQIX", "PSA", "CBRE", "SPG", "O", "VICI", "WELL",
        "DLR", "VTR", "HCP", "HCN", "PEAK", "EQC", "BXP", "SLG", "KIM", "FRT",
        
        # Communication Services
        "GOOGL", "GOOG", "META", "T", "VZ", "CMCSA", "DIS", "NFLX", "CHTR", "EA",
        "ATVI", "TTWO", "ZM", "OKTA", "SNOW", "DOCU", "TWLO", "RNG", "ZEN", "HUBS"
    ]
    
    return fallback_tickers


def get_sp500_constituents_from_yfinance() -> List[str]:
    """
    Fetch S&P 500 constituents using yfinance.
    This is an alternative method if Wikipedia fails.
    
    Returns:
        List of S&P 500 stock tickers
    """
    try:
        # Use SPY ETF holdings as a proxy for S&P 500
        spy = yf.Ticker("SPY")
        info = spy.info
        
        # Try to get holdings from info
        if 'holdings' in info:
            return list(info['holdings'].keys())
        
        # Alternative: Use a predefined list if yfinance doesn't provide holdings
        # This is a fallback mechanism
        return get_sp500_constituents()
    except Exception as e:
        print(f"Error fetching S&P 500 constituents from yfinance: {e}")
        return get_sp500_constituents()


def get_semiconductor_universe() -> List[str]:
    """
    Get the original semiconductor universe.
    
    Returns:
        List of semiconductor stock tickers
    """
    return ["NVDA", "AMD", "TSM", "ASML"]


def get_universe(universe_type: str = DEFAULT_UNIVERSE) -> List[str]:
    """
    Get stock universe based on type.
    
    Args:
        universe_type: Type of universe ('sp500', 'semiconductor', 'custom')
    
    Returns:
        List of stock tickers
    """
    if universe_type == "sp500":
        return get_sp500_constituents()
    elif universe_type == "semiconductor":
        return get_semiconductor_universe()
    elif universe_type == "custom":
        # For custom universe, you can add your own logic here
        # or load from a file
        return []
    else:
        raise ValueError(f"Unknown universe type: {universe_type}")


def validate_tickers(tickers: List[str], max_retries: int = 2) -> Dict[str, bool]:
    """
    Validate which tickers are actively traded and have data available.
    
    Args:
        tickers: List of ticker symbols to validate
        max_retries: Maximum number of retries for failed API calls
    
    Returns:
        Dictionary mapping ticker to validity (True if valid, False if invalid)
    """
    validity = {}
    
    for ticker in tickers:
        for attempt in range(max_retries + 1):
            try:
                t = yf.Ticker(ticker)
                # Try to fetch basic info to check if ticker exists
                hist = t.history(period="5d")
                
                if len(hist) > 0:
                    validity[ticker] = True
                    break
                else:
                    validity[ticker] = False
                    break
            except Exception as e:
                if attempt == max_retries:
                    validity[ticker] = False
                    print(f"Failed to validate {ticker} after {max_retries + 1} attempts: {e}")
                else:
                    # Wait before retry
                    time.sleep(0.1)
                    continue
    
    return validity


def get_filtered_universe(universe_type: str = DEFAULT_UNIVERSE, 
                         filter_valid: bool = True) -> List[str]:
    """
    Get filtered universe with option to remove invalid tickers.
    
    Args:
        universe_type: Type of universe
        filter_valid: Whether to filter out invalid tickers
    
    Returns:
        List of valid stock tickers
    """
    tickers = get_universe(universe_type)
    
    if not filter_valid:
        return tickers
    
    # Validate tickers
    validity = validate_tickers(tickers)
    valid_tickers = [ticker for ticker, is_valid in validity.items() if is_valid]
    
    return valid_tickers


def get_universe_stats(universe_type: str = DEFAULT_UNIVERSE,
                       filter_valid: bool = True) -> Dict[str, int]:
    """
    Get statistics about the universe.
    
    Args:
        universe_type: Type of universe
        filter_valid: Whether to filter valid tickers for stats
    
    Returns:
        Dictionary with universe statistics
    """
    total_tickers = get_universe(universe_type)
    
    if filter_valid:
        valid_tickers = get_filtered_universe(universe_type, filter_valid=True)
        return {
            "total": len(total_tickers),
            "valid": len(valid_tickers),
            "invalid": len(total_tickers) - len(valid_tickers)
        }
    else:
        return {
            "total": len(total_tickers),
            "valid": len(total_tickers),
            "invalid": 0
        }


if __name__ == "__main__":
    # Test the module
    print("Testing universe configuration...")
    
    # Test semiconductor universe
    print("\nSemiconductor Universe:")
    semiconductors = get_semiconductor_universe()
    print(f"Tickers: {semiconductors}")
    print(f"Count: {len(semiconductors)}")
    
    # Test S&P 500 universe
    print("\nS&P 500 Universe:")
    sp500 = get_sp500_constituents()
    print(f"Count: {len(sp500)}")
    print(f"First 10 tickers: {sp500[:10]}")
    
    # Test universe stats
    print("\nUniverse Statistics:")
    stats = get_universe_stats("sp500", filter_valid=False)
    print(f"S&P 500 Stats: {stats}")
    
    semicon_stats = get_universe_stats("semiconductor", filter_valid=False)
    print(f"Semiconductor Stats: {semicon_stats}")