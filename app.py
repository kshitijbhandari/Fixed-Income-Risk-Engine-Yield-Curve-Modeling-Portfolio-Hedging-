import os
from dotenv import load_dotenv
load_dotenv()
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from fredapi import Fred

# ── Page Config ────────────────────────────────────────────────
st.set_page_config(
    page_title="Yield Curve Risk Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Constants ──────────────────────────────────────────────────
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

TENORS = ["1mo","3mo","6mo","1yr","2yr","3yr","5yr","7yr","10yr","20yr","30yr"]
TAUS   = [1/12, 3/12, 6/12, 1, 2, 3, 5, 7, 10, 20, 30]
TENOR_MAP = {
    "1mo":"DGS1MO","3mo":"DGS3MO","6mo":"DGS6MO","1yr":"DGS1",
    "2yr":"DGS2","3yr":"DGS3","5yr":"DGS5","7yr":"DGS7",
    "10yr":"DGS10","20yr":"DGS20","30yr":"DGS30",
}
BUCKETS = {
    "0-3yr":  ["2yr_2pct","2yr_4pct"],
    "3-7yr":  ["5yr_3pct","5yr_5pct","7yr_3pct","7yr_4pct"],
    "7-15yr": ["10yr_3pct","10yr_5pct"],
    "15yr+":  ["20yr_4pct","20yr_5pct","30yr_3pct","30yr_4pct"],
}
HEDGE_SPECS = {
    "S1: Duration": {"contracts":{"TY":285},                        "cost":285*80},
    "S2: KRD":      {"contracts":{"TU":32,"FV":59,"TY":79,"US":32}, "cost":32*20+59*42+79*80+32*155},
    "S4: Combined": {"contracts":{"TU":51,"FV":93,"TY":125,"US":51},"cost":51*20+93*42+125*80+51*155},
}
STRAT_COLORS = {"Unhedged":"#d62728","S1":"#1f77b4","S2":"#2ca02c","S4":"#9467bd"}

# ── Data Loading ───────────────────────────────────────────────
@st.cache_data
def load_data():
    portfolio  = pd.read_csv(f"{DATA_DIR}/portfolio.csv",           index_col="label")
    krd        = pd.read_csv(f"{DATA_DIR}/krd.csv",                 index_col="bond")
    pnl_df     = pd.read_csv(f"{DATA_DIR}/scenario_pnl.csv",        index_col="scenario")
    moves      = pd.read_csv(f"{DATA_DIR}/scenario_moves.csv",      index_col="scenario")
    hedged_df  = pd.read_csv(f"{DATA_DIR}/hedged_pnl.csv",          index_col="scenario")
    eff_df     = pd.read_csv(f"{DATA_DIR}/hedge_effectiveness.csv", index_col="scenario")
    base_curve = pd.read_csv(f"{DATA_DIR}/base_curve.csv",          index_col=0).iloc[:, 0]
    yields_raw = pd.read_csv(f"{DATA_DIR}/yields_raw.csv",          index_col="date", parse_dates=True)
    ns_params  = pd.read_csv(f"{DATA_DIR}/ns_params.csv",           index_col="date", parse_dates=True)
    return portfolio, krd, pnl_df, moves, hedged_df, eff_df, base_curve, yields_raw, ns_params

# ── Utility Functions ──────────────────────────────────────────
def pnl_approx(portfolio, bps_shift):
    """Duration-convexity P&L approximation for a parallel shift."""
    dy = bps_shift / 10000
    return portfolio.apply(
        lambda r: (-r["mod_dur"] * dy + 0.5 * r["convexity"] * dy**2) * r["price"],
        axis=1,
    )

def fetch_fred_latest():
    """Fetch latest rates from FRED. Returns (DataFrame, error_str)."""
    api_key = os.environ.get("FRED_API_KEY", "")
    if not api_key:
        return None, "FRED_API_KEY environment variable not set."
    try:
        fred   = Fred(api_key=api_key)
        frames = {}
        for label, sid in TENOR_MAP.items():
            s = fred.get_series(sid, observation_start="2025-01-01")
            frames[label] = s
        df = pd.DataFrame(frames)
        df.index.name = "date"
        return df, None
    except Exception as e:
        return None, str(e)

# ── Load & Derive ──────────────────────────────────────────────
portfolio, krd, pnl_df, moves, hedged_df, eff_df, base_curve, yields_raw, ns_params = load_data()

port_price = portfolio["price"].sum()
port_dv01  = portfolio["dv01"].sum()
port_dur   = (portfolio["mod_dur"] * portfolio["price"]).sum() / port_price
port_conv  = (portfolio["convexity"] * portfolio["price"]).sum() / port_price
port_krd   = (krd.T * portfolio["price"]).sum(axis=1) / port_price
all_sc     = [s for s in hedged_df.index if not s.startswith("mc_")]
last_date  = yields_raw.index[-1].strftime("%Y-%m-%d")

# ── Sidebar ────────────────────────────────────────────────────
with st.sidebar:
    st.title("📈 Yield Curve Risk")
    st.divider()
    st.metric("Data as of",       last_date)
    st.metric("Portfolio Value",  f"${port_price/1e6:.2f}M")
    st.metric("Total DV01",       f"${port_dv01:,.0f}")
    st.metric("Modified Duration",f"{port_dur:.2f} yr")
    st.divider()

    if st.button("🔄 Refresh from FRED", use_container_width=True):
        with st.spinner("Fetching latest rates from FRED…"):
            new_df, err = fetch_fred_latest()
        if err:
            st.error(f"Error: {err}")
        else:
            existing     = pd.read_csv(f"{DATA_DIR}/yields_raw.csv", index_col="date", parse_dates=True)
            new_rows     = new_df[new_df.index > existing.index[-1]]
            if len(new_rows) > 0:
                updated = pd.concat([existing, new_rows])
                updated.to_csv(f"{DATA_DIR}/yields_raw.csv")
                # Update base curve to most recent complete row
                latest = new_df.dropna().iloc[-1]
                pd.DataFrame({"yield": latest}).to_csv(f"{DATA_DIR}/base_curve.csv")
                st.success(f"Added {len(new_rows)} new row(s). Reloading…")
                st.cache_data.clear()
                st.rerun()
            else:
                st.info("Already up to date.")

# ── Header ─────────────────────────────────────────────────────
st.title("US Treasury Yield Curve Risk Dashboard")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Portfolio Value",   f"${port_price/1e6:.2f}M")
c2.metric("Modified Duration", f"{port_dur:.2f} yr")
c3.metric("Total DV01",        f"${port_dv01:,.0f}")
c4.metric("Convexity",         f"{port_conv:.2f}")
st.divider()

# ── Tabs ───────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📉 Live Curve",
    "📊 Portfolio Risk",
    "⚡ Stress Test",
    "🛡️ Hedging",
    "💰 Cost Analysis",
])

