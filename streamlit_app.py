import json

import pandas as pd
import streamlit as st

from model import build_signals, build_signals_legacy
from portfolio_engine import (
    CASH_LABEL,
    PortfolioState,
    analyze_portfolio,
    normalize_holdings,
    load_user_portfolio,
    save_user_portfolio,
    create_member_profile,
    load_club_members_config,
    save_club_members_config,
    get_leaderboard_data,
    get_portfolio_history_df,
    append_portfolio_history,
    log_trades_if_any,
    load_trade_journal,
    get_club_analytics_data,
    get_club_holdings_insight,
    load_model_return,
    calculate_member_metrics,
    calculate_portfolio_value,
    calculate_portfolio_return,
    calculate_position_values,
    calculate_current_weights,
    load_model_portfolio,
    needs_rebalance_model_portfolio,
    rebalance_model_portfolio,
    load_model_portfolio_history,
    generate_decision_explanation,
    construct_target_portfolio,
    build_model_target_portfolio,
    load_model_changes,
    fetch_current_prices,
)


# ==========================================
# PAGE CONFIG
# ==========================================
st.set_page_config(
    page_title="Stock Intelligence - Investment Club",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("Stock Intelligence Investment Club")


# ==========================================
# SIDEBAR: USER MANAGEMENT
# ==========================================
st.sidebar.title("Club Member Portal")

config = load_club_members_config()
members_list = sorted(list(config.keys()))

if not members_list:
    create_member_profile("Oliver", 11111.11)
    config = load_club_members_config()
    members_list = sorted(list(config.keys()))

if "active_member" not in st.session_state:
    if members_list:
        st.session_state.active_member = "Oliver" if "Oliver" in members_list else members_list[0]
    else:
        st.session_state.active_member = "Oliver"

if members_list:
    active_member = st.sidebar.selectbox(
        "Active Club Member",
        members_list,
        index=members_list.index(st.session_state.active_member) if st.session_state.active_member in members_list else 0,
        key="active_member_selector",
    )
    st.session_state.active_member = active_member
else:
    st.sidebar.error("No members found. Please add a member to continue.")
    st.session_state.active_member = None

st.sidebar.divider()

st.sidebar.subheader("Add New Member")
new_member_name = st.sidebar.text_input("Member Name", placeholder="e.g. Charlie")
starting_capital = st.sidebar.number_input(
    "Initial Starting Capital ($)",
    min_value=100.0,
    value=10000.0,
    step=500.0,
    format="%.2f",
)

if st.sidebar.button("Register Member Profile"):
    clean_name = new_member_name.strip()
    if clean_name:
        if clean_name in members_list or clean_name == "MODEL":
            st.sidebar.error(f"'{clean_name}' is already reserved or registered.")
        else:
            create_member_profile(clean_name, starting_capital)
            st.session_state.active_member = clean_name
            st.sidebar.success(f"Welcome to the club, {clean_name}!")
            st.rerun()
    else:
        st.sidebar.error("Name cannot be empty.")


# ==========================================
# SHARED DATA (with caching for performance)
# ==========================================

@st.cache_data(ttl=3600)  # Cache signals for 1 hour (signals based on 6-month trends, acceptable staleness)
def get_cached_signals():
    """Cached signal generation to reduce yfinance API calls."""
    return build_signals_legacy()

@st.cache_data(ttl=3600)  # Cache target portfolio for 1 hour (derived from cached signals)
def get_cached_target_portfolio():
    """Cached target portfolio construction."""
    return construct_target_portfolio()

signals_df = get_cached_signals().sort_values("Score", ascending=False)
target_weights_df = get_cached_target_portfolio()
leaderboard_df = get_leaderboard_data(target_weights_df)


# ==========================================
# TABS
# ==========================================
tab_leaderboard, tab_command, tab_history, tab_journal, tab_model = st.tabs([
    "Club Leaderboard",
    "Portfolio Command Center",
    "Performance History",
    "Trade Journal",
    "Model Portfolio",
])


# ------------------------------------------
# TAB 1: CLUB LEADERBOARD & ANALYTICS
# ------------------------------------------
with tab_leaderboard:
    st.header("Investment Club Leaderboard")

    st.dataframe(
        leaderboard_df,
        column_config={
            "Rank": st.column_config.NumberColumn(format="%d"),
            "Member": st.column_config.TextColumn(),
            "Portfolio Value": st.column_config.NumberColumn(format="$%,.2f"),
            "Return %": st.column_config.NumberColumn(format="%.2f%%"),
            "Top Holding": st.column_config.TextColumn(),
            "Model Alignment Score": st.column_config.NumberColumn(format="%.1f%%"),
        },
        use_container_width=True,
        hide_index=True,
    )

    st.divider()

    # Club Analytics
    st.header("Club Analytics")
    analytics = get_club_analytics_data(leaderboard_df)

    met_cols = st.columns(4)
    with met_cols[0]:
        st.metric("Number of Members", int(analytics["num_members"]))
    with met_cols[1]:
        st.metric("Average Club Return", f"{analytics['average_return']:.2f}%")
    with met_cols[2]:
        st.metric("Best Performer", f"{analytics['best_performer_name']} ({analytics['best_performer_return']:.2f}%)")
    with met_cols[3]:
        st.metric("Worst Performer", f"{analytics['worst_performer_name']} ({analytics['worst_performer_return']:.2f}%)")

    # Benchmark Insights
    st.subheader("Model Benchmark Comparison")
    bench_cols = st.columns(3)
    with bench_cols[0]:
        outperforming = analytics.get("outperforming_model", [])
        st.metric("Members Above Model", len(outperforming))
        if outperforming:
            st.caption(", ".join(outperforming))
    with bench_cols[1]:
        underperforming = analytics.get("underperforming_model", [])
        st.metric("Members Below Model", len(underperforming))
        if underperforming:
            st.caption(", ".join(underperforming))
    with bench_cols[2]:
        aligned_name = analytics.get("most_aligned_member", "None")
        aligned_score = analytics.get("most_aligned_score", 0.0)
        st.metric("Most Aligned Member", f"{aligned_name} ({aligned_score:.1f}%)")

    st.subheader("Performance Comparison")
    if not leaderboard_df.empty:
        st.bar_chart(leaderboard_df, x="Member", y="Return %", use_container_width=True)

    st.divider()

    # Club Holdings Insight
    st.header("Club Holdings Concentration")
    holdings_insight_df = get_club_holdings_insight()

    if not holdings_insight_df.empty:
        col_table, col_chart = st.columns([1, 1])
        with col_table:
            st.subheader("Ticker Ownership Count")
            st.dataframe(
                holdings_insight_df,
                column_config={
                    "Ticker": st.column_config.TextColumn(),
                    "Members Owning": st.column_config.NumberColumn(format="%d members"),
                },
                use_container_width=True,
                hide_index=True,
            )
        with col_chart:
            st.subheader("Holdings Concentration")
            st.bar_chart(holdings_insight_df, x="Ticker", y="Members Owning", use_container_width=True)
    else:
        st.info("No stocks currently owned by club members.")


# ------------------------------------------
# TAB 2: PORTFOLIO COMMAND CENTER
# ------------------------------------------
with tab_command:
    st.header(f"Portfolio Command Center  --  {active_member}")

    state = load_user_portfolio(active_member)

    model_return = load_model_return()

    analysis = analyze_portfolio(state)
    prices = analysis["prices"]
    metrics = calculate_member_metrics(active_member, state, target_weights_df, prices)

    user_return = metrics["return_pct"]
    diff_return = user_return - model_return

    comp_cols = st.columns(4)
    with comp_cols[0]:
        st.metric("User Return", f"{user_return:.2f}%")
    with comp_cols[1]:
        st.metric("Model Return", f"{model_return:.2f}%")
    with comp_cols[2]:
        st.metric("Difference", f"{diff_return:+.2f}%")
    with comp_cols[3]:
        st.metric("Model Alignment Score", f"{metrics['alignment_score']:.1f}%")

    st.divider()

    left, right = st.columns([1, 2])

    with left:
        st.subheader("Portfolio Parameters")
        cash = st.number_input(
            "Cash Balance ($)", min_value=0.0, value=float(state.cash),
            step=100.0, format="%.2f", key="user_cash_input",
        )
        min_trade_value = st.number_input(
            "Minimum Trade Threshold ($)", min_value=0.0, value=100.0,
            step=25.0, format="%.2f", key="user_min_trade",
        )
        cash_reserve = st.number_input(
            "Cash Reserve Ratio (0.0 - 0.5)", min_value=0.0, max_value=0.50,
            value=0.05, step=0.01, format="%.2f", key="user_cash_reserve",
        )

    with right:
        st.subheader("Asset Holdings")
        starting_rows = [
            {"Ticker": ticker, "Shares": shares}
            for ticker, shares in state.holdings.items()
        ]
        if not starting_rows:
            starting_rows = [{"Ticker": "NVDA", "Shares": 0.0}]

        holdings_input = st.data_editor(
            starting_rows, num_rows="dynamic",
            use_container_width=True, key="user_portfolio_holdings",
        )

    if isinstance(holdings_input, pd.DataFrame):
        holdings_records = holdings_input.to_dict("records")
    else:
        holdings_records = holdings_input

    holdings = normalize_holdings(
        {str(item.get("Ticker", "")): item.get("Shares", 0.0) for item in holdings_records}
    )
    proposed_state = PortfolioState(cash=cash, holdings=holdings)

    save_col, load_col = st.columns(2)
    with save_col:
        if st.button("Save Portfolio", key="save_portfolio_btn", use_container_width=True):
            log_trades_if_any(active_member, state, proposed_state, prices)
            save_user_portfolio(active_member, proposed_state)
            append_portfolio_history(active_member, proposed_state, prices)
            st.success(f"Portfolio saved and history checkpoint recorded for {active_member}.")
            st.rerun()
    with load_col:
        if st.button("Load Saved State", key="load_portfolio_btn", use_container_width=True):
            st.rerun()

    st.divider()

    st.subheader("Overview Metrics")
    current_allocation = analysis["current_allocation"]
    target_allocation = analysis["target_allocation"]
    trade_plan = analysis["trade_plan"]
    health = analysis["health"]
    summary = analysis["decision_summary"]

    metric_cols = st.columns(6)
    metric_cols[0].metric("Total Portfolio Value", "$" + format(metrics["portfolio_value"], ",.2f"))
    metric_cols[1].metric("Cash", "$" + format(state.cash, ",.2f"))
    metric_cols[2].metric("Holdings Owned", int(health["number_of_holdings"]))
    metric_cols[3].metric("Largest Position", "{:.1%}".format(health["largest_position"]))
    metric_cols[4].metric("Diversification Score", "{:.2f}".format(health["diversification_score"]))
    metric_cols[5].metric("Cash %", "{:.1%}".format(health["cash_weight"]))

    if health["top_risk_flag"]:
        st.warning("Portfolio concentration is high. At least one position exceeds 40% of portfolio value.")

    st.divider()

    col_alloc, col_model = st.columns(2)
    with col_alloc:
        st.subheader("Current Asset Allocation")
        current_display = current_allocation[["Ticker", "Value", "Weight"]] if not current_allocation.empty else current_allocation
        st.dataframe(current_display, use_container_width=True)
    with col_model:
        st.subheader("Model Target Weightings")
        st.dataframe(target_allocation[["Ticker", "Target Weight"]], use_container_width=True)

    st.subheader("Trade Recommendations")
    trade_display = trade_plan[["Ticker", "Action", "Shares To Buy/Sell", "Dollar Amount"]]
    st.dataframe(trade_display, use_container_width=True)

    st.subheader("Allocation Visualizations")
    chart_cols = st.columns(2)

    with chart_cols[0]:
        st.caption("Current Allocation Breakdown")
        current_chart = current_display.rename(columns={"Weight": "weight"}) if not current_display.empty else pd.DataFrame()
        if not current_chart.empty and health["cash_weight"] > 0:
            current_chart = pd.concat(
                [current_chart[["Ticker", "weight"]], pd.DataFrame([{"Ticker": CASH_LABEL, "weight": health["cash_weight"]}])],
                ignore_index=True,
            )
        if not current_chart.empty:
            st.vega_lite_chart(current_chart, {
                "mark": {"type": "arc", "tooltip": True},
                "encoding": {"theta": {"field": "weight", "type": "quantitative"}, "color": {"field": "Ticker", "type": "nominal"}},
            }, use_container_width=True)

    with chart_cols[1]:
        st.caption("Model Target Allocation Breakdown")
        target_chart = target_allocation.rename(columns={"Target Weight": "weight"})
        st.vega_lite_chart(target_chart, {
            "mark": {"type": "arc", "tooltip": True},
            "encoding": {"theta": {"field": "weight", "type": "quantitative"}, "color": {"field": "Ticker", "type": "nominal"}},
        }, use_container_width=True)

    st.subheader("Decision Insights")
    decision_cols = st.columns(5)
    decision_cols[0].metric("Highest Conviction", summary["Highest Conviction Position"])
    decision_cols[1].metric("Most Overweight", summary["Most Overweight Position"])
    decision_cols[2].metric("Most Underweight", summary["Most Underweight Position"])
    decision_cols[3].metric("Largest Buy", summary["Largest Recommended Buy"])
    decision_cols[4].metric("Largest Sell", summary["Largest Recommended Sell"])
    st.write(summary["Summary"])


# ------------------------------------------
# TAB 3: PERFORMANCE HISTORY
# ------------------------------------------
with tab_history:
    st.header(f"Performance History  --  {active_member}")

    history_df = get_portfolio_history_df(active_member)

    if not history_df.empty:
        history_chart_df = history_df.sort_values("timestamp")
        st.subheader("Historical Portfolio Growth")
        st.line_chart(history_chart_df, x="timestamp", y="portfolio_value", use_container_width=True)

        st.subheader("Historical Snapshot Log")
        st.dataframe(
            history_df.sort_values("timestamp", ascending=False),
            column_config={
                "timestamp": st.column_config.TextColumn("Date and Time"),
                "portfolio_value": st.column_config.NumberColumn("Total Value", format="$%,.2f"),
                "cash": st.column_config.NumberColumn("Cash Balance", format="$%,.2f"),
                "holdings": st.column_config.TextColumn("Positions"),
            },
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No historical snapshots recorded yet for this member.")

    st.divider()

    st.subheader("Adjust Initial Capital")
    st.markdown("Set your starting capital below. This is used to compute return percentages on the leaderboard.")

    member_config = load_club_members_config()
    current_init_val = float(member_config.get(active_member, {}).get("initial_value", 10000.0))

    new_init_val = st.number_input(
        "Initial Capital / Cost Basis ($)", min_value=1.0,
        value=current_init_val, step=500.0, format="%.2f", key="adjust_initial_val_input",
    )

    if st.button("Update Cost Basis", key="update_basis_btn"):
        member_config[active_member] = {"initial_value": float(new_init_val)}
        save_club_members_config(member_config)
        st.success(f"Cost basis for {active_member} updated to ${new_init_val:,.2f}.")
        st.rerun()


# ------------------------------------------
# TAB 4: TRADE JOURNAL
# ------------------------------------------
with tab_journal:
    st.header("Shared Investment Club Trade Journal")
    st.markdown("Logs transactions executed across all members of the investment club.")

    journal = load_trade_journal()

    if journal:
        journal_df = pd.DataFrame(journal)
        journal_df["Total Amount"] = journal_df["shares"] * journal_df["price"]

        st.subheader("Filter Activity")
        col_fil_m, col_fil_a = st.columns(2)
        with col_fil_m:
            filter_member = st.selectbox(
                "Filter by Member",
                ["All"] + sorted(list(set(journal_df["member"]))),
                key="journal_filter_member",
            )
        with col_fil_a:
            filter_action = st.selectbox("Filter by Action", ["All", "BUY", "SELL"], key="journal_filter_action")

        filtered_df = journal_df.copy()
        if filter_member != "All":
            filtered_df = filtered_df[filtered_df["member"] == filter_member]
        if filter_action != "All":
            filtered_df = filtered_df[filtered_df["action"] == filter_action]

        st.subheader("Transactions Log")
        st.dataframe(
            filtered_df.sort_values("timestamp", ascending=False),
            column_config={
                "timestamp": st.column_config.TextColumn("Date and Time"),
                "member": st.column_config.TextColumn("Member"),
                "ticker": st.column_config.TextColumn("Asset Ticker"),
                "action": st.column_config.TextColumn("Action"),
                "shares": st.column_config.NumberColumn("Shares", format="%.4f"),
                "price": st.column_config.NumberColumn("Execution Price", format="$%.2f"),
                "Total Amount": st.column_config.NumberColumn("Transaction Value", format="$%,.2f"),
            },
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No trades have been recorded in the journal yet.")


# ------------------------------------------
# TAB 5: MODEL PORTFOLIO
# ------------------------------------------
with tab_model:
    st.header("Official Model Portfolio")
    st.markdown(
        "The Model Portfolio is a deterministic benchmark representing what would happen "
        "if an investor followed the model's signal-based allocations exactly. "
        "It only changes when explicitly rebalanced."
    )

    model_data = load_model_portfolio()
    model_positions = model_data.get("positions", {})
    model_cash = float(model_data.get("cash", 0.0))
    model_initial = float(model_data.get("initial_value", 10000.0))
    model_last_rebal = model_data.get("last_rebalance", "Never")

    model_state = PortfolioState(cash=model_cash, holdings=model_positions)

    model_tickers = set(model_positions.keys())
    model_target_tickers = set(target_weights_df[target_weights_df["Ticker"] != CASH_LABEL]["Ticker"])
    all_model_tickers = model_tickers | model_target_tickers
    model_prices = fetch_current_prices(all_model_tickers) if all_model_tickers else {}

    model_total_value = calculate_portfolio_value(model_state, model_prices)
    model_return_pct = calculate_portfolio_return(model_state, model_prices, model_initial)
    model_cash_pct = (model_cash / model_total_value * 100) if model_total_value > 0 else 0.0

    # Overview Metrics
    st.subheader("Portfolio Overview")
    ov_cols = st.columns(4)
    with ov_cols[0]:
        st.metric("Current Value", f"${model_total_value:,.2f}")
    with ov_cols[1]:
        st.metric("Return", f"{model_return_pct:.2f}%")
    with ov_cols[2]:
        st.metric("Cash %", f"{model_cash_pct:.1f}%")
    with ov_cols[3]:
        st.metric("Last Rebalanced", model_last_rebal)

    # Rebalance Controls
    st.divider()
    needs_rebal = needs_rebalance_model_portfolio()

    if needs_rebal:
        st.warning(
            "The model's current positions do not match the latest target portfolio. "
            "A rebalance is recommended."
        )

    if st.button("Rebalance Model Portfolio", key="rebalance_model_btn", use_container_width=True):
        rebalance_model_portfolio()
        st.success("Model Portfolio has been rebalanced to match the latest target allocations.")
        st.rerun()

    st.divider()

    # Current Holdings Table
    st.subheader("Current Holdings")
    if model_positions:
        model_pos_df = calculate_position_values(model_state, model_prices)
        if not model_pos_df.empty:
            model_pos_df["Weight"] = model_pos_df["Value"] / model_total_value if model_total_value > 0 else 0.0

            # Merge target weights
            target_map = {}
            for _, r in target_weights_df.iterrows():
                if r["Ticker"] != CASH_LABEL:
                    target_map[str(r["Ticker"])] = float(r["Target Weight"])

            model_pos_df["Target Weight"] = model_pos_df["Ticker"].map(target_map).fillna(0.0)

            st.dataframe(
                model_pos_df[["Ticker", "Shares", "Price", "Value", "Weight", "Target Weight"]],
                column_config={
                    "Ticker": st.column_config.TextColumn(),
                    "Shares": st.column_config.NumberColumn(format="%.4f"),
                    "Price": st.column_config.NumberColumn(format="$%.2f"),
                    "Value": st.column_config.NumberColumn(format="$%,.2f"),
                    "Weight": st.column_config.NumberColumn(format="%.2f%%"),
                    "Target Weight": st.column_config.NumberColumn(format="%.2f%%"),
                },
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No position data available.")
    else:
        st.info("The model portfolio has no positions. Click 'Rebalance Model Portfolio' to initialize.")

    # Target Allocations
    st.subheader("Target Allocations")
    st.dataframe(
        target_weights_df[["Ticker", "Target Weight"]],
        column_config={
            "Ticker": st.column_config.TextColumn(),
            "Target Weight": st.column_config.NumberColumn(format="%.2f%%"),
        },
        use_container_width=True,
        hide_index=True,
    )

    # Allocation Charts
    st.subheader("Allocation Comparison")
    model_chart_cols = st.columns(2)

    with model_chart_cols[0]:
        st.caption("Current Model Allocation")
        if model_positions and not model_pos_df.empty:
            chart_data = model_pos_df[["Ticker", "Weight"]].rename(columns={"Weight": "weight"}).copy()
            if model_cash_pct > 0:
                chart_data = pd.concat(
                    [chart_data, pd.DataFrame([{"Ticker": CASH_LABEL, "weight": model_cash / model_total_value}])],
                    ignore_index=True,
                )
            st.vega_lite_chart(chart_data, {
                "mark": {"type": "arc", "tooltip": True},
                "encoding": {"theta": {"field": "weight", "type": "quantitative"}, "color": {"field": "Ticker", "type": "nominal"}},
            }, use_container_width=True)
        else:
            st.info("No allocation data to display.")

    with model_chart_cols[1]:
        st.caption("Target Model Allocation")
        target_chart = target_weights_df.rename(columns={"Target Weight": "weight"})
        st.vega_lite_chart(target_chart, {
            "mark": {"type": "arc", "tooltip": True},
            "encoding": {"theta": {"field": "weight", "type": "quantitative"}, "color": {"field": "Ticker", "type": "nominal"}},
        }, use_container_width=True)

    st.divider()

    # Decision Explanations
    st.subheader("Position Decision Explanations")
    st.markdown(
        "Each position is explained using rule-based factor analysis. "
        "Rankings are derived from computed ROE, Momentum, and PE scores."
    )

    explanation_tickers = list(model_positions.keys()) if model_positions else list(model_target_tickers)

    if explanation_tickers:
        explanation_rows = []
        for ticker in explanation_tickers:
            expl = generate_decision_explanation(ticker, signals_df)
            explanation_rows.append({
                "Ticker": ticker,
                "Overall Rank": expl["rank"],
                "Score": expl["score"],
                "ROE Rank": expl["roe_rank"],
                "Momentum Rank": expl["mom_rank"],
                "PE Rank": expl["pe_rank"],
                "Explanation": expl["explanation"],
            })

        expl_df = pd.DataFrame(explanation_rows)
        st.dataframe(expl_df, use_container_width=True, hide_index=True)
    else:
        st.info("No positions to explain. Rebalance the model portfolio first.")

    st.divider()

    # Performance History Chart
    st.subheader("Model Portfolio Value Over Time")
    model_history = load_model_portfolio_history()

    if model_history:
        model_hist_df = pd.DataFrame(model_history)
        st.line_chart(model_hist_df, x="date", y="portfolio_value", use_container_width=True)

        st.subheader("Model Return")
        st.metric("Cumulative Model Return", f"{model_return_pct:.2f}%")
    else:
        st.info("No historical data recorded yet. Rebalance the model portfolio to start tracking.")

    st.divider()

    # Model Change Log
    st.subheader("Model Change Log")
    st.markdown("Tracks all position changes made during rebalancing events.")

    changes = load_model_changes()

    if changes:
        changes_df = pd.DataFrame(changes)
        st.dataframe(
            changes_df.sort_values("date", ascending=False) if "date" in changes_df.columns else changes_df,
            column_config={
                "date": st.column_config.TextColumn("Date"),
                "action": st.column_config.TextColumn("Action"),
                "ticker": st.column_config.TextColumn("Ticker"),
            },
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No model changes have been recorded yet.")
