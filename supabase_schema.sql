-- Stock Intelligence System - Supabase Database Schema
-- Run this in your Supabase SQL Editor

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Members table (replaces club_members.json)
CREATE TABLE IF NOT EXISTS members (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    initial_value DECIMAL(10,2) NOT NULL DEFAULT 10000.00,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Portfolios table (replaces club_portfolios.json)
CREATE TABLE IF NOT EXISTS portfolios (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    member_id UUID REFERENCES members(id) ON DELETE CASCADE,
    cash DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    holdings JSONB NOT NULL DEFAULT '{}',
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(member_id)
);

-- Model portfolio table (replaces model_portfolio.json)
CREATE TABLE IF NOT EXISTS model_portfolio (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    cash DECIMAL(10,2) NOT NULL DEFAULT 10000.00,
    positions JSONB NOT NULL DEFAULT '{}',
    initial_value DECIMAL(10,2) NOT NULL DEFAULT 10000.00,
    last_rebalance TIMESTAMP,
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Portfolio history table (replaces portfolio_history.json)
CREATE TABLE IF NOT EXISTS portfolio_history (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    member_id UUID REFERENCES members(id) ON DELETE CASCADE,
    timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
    portfolio_value DECIMAL(10,2) NOT NULL,
    cash DECIMAL(10,2) NOT NULL,
    holdings JSONB NOT NULL DEFAULT '{}'
);

-- Trade journal table (replaces trade_journal.json)
CREATE TABLE IF NOT EXISTS trade_journal (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    member_id UUID REFERENCES members(id) ON DELETE CASCADE,
    timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
    ticker TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('BUY', 'SELL')),
    shares DECIMAL(10,4) NOT NULL,
    price DECIMAL(10,2) NOT NULL
);

-- Model history table (replaces model_portfolio_history.json)
CREATE TABLE IF NOT EXISTS model_history (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    date DATE NOT NULL,
    portfolio_value DECIMAL(10,2) NOT NULL,
    return_pct DECIMAL(5,2) NOT NULL
);

-- Model changes table (replaces model_changes.json)
CREATE TABLE IF NOT EXISTS model_changes (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    date DATE NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('ADD', 'REMOVE', 'WEIGHT_INCREASE', 'WEIGHT_DECREASE')),
    ticker TEXT NOT NULL
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_portfolio_history_member_id ON portfolio_history(member_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_history_timestamp ON portfolio_history(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_trade_journal_member_id ON trade_journal(member_id);
CREATE INDEX IF NOT EXISTS idx_trade_journal_timestamp ON trade_journal(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_model_history_date ON model_history(date DESC);
CREATE INDEX IF NOT EXISTS idx_model_changes_date ON model_changes(date DESC);

-- Insert initial model portfolio state
INSERT INTO model_portfolio (cash, positions, initial_value, last_rebalance)
VALUES (10000.0, '{}'::jsonb, 10000.0, NULL)
ON CONFLICT DO NOTHING;