# ════════════════════════════════════════════════════
# TAB 1 — LIVE YIELD CURVE
# ════════════════════════════════════════════════════
with tab1:
    st.subheader("Current US Treasury Yield Curve")
    col_chart, col_table = st.columns([3, 1])

    with col_chart:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=TAUS, y=base_curve.values,
            mode="lines+markers",
            name=f"Today ({last_date})",
            line=dict(color="#1f77b4", width=3),
            marker=dict(size=8),
        ))
        for label, lookback in [("1yr ago", 252), ("2yr ago", 504), ("5yr ago", 1260)]:
            idx = max(0, len(yields_raw) - lookback)
            row = yields_raw.iloc[idx].reindex(TENORS)
            if row.notna().sum() >= 8:
                fig.add_trace(go.Scatter(
                    x=TAUS, y=row.values,
                    mode="lines", name=label,
                    line=dict(dash="dot", width=1.5), opacity=0.55,
                ))
        fig.update_layout(
            title="US Treasury Spot Curve",
            xaxis_title="Maturity (years)",
            yaxis_title="Yield (%)",
            height=380,
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )
        st.plotly_chart(fig, use_container_width=True)

    with col_table:
        st.markdown("**Current Rates**")
        tbl = pd.DataFrame({"Tenor": TENORS, "Yield": [f"{v:.2f}%" for v in base_curve.values]})
        st.dataframe(tbl, hide_index=True, height=360)

    st.subheader("Yield History")
    sel_tenors = st.multiselect("Tenors", TENORS, default=["2yr","5yr","10yr","30yr"])
    lookback_yr = st.slider("Lookback (years)", 1, 10, 5)
    start = yields_raw.index[-1] - pd.DateOffset(years=lookback_yr)
    hist  = yields_raw[yields_raw.index >= start][sel_tenors]

    fig2 = go.Figure()
    for t in sel_tenors:
        fig2.add_trace(go.Scatter(x=hist.index, y=hist[t], name=t, mode="lines", line=dict(width=1.5)))
    fig2.update_layout(
        title="Treasury Yields Over Time",
        xaxis_title="Date", yaxis_title="Yield (%)",
        height=340, hovermode="x unified",
    )
    st.plotly_chart(fig2, use_container_width=True)

    st.subheader("Nelson-Siegel Factors")
    st.caption("β₀ = Level (long-run rate)  |  β₁ = Slope  |  β₂ = Curvature (hump)")
    ns_hist = ns_params[ns_params.index >= start]
    fig3 = make_subplots(rows=3, cols=1, shared_xaxes=True,
                          subplot_titles=["β₀ — Level","β₁ — Slope","β₂ — Curvature"])
    for i, (col, color) in enumerate(zip(["beta0","beta1","beta2"],
                                          ["#1f77b4","#ff7f0e","#2ca02c"]), 1):
        fig3.add_trace(go.Scatter(x=ns_hist.index, y=ns_hist[col],
                                   name=col, line=dict(color=color, width=1.2)), row=i, col=1)
    fig3.update_layout(height=430, showlegend=False)
    st.plotly_chart(fig3, use_container_width=True)

