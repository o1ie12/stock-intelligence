"""
Migration script to move existing JSON data to Supabase
"""
import json
from pathlib import Path
from database import supabase, MEMBERS_TABLE, PORTFOLIOS_TABLE
from database import MODEL_PORTFOLIO_TABLE, PORTFOLIO_HISTORY_TABLE
from database import TRADE_JOURNAL_TABLE, MODEL_HISTORY_TABLE, MODEL_CHANGES_TABLE

def migrate_members():
    """Migrate club members from JSON to Supabase."""
    try:
        members_file = Path(__file__).parent / "club_members.json"
        if members_file.exists():
            with open(members_file) as f:
                members = json.load(f)
            
            for username, data in members.items():
                # Check if member exists
                existing = supabase.table(MEMBERS_TABLE).select("*").eq("username", username).execute()
                if not existing.data:
                    supabase.table(MEMBERS_TABLE).insert({
                        "username": username,
                        "initial_value": float(data.get("initial_value", 10000.0))
                    }).execute()
                    print(f"✅ Migrated member: {username}")
                else:
                    print(f"⏭️  Member already exists: {username}")
        else:
            print("⚠️  No members file found")
    except Exception as e:
        print(f"❌ Error migrating members: {e}")

def migrate_portfolios():
    """Migrate club portfolios from JSON to Supabase."""
    try:
        portfolios_file = Path(__file__).parent / "club_portfolios.json"
        if portfolios_file.exists():
            with open(portfolios_file) as f:
                portfolios = json.load(f)
            
            for username, data in portfolios.items():
                # Get member ID
                member_response = supabase.table(MEMBERS_TABLE).select("id").eq("username", username).execute()
                if member_response.data:
                    member_id = member_response.data[0]["id"]
                    
                    # Check if portfolio exists
                    existing = supabase.table(PORTFOLIOS_TABLE).select("*").eq("member_id", member_id).execute()
                    if not existing.data:
                        supabase.table(PORTFOLIOS_TABLE).insert({
                            "member_id": member_id,
                            "cash": float(data.get("cash", 0.0)),
                            "holdings": data.get("holdings", {})
                        }).execute()
                        print(f"✅ Migrated portfolio for: {username}")
                    else:
                        print(f"⏭️  Portfolio already exists: {username}")
                else:
                    print(f"⚠️  Member not found for portfolio: {username}")
        else:
            print("⚠️  No portfolios file found")
    except Exception as e:
        print(f"❌ Error migrating portfolios: {e}")

def migrate_model_portfolio():
    """Migrate model portfolio from JSON to Supabase."""
    try:
        model_portfolio_file = Path(__file__).parent / "model_portfolio.json"
        if model_portfolio_file.exists():
            with open(model_portfolio_file) as f:
                model_portfolio = json.load(f)
            
            # Delete existing model portfolio
            existing = supabase.table(MODEL_PORTFOLIO_TABLE).select("*").execute()
            if existing.data:
                supabase.table(MODEL_PORTFOLIO_TABLE).delete().eq("id", existing.data[0]["id"]).execute()
            
            # Insert new model portfolio
            supabase.table(MODEL_PORTFOLIO_TABLE).insert({
                "cash": float(model_portfolio.get("cash", 10000.0)),
                "positions": model_portfolio.get("positions", {}),
                "initial_value": float(model_portfolio.get("initial_value", 10000.0)),
                "last_rebalance": model_portfolio.get("last_rebalance")
            }).execute()
            print("✅ Migrated model portfolio")
        else:
            print("⚠️  No model portfolio file found")
    except Exception as e:
        print(f"❌ Error migrating model portfolio: {e}")

def migrate_portfolio_history():
    """Migrate portfolio history from JSON to Supabase."""
    try:
        history_file = Path(__file__).parent / "portfolio_history.json"
        if history_file.exists():
            with open(history_file) as f:
                history = json.load(f)
            
            for username, records in history.items():
                # Get member ID
                member_response = supabase.table(MEMBERS_TABLE).select("id").eq("username", username).execute()
                if member_response.data:
                    member_id = member_response.data[0]["id"]
                    
                    for record in records:
                        supabase.table(PORTFOLIO_HISTORY_TABLE).insert({
                            "member_id": member_id,
                            "timestamp": record["timestamp"],
                            "portfolio_value": float(record["portfolio_value"]),
                            "cash": float(record["cash"]),
                            "holdings": record["holdings"]
                        }).execute()
                    print(f"✅ Migrated history for: {username} ({len(records)} records)")
                else:
                    print(f"⚠️  Member not found for history: {username}")
        else:
            print("⚠️  No portfolio history file found")
    except Exception as e:
        print(f"❌ Error migrating portfolio history: {e}")

def migrate_trade_journal():
    """Migrate trade journal from JSON to Supabase."""
    try:
        journal_file = Path(__file__).parent / "trade_journal.json"
        if journal_file.exists():
            with open(journal_file) as f:
                journal = json.load(f)
            
            for trade in journal:
                # Get member ID
                member_response = supabase.table(MEMBERS_TABLE).select("id").eq("username", trade["member"]).execute()
                if member_response.data:
                    member_id = member_response.data[0]["id"]
                    
                    supabase.table(TRADE_JOURNAL_TABLE).insert({
                        "member_id": member_id,
                        "timestamp": trade["timestamp"],
                        "ticker": trade["ticker"],
                        "action": trade["action"],
                        "shares": float(trade["shares"]),
                        "price": float(trade["price"])
                    }).execute()
            print(f"✅ Migrated trade journal ({len(journal)} records)")
        else:
            print("⚠️  No trade journal file found")
    except Exception as e:
        print(f"❌ Error migrating trade journal: {e}")

def migrate_model_history():
    """Migrate model history from JSON to Supabase."""
    try:
        history_file = Path(__file__).parent / "model_portfolio_history.json"
        if history_file.exists():
            with open(history_file) as f:
                history = json.load(f)
            
            for record in history:
                supabase.table(MODEL_HISTORY_TABLE).insert({
                    "date": record["date"],
                    "portfolio_value": float(record["portfolio_value"]),
                    "return_pct": float(record["return_pct"])
                }).execute()
            print(f"✅ Migrated model history ({len(history)} records)")
        else:
            print("⚠️  No model history file found")
    except Exception as e:
        print(f"❌ Error migrating model history: {e}")

def migrate_model_changes():
    """Migrate model changes from JSON to Supabase."""
    try:
        changes_file = Path(__file__).parent / "model_changes.json"
        if changes_file.exists():
            with open(changes_file) as f:
                changes = json.load(f)
            
            for change in changes:
                supabase.table(MODEL_CHANGES_TABLE).insert({
                    "date": change["date"],
                    "action": change["action"],
                    "ticker": change["ticker"]
                }).execute()
            print(f"✅ Migrated model changes ({len(changes)} records)")
        else:
            print("⚠️  No model changes file found")
    except Exception as e:
        print(f"❌ Error migrating model changes: {e}")

if __name__ == "__main__":
    print("=" * 50)
    print("MIGRATING DATA FROM JSON TO SUPABASE")
    print("=" * 50)
    
    migrate_members()
    migrate_portfolios()
    migrate_model_portfolio()
    migrate_portfolio_history()
    migrate_trade_journal()
    migrate_model_history()
    migrate_model_changes()
    
    print("=" * 50)
    print("MIGRATION COMPLETE!")
    print("=" * 50)