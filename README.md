# Stock Intelligence System

A factor-based stock analysis tool that ranks stocks and builds a simulated portfolio using three key signals: Momentum, Return on Equity (ROE), and Price-to-Earnings (P/E).

## What It Is

The Stock Intelligence System is an educational project that demonstrates factor-based investing concepts. It generates a ranked list of stocks, constructs a model portfolio, and evaluates performance using historical backtesting against the SPY benchmark.

**Disclaimer:** This project is for educational use only. It does not provide financial advice or trading recommendations.

## Features

- **Factor-Based Stock Scoring Model**: Uses Momentum, ROE, and P/E ratios to rank stocks
- **Automated Portfolio Construction**: Selects top 5 stocks with exponential weighting
- **Mathematically Consistent Backtesting**: Live and backtest engines use identical methodology
- **Investment Club Dashboard**: Streamlit-based interface with member portfolio tracking
- **Model Portfolio Benchmark**: Automated benchmark portfolio for performance comparison
- **Performance Analytics**: Sharpe ratio, drawdown, volatility metrics vs SPY

## How It Works

1. **Stock Scoring**: Stocks are scored using 3 factors
   - **Momentum** (40% weight): 6-month price momentum
   - **ROE** (40% weight): Return on equity ranking
   - **P/E** (20% weight): Price-to-earnings ranking (inverted - lower is better)

2. **Stock Ranking**: Stocks are ranked by their composite score

3. **Portfolio Construction**: Top 5 stocks are selected
   - Exponential weighting based on scores
   - Position limits: minimum 5%, maximum 35% per stock
   - 5% cash reserve

4. **Performance Evaluation**: Historical simulation against SPY benchmark

## Architecture

The system uses a unified portfolio construction approach to ensure mathematical consistency:

- **`model.py`**: Signal generation and stock scoring
- **`portfolio_engine.py`**: Core portfolio construction logic with `build_shared_portfolio()`
- **`backtest.py`**: Historical validation using identical methodology
- **`streamlit_app.py`**: Interactive dashboard interface

## How to Run

### Prerequisites

- Python 3.8+
- Virtual environment (recommended)

### Installation

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Running the Application

```bash
# Start the Streamlit dashboard
streamlit run streamlit_app.py
```

The app will be available at `http://localhost:8501`

### Running Backtests

```bash
# Run the standard backtest
python backtest.py

# Run comprehensive factor validation
python model_validation.py
```

## Stock Universe

The current implementation uses a focused universe of 4 semiconductor stocks:
- NVDA (NVIDIA)
- AMD (Advanced Micro Devices)
- TSM (Taiwan Semiconductor)
- ASML (ASML Holding)

*Note: The backtest system uses a larger 32-stock multi-sector universe for validation purposes.*

## Key Concepts

### Factor Scoring

Each stock receives a percentile rank (0-100) for each factor:
- **ROE Rank**: Higher ROE = higher rank ( profitability)
- **Momentum Rank**: Higher momentum = higher rank (price trend)
- **PE Rank**: Lower PE = higher rank (valuation attractiveness)

### Portfolio Construction

The system uses exponential weighting to emphasize high-scoring stocks:
- Scores are transformed using `exp(score)`
- Weights are normalized and clipped to [5%, 35%]
- Cash reserve of 5% is maintained
- Only top 5 stocks by score are selected

### Performance Metrics

- **Sharpe Ratio**: Risk-adjusted return (higher is better)
- **Max Drawdown**: Maximum peak-to-trough decline (lower is better)
- **Volatility**: Annualized standard deviation of returns
- **Excess Return**: Performance difference vs SPY benchmark

## Recent Updates (Phase 2)

**Strategy Consistency & Validation**: 
- Unified portfolio construction across all systems
- Eliminated mathematical inconsistencies between live and backtest engines
- Implemented exponential weighting with position limits in backtest
- Performance improved from 31.6% to 49.3% annual return

## Project Structure

```
stock-intelligence/
├── model.py                  # Signal generation and scoring
├── portfolio_engine.py       # Portfolio construction and management
├── backtest.py              # Historical backtesting
├── streamlit_app.py         # Dashboard interface
├── model_validation.py      # Comprehensive factor analysis
├── requirements.txt         # Python dependencies
├── model_portfolio.json     # Model portfolio state
├── club_members.json        # Investment club members
└── README.md               # This file
```

## Disclaimer

**IMPORTANT:** This project is for educational purposes only. It is not intended to provide financial advice, investment recommendations, or trading guidance. The results shown are based on historical data and do not guarantee future performance. Always consult with a qualified financial advisor before making investment decisions.

## License

This project is provided as-is for educational use.