# ════════════════════════════════════════════════════
# TAB 2 — PORTFOLIO RISK
# ════════════════════════════════════════════════════
with tab2:
    st.subheader("Portfolio Constituents")
    disp = portfolio[["coupon","face","maturity","price","mod_dur","dv01","convexity"]].copy()
    disp["coupon"] = (disp["coupon"] * 100).map("{:.2f}%".format)
    disp["face"]   = disp["face"].map("${:,.0f}".format)
    disp["price"]  = disp["price"].map("${:,.0f}".format)
    disp["dv01"]   = disp["dv01"].map("${:,.0f}".format)
    disp.columns   = ["Coupon","Face","Maturity (yr)","Price","Mod Dur","DV01","Convexity"]
    st.dataframe(disp, use_container_width=True)

    st.divider()
    col1, col2 = st.columns(2)

    with col1:
        bucket_dv01 = {b: portfolio.loc[labels,"dv01"].sum() for b, labels in BUCKETS.items()}
        fig = go.Figure(go.Bar(
            x=list(bucket_dv01.keys()), y=list(bucket_dv01.values()),
            marker_color=["#1f77b4","#ff7f0e","#2ca02c","#d62728"],
            text=[f"${v:,.0f}" for v in bucket_dv01.values()],
            textposition="outside",
        ))
        fig.update_layout(title="DV01 by Maturity Bucket ($ per 1bp)", yaxis_title="DV01 ($)", height=360)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        fig = go.Figure(go.Pie(
            labels=list(bucket_dv01.keys()),
            values=list(bucket_dv01.values()),
            hole=0.35,
            marker_colors=["#1f77b4","#ff7f0e","#2ca02c","#d62728"],
        ))
        fig.update_layout(title="DV01 Concentration", height=360)
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Key Rate Duration Profile")
    krd_plot = port_krd[["1yr","2yr","3yr","5yr","7yr","10yr","20yr","30yr"]]
    fig = go.Figure(go.Bar(
        x=krd_plot.index.tolist(), y=krd_plot.values,
        marker_color="#1f77b4",
        text=[f"{v:.2f}" for v in krd_plot.values],
        textposition="outside",
    ))
    fig.update_layout(
        title="Key Rate Duration — Rate Sensitivity at Each Tenor",
        xaxis_title="Tenor", yaxis_title="KRD (years)", height=360,
    )
    st.plotly_chart(fig, use_container_width=True)

