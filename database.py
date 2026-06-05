import os
from dotenv import load_dotenv
from supabase import create_client, Client

# Try loading from .env first (for local development)
load_dotenv()

# Lazy initialization - don't access streamlit.secrets during module import
_supabase_client: Client | None = None

def get_supabase_client() -> Client:
    """Get or create the Supabase client with lazy initialization."""
    global _supabase_client
    
    if _supabase_client is not None:
        return _supabase_client
    
    # Get Supabase credentials from environment variables
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")
    
    # If not in environment, try Streamlit secrets
    if not supabase_url or not supabase_key:
        try:
            import streamlit as st
            supabase_url = st.secrets.get("SUPABASE_URL", os.getenv("SUPABASE_URL"))
            supabase_key = st.secrets.get("SUPABASE_KEY", os.getenv("SUPABASE_KEY"))
        except (ImportError, AttributeError):
            pass
    
    if not supabase_url or not supabase_key:
        raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in .env file or secrets.toml")
    
    _supabase_client = create_client(supabase_url, supabase_key)
    return _supabase_client

# For backward compatibility, create a property-like access
class _SupabaseProxy:
    """Proxy to provide lazy access to the supabase client."""
    def __getattr__(self, name):
        return getattr(get_supabase_client(), name)

supabase = _SupabaseProxy()

# Table names
MEMBERS_TABLE = "members"
PORTFOLIOS_TABLE = "portfolios"
MODEL_PORTFOLIO_TABLE = "model_portfolio"
PORTFOLIO_HISTORY_TABLE = "portfolio_history"
TRADE_JOURNAL_TABLE = "trade_journal"
MODEL_HISTORY_TABLE = "model_history"
MODEL_CHANGES_TABLE = "model_changes"

def test_connection():
    """Test the Supabase connection."""
    try:
        result = supabase.table(MEMBERS_TABLE).select("username").limit(1).execute()
        print("✅ Supabase connection successful!")
        return True
    except Exception as e:
        print(f"❌ Supabase connection failed: {e}")
        return False