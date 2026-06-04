-- Fix Row Level Security (RLS) policies for data migration
-- Run this in your Supabase SQL Editor

-- Disable RLS temporarily for migration
ALTER TABLE members DISABLE ROW LEVEL SECURITY;
ALTER TABLE portfolios DISABLE ROW LEVEL SECURITY;
ALTER TABLE model_portfolio DISABLE ROW LEVEL SECURITY;
ALTER TABLE portfolio_history DISABLE ROW LEVEL SECURITY;
ALTER TABLE trade_journal DISABLE ROW LEVEL SECURITY;
ALTER TABLE model_history DISABLE ROW LEVEL SECURITY;
ALTER TABLE model_changes DISABLE ROW LEVEL SECURITY;

-- After migration, you can re-enable RLS with proper policies
-- ALTER TABLE members ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE portfolios ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE model_portfolio ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE portfolio_history ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE trade_journal ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE model_history ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE model_changes ENABLE ROW LEVEL SECURITY;