# ════════════════════════════════════════════════════
# TAB 3 — STRESS TEST
# ════════════════════════════════════════════════════
with tab3:
    st.subheader("Predefined Stress Scenarios")
    col1, col2 = st.columns([3, 1])
    with col1:
        sel_sc = st.multiselect("Select scenarios", all_sc, default=all_sc)
    with col2:
        sort_opt = st.selectbox("Sort", ["Worst → Best","Best → Worst","Alphabetical"])

    if sel_sc:
        pnl_sel = pnl_df.loc[sel_sc, "total"].copy()
        if sort_opt == "Worst → Best":
            pnl_sel = pnl_sel.sort_values()
        elif sort_opt == "Best → Worst":
            pnl_sel = pnl_sel.sort_values(ascending=False)
        else:
            pnl_sel = pnl_sel.sort_index()

        fig = go.Figure(go.Bar(
            x=pnl_sel.values / 1e3,
            y=pnl_sel.index.tolist(),
            orientation="h",
            marker_color=["#d62728" if v < 0 else "#2ca02c" for v in pnl_sel.values],
            text=[f"{'−' if v<0 else '+'}${abs(v)/1e3:.1f}K" for v in pnl_sel.values],
            textposition="outside",
        ))
        fig.update_layout(
            title="Unhedged Portfolio P&L by Scenario",
            xaxis_title="P&L ($K)",
            height=max(320, len(sel_sc) * 28 + 80),
        )
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("Rate Moves vs Base Curve (bps)")
        moves_sel = moves.loc[sel_sc].astype(float)
        fig = go.Figure(go.Heatmap(
            z=moves_sel.values,
            x=moves_sel.columns.tolist(),
            y=moves_sel.index.tolist(),
            colorscale="RdBu_r", zmid=0,
            text=moves_sel.values.round(0).astype(int),
            texttemplate="%{text}",
            colorbar=dict(title="bps"),
        ))
        fig.update_layout(
            title="Rate Moves by Scenario and Tenor",
            height=max(320, len(sel_sc) * 25 + 80),
        )
        st.plotly_chart(fig, use_container_width=True)

    st.divider()
    st.subheader("Custom Parallel Shift")
    st.caption("Duration-convexity approximation. Accurate for moves ≤ 200bps.")

    custom_bps = st.slider("Parallel shift (bps)", -500, 500, 0, step=25)
    if custom_bps != 0:
        cpnl  = pnl_approx(portfolio, custom_bps)
        total = cpnl.sum()
        c1, c2, c3 = st.columns(3)
        c1.metric("Total P&L",    f"${total/1e3:,.1f}K",
                  delta=f"{total/port_price*100:.2f}% of AUM")
        c2.metric("DV01 impact",  f"${port_dv01*abs(custom_bps)/1e3:,.1f}K")
        c3.metric("Shift applied",f"{'+' if custom_bps>0 else ''}{custom_bps} bps")

        fig = go.Figure(go.Bar(
            x=cpnl.index.tolist(),
            y=cpnl.values / 1e3,
            marker_color=["#d62728" if v < 0 else "#2ca02c" for v in cpnl.values],
            text=[f"${v/1e3:.1f}K" for v in cpnl.values],
            textposition="outside",
        ))
        fig.update_layout(
            title=f"P&L by Bond — {custom_bps:+d} bps",
            xaxis_title="Bond", yaxis_title="P&L ($K)", height=350,
        )
        st.plotly_chart(fig, use_container_width=True)

# ════════════════════════════════════════════════════
# TAB 4 — HEDGING
# ════════════════════════════════════════════════════
with tab4:
    st.subheader("Hedge Strategy Comparison")
    c1, c2, c3 = st.columns(3)
    c1.info("**S1: Duration Neutral**\n285 TY contracts\nZeros out total DV01\nStrong on parallel moves")
    c2.info("**S2: KRD Spread**\nTU + FV + TY + US\nMatches key rate durations\nStrong on curve shapes")
    c3.success("**S4: Combined** ✓ Recommended\nFull KRD mix at DV01 scale\nBest of both worlds\n80.4% avg effectiveness")

    st.subheader("Effectiveness Heatmap (%)")
    sel_strats = st.multiselect(
        "Strategies to display",
        ["S1: Duration","S2: KRD","S4: Combined"],
        default=["S1: Duration","S2: KRD","S4: Combined"],
    )
    col_map = {"S1: Duration":"s1_eff_%","S2: KRD":"s2_eff_%","S4: Combined":"s4_eff_%"}

    if sel_strats:
        eff_sel = eff_df.loc[all_sc, [col_map[s] for s in sel_strats]].copy()
        eff_sel.columns = sel_strats
        fig = go.Figure(go.Heatmap(
            z=eff_sel.values,
            x=eff_sel.columns.tolist(),
            y=eff_sel.index.tolist(),
            colorscale="RdYlGn", zmin=0, zmax=100,
            text=eff_sel.values.round(1),
            texttemplate="%{text}%",
            colorbar=dict(title="Effectiveness %"),
        ))
        fig.update_layout(
            title="Hedge Effectiveness — Green is Good",
            height=max(320, len(all_sc) * 25 + 80),
        )
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Unhedged vs Hedged P&L")
    top_n = st.slider("Top N scenarios by impact", 5, len(all_sc), 10)
    top_sc = pnl_df.loc[all_sc,"total"].abs().nlargest(top_n).index.tolist()

    fig = go.Figure()
    for label, col in [("Unhedged","unhedged"),("S1","s1_hedged"),("S2","s2_hedged"),("S4","s4_hedged")]:
        fig.add_trace(go.Bar(
            name=label,
            x=top_sc,
            y=hedged_df.loc[top_sc, col] / 1e3,
            marker_color=STRAT_COLORS[label],
        ))
    fig.update_layout(
        barmode="group",
        title=f"P&L Comparison — Top {top_n} Most Impactful Scenarios",
        xaxis_title="Scenario", yaxis_title="P&L ($K)",
        height=420, xaxis_tickangle=-25,
    )
    st.plotly_chart(fig, use_container_width=True)

