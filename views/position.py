"""현재 포지션 페이지 — 오늘 시점 계산 + 최근 결정 근거."""

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

import config as C
import engine

TICKER_KR = {
    "QLD": "나스닥100 2배",
    "USD": "현금",
    "TLT": "장기국채",
    "BIL": "초단기국채",
    "USO": "원유",
    "GLD": "금",
}


def asset_label(t):
    return f"{t} ({TICKER_KR.get(t, t)})"


st.markdown("<style>div.block-container { padding-top: 2.6rem; }</style>", unsafe_allow_html=True)

st.markdown(
    """
    <style>
    .ic-pos-card { background:#f7f8f4; border:1px solid #e1e0d9; border-radius:10px; padding:18px 20px; }
    .ic-pos-title { font-size:15px; font-weight:600; color:#16191a; }
    .ic-pos-regime { font-size:13px; color:#52564d; margin:6px 0 10px; }
    .ic-pos-asset { font-size:22px; font-weight:700; color:#bb6b2c; }
    .ic-pos-note { font-size:12px; color:#898781; margin-top:10px; }
    </style>
    """,
    unsafe_allow_html=True,
)

@st.cache_data(ttl=3600)
def run_engine_cached():
    data = engine.load_data()
    master = engine.build_master(data)
    df, info = engine.run_strategy(master)
    return df, info


try:
    df, info = run_engine_cached()
except Exception as e:
    st.error(f"엔진 실행 실패: {e}")
    st.stop()

R = C.REGIME_TICKER
target_today = str(df["Chosen_Asset"].iloc[-1]) if pd.notna(df["Chosen_Asset"].iloc[-1]) else C.INIT_ASSET
last_close_date = str(df.index[-1].date())
reason = engine.build_reason(info)

regime_word = "공격 국면" if info.get("is_bull") else "방어 국면"

st.title("현재 포지션")

col1, col2 = st.columns(2)

with col1:
    st.markdown(
        f"""
        <div class="ic-pos-card">
        <div class="ic-pos-title">📅 최근 결정 ({last_close_date})</div>
        <div class="ic-pos-regime">{regime_word}</div>
        <div class="ic-pos-asset">{asset_label(target_today)}</div>
        <div class="ic-pos-note">새벽 미국장 종가 기준 시그널 → 오늘 아침 한국장 시가 진입</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with col2:
    st.markdown(
        f"""
        <div class="ic-pos-card">
        <div class="ic-pos-title">🔄 오늘 시점 계산</div>
        <div class="ic-pos-regime">{regime_word} (완충지대 유지)</div>
        <div class="ic-pos-asset">{asset_label(target_today)}</div>
        <div class="ic-pos-note">최신 데이터 기준 실시간 신호</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.info(f"📌 선정 근거: {reason}")

st.markdown("")
st.markdown("#### 신호 세부")
signals_detail = pd.DataFrame({
    "레짐": [regime_word],
    "기준종가일": [last_close_date],
    "실행 포지션": [target_today],
    "ZLEMA 윈도우": [C.LENGTH_IN],
    "모멘텀 주기": [C.MOM_WINDOW],
    "샹들리에": [f"ATR({C.LENGTH_OUT}, {C.MULT_OUT})"],
})
st.dataframe(signals_detail, width="stretch", hide_index=True)

st.markdown("")
st.markdown("#### 최근 보유 자산 히스토리 (최근 30거래일)")
recent = df[["Chosen_Asset", "Target_Asset"]].tail(30)
recent = recent.rename(columns={"Chosen_Asset": "시그널 자산", "Target_Asset": "실행 자산"})
recent.index = recent.index.strftime("%Y-%m-%d")
st.dataframe(recent, width="stretch")

st.markdown("")
st.markdown("#### 전략 유니버스")
st.markdown(
    f"""
    - **레짐 필터**: {R} 종가 ≥ ZLEMA({C.LENGTH_IN}) → 공격 국면
    - **공격 자산**: {', '.join(C.ATTACK_TICKERS)}
    - **방어 자산**: {', '.join(C.DEFENSE_TICKERS)} — {C.MOM_WINDOW}일 모멘텀 로테이션
    - **샹들리에 청산**: ATR({C.LENGTH_OUT}, {C.MULT_OUT}) 추적 손절선
    - **수수료**: 왕복 {C.FEE_RATE * 2:.2%} (자산 전환일 차감)
    """
)
