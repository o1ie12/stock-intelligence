# Stock Intelligence System

**LIVE APP:** https://stock-intelligence-nextgen.streamlit.app/

**Status:** **Live on Streamlit Cloud** | **Multi-User** | **No Installation Required**

---

## **For Users: Just Visit and Use!**

**No installation required!** Just visit the live app URL above and start using it.

- **Works in any web browser** (Chrome, Firefox, Safari, Edge, etc.)
- **Works on any device** (desktop, tablet, mobile)
- **No account signup** needed (just use the app)
- **No Python installation** needed
- **Nothing to download or configure**

---

## **What It Does**

The Stock Intelligence System is an educational tool that helps you understand factor-based investing. It:

- **Analyzes stocks** using 3 key factors: Momentum, ROE, and P/E ratios
- **Ranks stocks** based on their combined factor scores
- **Builds a model portfolio** with the top 5 stocks
- **Tracks performance** against the SPY benchmark
- **Enables investment club collaboration** with multi-user portfolio management

**Educational Disclaimer:** This project is for educational purposes only. It does not provide financial advice or trading recommendations.

---

## **Key Features**

- **Multi-User Cloud Deployment:** Access from anywhere, share with friends
- **Factor-Based Stock Scoring:** Uses Momentum, ROE, and P/E ratios to rank stocks
- **Automated Portfolio Construction:** Selects top 5 stocks with smart weighting
- **Investment Club Dashboard:** Track portfolios, compare performance, see leaderboards
- **Model Portfolio Benchmark:** See how the model strategy performs
- **Performance Analytics:** Sharpe ratio, drawdown, volatility metrics vs SPY
- **Real-Time Data Sharing:** Multiple users can access and update shared portfolio data

---

## **For Developers: Local Development Setup**

If you're a developer wanting to run this locally or contribute to the code, follow these steps:

### Prerequisites

- Python 3.8+
- Virtual environment (recommended)
- Supabase account (for local development)

### Database Setup

1. Create a Supabase account at https://supabase.com
2. Create a new project
3. Run the SQL schema in `supabase_schema.sql` in the Supabase SQL Editor
4. Disable RLS temporarily (run `fix_rls.sql`)
5. Copy your Project URL and anon key
6. Create a `.env` file with your credentials:
   ```
   SUPABASE_URL=your_project_url
   SUPABASE_KEY=your_anon_key
   ```

### Installation

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Running the Application Locally

```bash
# Start the Streamlit dashboard
streamlit run streamlit_app.py
```

The app will be available at `http://localhost:8501`

---

## **Architecture**

The system uses a unified portfolio construction approach to ensure mathematical consistency:

- **`model.py`**: Signal generation and stock scoring
- **`portfolio_engine.py`**: Core portfolio construction logic with `build_shared_portfolio()`
- **`backtest.py`**: Historical validation using identical methodology
- **`streamlit_app.py`**: Interactive dashboard interface
- **`database.py`**: Supabase database connection and management
- **Supabase**: Cloud database for multi-user data persistence

---

## **Cloud Deployment**

The Stock Intelligence System is deployed on **Streamlit Cloud** with **Supabase** database backend.

### Deployment Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    CLOUD ARCHITECTURE                         │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Streamlit Cloud (Frontend)                                 │
│  └── streamlit_app.py (Web Interface)                        │
│                                                              │
│  Supabase (Backend Database)                                 │
│  ├── members (user accounts)                                 │
│  ├── portfolios (holdings & cash)                             │
│  ├── model_portfolio (benchmark)                             │
│  ├── portfolio_history (snapshots)                           │
│  ├── trade_journal (executions)                              │
│  └── model_history (performance)                             │
│                                                              │
│  GitHub (Code Repository)                                    │
│  └── Automatic deployment on push                             │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Database Schema (Supabase)

- **members**: Club member accounts with initial capital values
- **portfolios**: User portfolio holdings linked to members
- **model_portfolio**: Official model benchmark portfolio state
- **portfolio_history**: Historical portfolio performance snapshots
- **trade_journal**: Trade execution logs for all users
- **model_history**: Model portfolio performance tracking
- **model_changes**: Model portfolio rebalance change log

---

## **How It Works**

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

---

## **Stock Universe**

The current implementation uses a focused universe of 4 semiconductor stocks:
- NVDA (NVIDIA)
- AMD (Advanced Micro Devices)
- TSM (Taiwan Semiconductor)
- ASML (ASML Holding)

*Note: The backtest system uses a larger 32-stock multi-sector universe for validation purposes.*

---

## **Key Concepts**

### Factor Scoring

Each stock receives a percentile rank (0-100) for each factor:
- **ROE Rank**: Higher ROE = higher rank (profitability)
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

---

## **Project Structure**

```
stock-intelligence/
├── model.py                  # Signal generation and scoring
├── portfolio_engine.py       # Portfolio construction and management
├── backtest.py              # Historical backtesting
├── streamlit_app.py         # Dashboard interface
├── model_validation.py      # Comprehensive factor analysis
├── database.py              # Supabase database connection
├── requirements.txt         # Python dependencies
├── supabase_schema.sql      # Database table definitions
├── fix_rls.sql              # Row-level security fixes
├── migrate_to_supabase.py   # Data migration script
├── .streamlit/
│   ├── config.toml          # Streamlit configuration
│   └── secrets.toml         # Supabase credentials (gitignored)
├── .env                     # Local Supabase credentials (gitignored)
├── README.md                # This file
└── venv/                    # Virtual environment (gitignored)
```

---

## **Recent Updates**

### **Phase 3: Cloud Database Integration & Multi-User Deployment**

**Achievements:**
- Migrated from local JSON files to Supabase cloud database
- Implemented multi-user data sharing capabilities
- Successfully deployed to Streamlit Cloud
- Added proper secrets management with TOML configuration
- Created database schema with 7 tables for data persistence
- Migrated all existing data to cloud database
- Real-time data synchronization across users

**Benefits:**
- Multi-user access from anywhere in the world
- Cloud-based data persistence
- No local file dependencies
- Automatic deployment via GitHub integration
- SSL/HTTPS secure connection by default

### **Phase 2: Strategy Consistency & Validation**

**Strategy Consistency & Validation:** 
- Unified portfolio construction across all systems
- Eliminated mathematical inconsistencies between live and backtest engines
- Implemented exponential weighting with position limits in backtest
- Performance improved from 31.6% to 49.3% annual return

---

## **Disclaimer**

**IMPORTANT:** This project is for educational purposes only. It is not intended to provide financial advice, investment recommendations, or trading guidance. The results shown are based on historical data and do not guarantee future performance. Always consult with a qualified financial advisor before making investment decisions.

---

## **License**

This project is provided as-is for educational use.