# ════════════════════════════════════════════════════
# TAB 5 — COST ANALYSIS
# ════════════════════════════════════════════════════
with tab5:
    st.subheader("Cost of Hedging")

    worst_sc_name = pnl_df.loc[all_sc,"total"].idxmin()
    worst_unh     = pnl_df.loc[worst_sc_name,"total"]
    protection    = {
        "S1": worst_unh - hedged_df.loc[worst_sc_name,"s1_hedged"],
        "S2": worst_unh - hedged_df.loc[worst_sc_name,"s2_hedged"],
        "S4": worst_unh - hedged_df.loc[worst_sc_name,"s4_hedged"],
    }

    c1, c2, c3 = st.columns(3)
    for col_w, (name, spec) in zip([c1,c2,c3], HEDGE_SPECS.items()):
        short = name.split(":")[0].strip()
        col_w.metric(
            name,
            f"${spec['cost']:,.0f}",
            delta=f"{spec['cost']/port_price*100:.4f}% of AUM",
        )

    st.divider()
    c1, c2, c3 = st.columns(3)

    with c1:
        fig = go.Figure(go.Bar(
            x=list(HEDGE_SPECS.keys()),
            y=[s["cost"] for s in HEDGE_SPECS.values()],
            marker_color=["#1f77b4","#2ca02c","#9467bd"],
            text=[f"${s['cost']:,.0f}" for s in HEDGE_SPECS.values()],
            textposition="outside",
        ))
        fig.update_layout(title="Transaction Cost", yaxis_title="$", height=360)
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        prot_vals = {s: abs(protection[s])/1e3 for s in ["S1","S2","S4"]}
        fig = go.Figure(go.Bar(
            x=list(prot_vals.keys()), y=list(prot_vals.values()),
            marker_color=["#1f77b4","#2ca02c","#9467bd"],
            text=[f"${v:,.0f}K" for v in prot_vals.values()],
            textposition="outside",
        ))
        fig.update_layout(
            title=f"Loss Avoided in Worst Scenario<br>({worst_sc_name})",
            yaxis_title="$K", height=360,
        )
        st.plotly_chart(fig, use_container_width=True)

    with c3:
        roh_map = {"S1":"S1: Duration","S2":"S2: KRD","S4":"S4: Combined"}
        roh_vals = {s: abs(protection[s]) / HEDGE_SPECS[roh_map[s]]["cost"] for s in ["S1","S2","S4"]}
        fig = go.Figure(go.Bar(
            x=list(roh_vals.keys()), y=list(roh_vals.values()),
            marker_color=["#1f77b4","#2ca02c","#9467bd"],
            text=[f"{v:.0f}x" for v in roh_vals.values()],
            textposition="outside",
        ))
        fig.update_layout(title="Return on Hedge Cost ($ saved / $ spent)", yaxis_title="x", height=360)
        st.plotly_chart(fig, use_container_width=True)

    st.divider()
    st.subheader("Bottom Line — Why S4?")
    s4_cost = HEDGE_SPECS["S4: Combined"]["cost"]
    s4_prot = abs(protection["S4"])
    st.markdown(f"""
| Metric | Value |
|---|---|
| Portfolio at risk | ${port_price/1e6:.1f}M |
| Worst case unhedged loss | ${worst_unh/1e3:,.1f}K &nbsp;({abs(worst_unh/port_price)*100:.1f}% of AUM) |
| S4 transaction cost | ${s4_cost:,.0f} &nbsp;({s4_cost/port_price*100:.4f}% of AUM) |
| Loss avoided with S4 | ${s4_prot/1e3:,.1f}K |
| Return on hedge cost | {s4_prot/s4_cost:.0f}x |
| S4 avg effectiveness | {eff_df["s4_eff_%"].mean():.1f}% across all {len(all_sc)} scenarios |
""")
