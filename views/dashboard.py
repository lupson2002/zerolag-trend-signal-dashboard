"""Main dashboard page: strategy performance + today's position.

Runs the ZeroLag engine live (yfinance download -> indicators -> state machine
-> backtest) and renders equity/drawdown/stats/yearly charts with plotly.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

sys.path.insert(0, str(Path(__file__).parent.parent))

import config as C
import engine

COPPER = "#bb6b2c"
COPPER_DIM = "#d3a578"
SLATE = "#3d5a73"
GOOD = "#2f7d4f"
BAD = "#b0442f"


@st.cache_data(ttl=3600)
def run_engine(_version: str = "v2"):
    data = engine.load_data()
    master = engine.build_master(data)
    df, info = engine.run_strategy(master)
    return df, info


def equity_curve(ret):
    return (1 + ret).cumprod()


def drawdown_of(eq):
    return eq / eq.cummax() - 1


def perf_stats(ret, eq):
    n_years = len(ret) / 252
    cagr = eq.iloc[-1] ** (1 / n_years) - 1
    vol = ret.std() * np.sqrt(252)
    sharpe = (ret.mean() * 252) / vol
    mdd = drawdown_of(eq).min()
    return {"CAGR": cagr, "Vol": vol, "Sharpe": sharpe, "MaxDD": mdd, "Multiple": eq.iloc[-1]}


def yearly_returns(ret):
    return ret.groupby(ret.index.year).apply(lambda r: (1 + r).prod() - 1)


st.markdown("<style>div.block-container { padding-top: 2.6rem; }</style>", unsafe_allow_html=True)

R = C.REGIME_TICKER
ATTACK = C.ATTACK_TICKERS[0]

try:
    df, info = run_engine()
except Exception as e:
    st.error(f"엔진 실행 실패: {e}")
    st.stop()

# ★ 방어적 폴백: 낡은 캐시/데이터로 {R}_RetClose 같은 파생 컬럼이 없어도
#   KeyError 로 화면 전체가 죽지 않도록 벤치마크 수익률을 직접 산출한다.
if f"{R}_RetClose" not in df.columns:
    df[f"{R}_RetClose"] = df[f"{R}_Close"].pct_change()
if f"{ATTACK}_RetClose" not in df.columns:
    df[f"{ATTACK}_RetClose"] = df[f"{ATTACK}_Close"].pct_change()
if "Strategy_Return" not in df.columns:
    df["Strategy_Return"] = 0.0

strat_ret = df["Strategy_Return"].fillna(0)
qqq_ret = df[f"{R}_RetClose"].fillna(0)
qld_ret = df[f"{ATTACK}_RetClose"].fillna(0)

strat_eq = equity_curve(strat_ret)
qqq_eq = equity_curve(qqq_ret)
qld_eq = equity_curve(qld_ret)

strat_stats = perf_stats(strat_ret, strat_eq)
qqq_stats = perf_stats(qqq_ret, qqq_eq)
qld_stats = perf_stats(qld_ret, qld_eq)

strat_yearly = yearly_returns(strat_ret)
qqq_yearly = yearly_returns(qqq_ret)

target_today = str(df["Target_Asset"].iloc[-1]) if pd.notna(df["Target_Asset"].iloc[-1]) else C.INIT_ASSET
last_close_date = str(df.index[-1].date())
reason = engine.build_reason(info)

st.markdown(
    f"""
    <div style="background:#f7f8f4;border:1px solid #e1e0d9;border-radius:10px;padding:16px 20px;margin-bottom:14px">
    <div style="font-size:13px;color:#52564d">오늘 아침 한국장 실행 포지션 · 기준종가 {last_close_date}</div>
    <div style="font-size:26px;font-weight:700;color:#bb6b2c;margin:4px 0 6px">▶ {target_today}</div>
    <div style="font-size:13px;color:#52564d">📌 {reason}</div>
    </div>
    """,
    unsafe_allow_html=True,
)

tab_chart, tab_stats, tab_yearly, tab_holdings = st.tabs(
    ["그래프", "통계표", "연도별 수익률", "보유 자산"]
)

with tab_chart:
    fig1 = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3], vertical_spacing=0.06)
    fig1.add_trace(go.Scatter(x=qqq_eq.index, y=qqq_eq, name="QQQ", line=dict(color=SLATE, width=2)), row=1, col=1)
    fig1.add_trace(go.Scatter(x=qld_eq.index, y=qld_eq, name="QLD (2x)", line=dict(color=COPPER_DIM, width=1.4, dash="dot")), row=1, col=1)
    fig1.add_trace(go.Scatter(x=strat_eq.index, y=strat_eq, name="ZeroLag Strategy", line=dict(color=COPPER, width=2)), row=1, col=1)
    fig1.update_yaxes(type="log", title="growth of $1", row=1, col=1)

    qqq_dd, strat_dd = drawdown_of(qqq_eq), drawdown_of(strat_eq)
    fig1.add_trace(go.Scatter(x=qqq_dd.index, y=qqq_dd * 100, line=dict(color=SLATE, width=1), fill="tozeroy", fillcolor="rgba(61,90,115,0.15)", showlegend=False), row=2, col=1)
    fig1.add_trace(go.Scatter(x=strat_dd.index, y=strat_dd * 100, line=dict(color=COPPER, width=1), fill="tozeroy", fillcolor="rgba(187,107,44,0.18)", showlegend=False), row=2, col=1)
    fig1.update_yaxes(title="drawdown %", row=2, col=1)
    fig1.update_layout(height=560, margin=dict(l=10, r=10, t=10, b=10), legend=dict(orientation="h", yanchor="bottom", y=1.02), hovermode="x unified", plot_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig1, width="stretch")

with tab_stats:
    metric_order = ["CAGR", "Vol", "Sharpe", "MaxDD", "Multiple"]

    def fmt_metric(name, v):
        if name == "Sharpe":
            return f"{v:.2f}"
        if name == "Multiple":
            return f"${v:.1f}"
        return f"{v:.1%}"

    stats_df = pd.DataFrame({
        "QQQ": {k: fmt_metric(k, qqq_stats[k]) for k in metric_order},
        "QLD (2x)": {k: fmt_metric(k, qld_stats[k]) for k in metric_order},
        "ZeroLag Strategy": {k: fmt_metric(k, strat_stats[k]) for k in metric_order},
    })
    st.dataframe(stats_df, width="stretch")

with tab_yearly:
    years = sorted(strat_yearly.index)
    yearly_df = pd.DataFrame({
        "연도": years,
        "QQQ": [qqq_yearly.get(y, 0) * 100 for y in years],
        "ZeroLag Strategy": [strat_yearly.get(y, 0) * 100 for y in years],
    })
    yearly_df["초과수익"] = yearly_df["ZeroLag Strategy"] - yearly_df["QQQ"]

    def color_excess(v):
        return f"color: {GOOD}" if v >= 0 else f"color: {BAD}"

    st.dataframe(
        yearly_df.style.format({c: "{:.1f}%" for c in yearly_df.columns if c != "연도"}).map(color_excess, subset=["초과수익"]),
        width="stretch", hide_index=True,
    )

with tab_holdings:
    st.markdown("#### 전략 유니버스")
    st.markdown(
        f"""
        - **레짐 필터**: {R} 종가 ≥ ZLEMA({C.LENGTH_IN}) → 공격 국면
        - **공격 자산**: {', '.join(C.ATTACK_TICKERS)} (2배 레버리지 + 현금)
        - **방어 자산**: {', '.join(C.DEFENSE_TICKERS)} — {C.MOM_WINDOW}일 모멘텀 로테이션
        - **샹들리에 청산**: ATR({C.LENGTH_OUT}, {C.MULT_OUT}) 추적 손절선
        - **수수료**: 왕복 {C.FEE_RATE * 2:.2%} (자산 전환일 차감)
        """
    )
    st.caption("백테스트 기간: 2016-01-01 ~ 오늘 · 1-Day Lag(룩어헤드 차단) 적용")
