"""ZEROLAG TREND SIGNAL — 코어 연산 엔진 (노트북 백테스트 100% 준용).

흐름:
  1) yfinance 로 2016-01-01 ~ 오늘 전 유니버스 일괄 다운로드
  2) 지표 산출:
       - 정통 Ehlers ZLEMA(105) + 변동성 밴드 → 레짐 판별선(Upper_In)
       - 자산별 샹들리에 ATR(15) + 55일 모멘텀
  3) 포지션 유지형 상태머신 → 일별 Chosen_Asset
       - 레짐 전환 시에만 공격/방어 메인 군단 스위칭(모멘텀 max)
       - 보유 자산 개별 샹들리에 추적 손절선 붕괴 시 차순위 교체
  4) ★ 1-Day Lag(.shift(1)) → 룩어헤드 바이어스 차단
     (새벽 미국장 종가 확정 → 아침 한국장 시가 진입 모사)
  5) 왕복 수수료(0.0015×2) 차감 정산 → 성과 지표

주의: 시그널 연산은 종가 기준, 실행 포지션은 반드시 1일 시프트.
      "어제 마감 캔들" 기준 → "오늘 아침 최종 포지셔닝 자산" 반환.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass

import numpy as np
import pandas as pd
import yfinance as yf

import config as C

R = C.REGIME_TICKER


# ── 데이터 로드 ───────────────────────────────────────────────────

def load_data(tickers: list[str] | None = None,
              start: str | None = None) -> dict[str, pd.DataFrame]:
    """yfinance 일괄 다운로드 → {ticker: DataFrame(OHLCV)}.
    노트북과 동일: auto_adjust 미지정(최신 yfinance 기본 auto_adjust=True).
    """
    tickers = tickers or C.PRICE_TICKERS
    start = start or C.DATA_START
    end = _dt.date.today().isoformat()

    frames: dict[str, pd.DataFrame] = {}
    for t in tickers:
        df = yf.download(
            t, start=start, end=end,
            progress=False, threads=False,
        )
        if df is None or df.empty:
            raise RuntimeError(f"yfinance: {t} 데이터 수집 실패/빈 결과")
        # MultiIndex 컬럼 정리 (단일 티커도 (Price,Ticker) 형태 가능)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        frames[t] = df
    return frames


def build_master(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """개별 OHLC → 단일 DataFrame({TICKER}_Close/High/Low).
    노트북 yf.download(universe) 후 dropna() 동기화와 동일(공통 캘린더 교집합).
    """
    idx = data[C.REGIME_TICKER].index
    master = pd.DataFrame(index=idx)
    for t in C.PRICE_TICKERS:
        d = data[t].reindex(idx)
        master[f"{t}_Close"] = d["Close"]
        master[f"{t}_Open"] = d["Open"]
        master[f"{t}_High"] = d["High"]
        master[f"{t}_Low"] = d["Low"]
    return master.dropna()


# ── 지표 헬퍼 (노트북 그대로) ──────────────────────────────────────

def true_range(df: pd.DataFrame, asset: str) -> pd.Series:
    """Wilder True Range."""
    return pd.concat(
        [
            df[f"{asset}_High"] - df[f"{asset}_Low"],
            (df[f"{asset}_High"] - df[f"{asset}_Close"].shift(1)).abs(),
            (df[f"{asset}_Low"] - df[f"{asset}_Close"].shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)


# ── 시그널 산출 (노트북 run_k_universe_strategy 100% 준용) ─────────

def run_strategy(df: pd.DataFrame,
                 length_in: int = C.LENGTH_IN,
                 mult_in: float = C.MULT_IN,
                 length_out: int = C.LENGTH_OUT,
                 mult_out: float = C.MULT_OUT,
                 mom_window: int = C.MOM_WINDOW,
                 fee_rate: float = C.FEE_RATE) -> tuple[pd.DataFrame, dict]:
    """노트북 백테스트 로직 100% 준용. (df, last_day_info) 반환."""
    df = df.copy()
    size = len(df)
    attack = C.ATTACK_TICKERS
    defense = C.DEFENSE_TICKERS
    all_assets = C.ALL_TICKERS

    # 1. QQQ 기반 대세 상승장 판별선 (정통 Ehlers ZLEMA + 변동성 밴드)
    lag_in = int(np.floor((length_in - 1) / 2))
    src_adj_in = df[f"{R}_Close"] + (df[f"{R}_Close"] - df[f"{R}_Close"].shift(lag_in))
    df["ZLEMA_In"] = src_adj_in.ewm(span=length_in, adjust=False).mean()

    qqq_tr = true_range(df, R)
    df["QQQ_ATR"] = qqq_tr.ewm(alpha=1 / length_in, adjust=False).mean()
    df["QQQ_Vol"] = df["QQQ_ATR"].rolling(window=int(length_in * 3)).max() * mult_in
    # 상단 돌파 시 상승장 진입 / 하단 이탈 시 하락장 진입 (사이 구간은 이전 레짐 유지)
    df["Upper_In"] = df["ZLEMA_In"] + df["QQQ_Vol"]
    df["Lower_In"] = df["ZLEMA_In"]

    # 2. 공격 2종(QLD, USD) + 방어 4종(TLT, BIL, USO, GLD) 55일 모멘텀 + 샹들리에 ATR(15)
    attack_assets = attack
    def_assets = defense
    for asset in all_assets:
        df[f"{asset}_Mom"] = df[f"{asset}_Close"].pct_change(mom_window)
        asset_tr = true_range(df, asset)
        df[f"{asset}_ATR_Out"] = asset_tr.ewm(alpha=1 / length_out, adjust=False).mean()

    # 3. 상태 머신 시뮬레이션 (코랩 run_k_universe_strategy_v2 1:1 준용)
    chosen_assets: list[str] = []
    curr_asset: str = C.INIT_ASSET      # 'BIL'
    curr_regime: str = "BEAR"
    highest_high: float = 0.0
    last_info: dict = {}

    for i in range(size):
        qqq_close = df[f"{R}_Close"].iloc[i]
        upper_in = df["Upper_In"].iloc[i]
        lower_in = df["Lower_In"].iloc[i]

        if pd.isna(upper_in) or pd.isna(lower_in):
            chosen_assets.append(C.INIT_ASSET)
            continue

        # [A] 완충지대(Hysteresis) 적용 레짐 판단 — 잦은 핑퐁 매매 차단
        if qqq_close > upper_in:
            new_regime = "BULL"
        elif qqq_close < lower_in:
            new_regime = "BEAR"
        else:
            new_regime = curr_regime  # 기존 레짐 유지(완충지대)

        regime_changed = (new_regime != curr_regime)
        curr_regime = new_regime

        # 메타데이터(근거 문장용) — chosen_assets 결과에 영향 없음
        exited = False
        exited_from = None
        fallback_bil = False
        prev_curr = curr_asset

        # [B] 레짐 전환 시 자산 교체 (모멘텀 max) + highest_high 리셋
        if regime_changed:
            if curr_regime == "BULL":
                mom_scores = {a: df[f"{a}_Mom"].iloc[i] for a in attack_assets}
                curr_asset = max(mom_scores, key=mom_scores.get)
            else:
                # ★ 양수 모멘텀 필터: 양수 모멘텀 방어 자산만 후보, 없으면 현금(BIL) 대피
                pos = [a for a in def_assets
                       if pd.notna(df[f"{a}_Mom"].iloc[i]) and df[f"{a}_Mom"].iloc[i] > 0]
                if pos:
                    mom_scores = {a: df[f"{a}_Mom"].iloc[i] for a in pos}
                    curr_asset = max(mom_scores, key=mom_scores.get)
                else:
                    curr_asset = "BIL"
            highest_high = df[f"{curr_asset}_High"].iloc[i]

        else:
            # [C] 동일 레짐 내 샹들리에 손절선 검증
            asset_high = df[f"{curr_asset}_High"].iloc[i]
            asset_close = df[f"{curr_asset}_Close"].iloc[i]
            asset_atr = df[f"{curr_asset}_ATR_Out"].iloc[i]

            if asset_high > highest_high:
                highest_high = asset_high

            chandelier_line = highest_high - (asset_atr * mult_out)

            # 손절선 붕괴 시
            if asset_close < chandelier_line:
                exited_from = curr_asset
                exited = True
                if curr_regime == "BULL":
                    remains = [a for a in attack_assets if a != curr_asset]
                    alt_asset = remains[0] if remains else curr_asset

                    # 대안 자산도 손절 상태인지 확인
                    alt_high = df[f"{alt_asset}_High"].iloc[i]
                    alt_atr = df[f"{alt_asset}_ATR_Out"].iloc[i]
                    alt_close = df[f"{alt_asset}_Close"].iloc[i]

                    if alt_close < (alt_high - (alt_atr * mult_out)):
                        curr_asset = "BIL"  # 둘 다 위험하면 현금 대피
                        fallback_bil = True
                    else:
                        curr_asset = alt_asset
                else:
                    remains = [a for a in def_assets if a != curr_asset]
                    # ★ 양수 모멘텀 필터: 양수 모멘텀 자산만 후보, 없으면 현금(BIL) 대피
                    pos = [a for a in remains
                           if pd.notna(df[f"{a}_Mom"].iloc[i]) and df[f"{a}_Mom"].iloc[i] > 0]
                    if pos:
                        mom_scores = {a: df[f"{a}_Mom"].iloc[i] for a in pos}
                        curr_asset = max(mom_scores, key=mom_scores.get)
                    else:
                        curr_asset = "BIL"

                highest_high = df[f"{curr_asset}_High"].iloc[i]  # ★ 손절 교체 시에만 리셋(코랩 준용)

        # 마지막 날 결정 정보 캡처(근거 문장용)
        if i == size - 1:
            last_info = {
                "is_bull": curr_regime == "BULL",
                "regime": curr_regime,
                "curr": curr_asset,
                "switched": regime_changed,
                "sw_to_attack": regime_changed and curr_regime == "BULL",
                "exited": exited,
                "exited_from": exited_from,
                "fallback_bil": fallback_bil,
                "prev": prev_curr,
            }

        chosen_assets.append(curr_asset)

    df["Chosen_Asset"] = chosen_assets

    # ★ 1-Day Lag 처리 (새벽 미장 종가 확인 후 아침 국장 시가 체결 모사)
    df["Target_Asset"] = df["Chosen_Asset"].shift(1)

    # 4. 일별 수익률 합산 및 왕복 수수료 차감 정산
    # ★ 시가 진입 모델 (전일 종가 시그널 → 당일 시가 체결):
    #   - 전환일: 시그널 후 당일 시가에 새 자산 매수 → 당일 종가 청산
    #             수익률 = close[i] / open[i] − 1  (전일종가→당일시가 갭 미노출)
    #   - 유지일: 전일 종가 보유분 그대로 → close[i] / close[i-1] − 1
    for asset in [R, C.ATTACK_TICKERS[0]] + all_assets:
        df[f"{asset}_RetClose"] = df[f"{asset}_Close"].pct_change()          # 유지일
        df[f"{asset}_RetOpen"] = df[f"{asset}_Close"] / df[f"{asset}_Open"] - 1  # 전환일

    strat_returns: list[float] = []
    prev_target: str | None = None
    for i in range(size):
        target = df["Target_Asset"].iloc[i]
        if pd.isna(target):
            strat_returns.append(0.0)
            continue
        is_entry = (prev_target is None or target != prev_target)
        if is_entry:
            asset_ret = df[f"{target}_RetOpen"].iloc[i]
        else:
            asset_ret = df[f"{target}_RetClose"].iloc[i]
        friction = fee_rate if (prev_target is not None and target != prev_target) else 0.0
        strat_returns.append(asset_ret - friction)
        prev_target = target

    df["Strategy_Return"] = strat_returns
    # 벤치마크는 순수 종가 기준 바이앤홀드 (close→close)
    df["Cum_QQQ"] = (1 + df[f"{R}_RetClose"].fillna(0)).cumprod()
    df["Cum_QLD"] = (1 + df[f"{C.ATTACK_TICKERS[0]}_RetClose"].fillna(0)).cumprod()
    df["Cum_Strategy"] = (1 + df["Strategy_Return"].fillna(0)).cumprod()

    return df, last_info


# ── 근거 문장 ──────────────────────────────────────────────────────

def build_reason(info: dict) -> str:
    """마지막 날 결정 근거 한 문장(notifier 메시지용). V2 로직(완충지대+BIL 대피) 기반."""
    if not info:
        return "해당일 지표 기준 선정"

    is_bull = info["is_bull"]
    curr = info["curr"]

    if info["switched"]:
        if info["sw_to_attack"]:
            return (f"QQQ 종가가 105일 ZLEMA(105)+변동성밴드 상단 돌파(공격 국면 전환) → "
                    f"공격 2종 중 {curr} 55일 모멘텀 최대 → {curr} 선정")
        return (f"QQQ 종가가 105일 ZLEMA(105) 하단 이탈(방어 국면 전환) → "
                f"방어 4종 중 {curr} 55일 모멘텀 최대 → {curr} 선정")

    if info["exited"]:
        if info.get("fallback_bil"):
            return (f"보유 자산 {info['exited_from']} 샹들리에(15,4.0) 추적 손절선 이탈 + "
                    f"대안 공격 자산도 손절선 이탈 → BIL(현금) 대피")
        return (f"보유 자산 {info['exited_from']} 샹들리에(15,4.0) 추적 손절선 이탈 → "
                f"차순위 {curr} 교체")

    regime_word = "공격 국면 유지" if is_bull else "방어 국면 유지"
    return f"{regime_word}(완충지대) → {curr} 보유(샹들리에 추적 손절선 위)"


# ── 성과 지표 ──────────────────────────────────────────────────────

def get_performance_metrics(cum_wealth: pd.Series, daily_returns: pd.Series) -> tuple[float, float, float]:
    """노트북 get_performance_metrics 100% 준용."""
    n_days = len(cum_wealth)
    years = n_days / 252.0
    cagr = (cum_wealth.iloc[-1]) ** (1 / years) - 1 if cum_wealth.iloc[-1] > 0 else -0.99
    daily_std = daily_returns.std()
    sharpe = (daily_returns.mean() / daily_std * np.sqrt(252)) if daily_std > 0 else 0
    peak = cum_wealth.cummax()
    mdd = ((cum_wealth - peak) / peak).min()
    return cagr, sharpe, mdd


# ── 백테스트 결과 ──────────────────────────────────────────────────

@dataclass
class BacktestResult:
    target_today: str            # 오늘 아침 최종 포지셔닝 자산(티커)
    last_close_date: str         # 기준 종가 날짜
    reason: str                   # 오늘 포지션 선정 근거(한 문장, 메시지용)
    cagr: float
    sharpe: float
    mdd: float
    n_days: int


def build_result(df: pd.DataFrame, info: dict) -> BacktestResult:
    """성과 지표 + 오늘 포지션 + 근거 산출.

    오늘 포지션 = Chosen_Asset 의 마지막 값(가장 최근 종가 기준 시그널 → 오늘 시가 진입).
    백테스트 수익률은 Target_Asset(shift(1)) 기준(과거 실행 모사).
    """
    s_cagr, s_sharpe, s_mdd = get_performance_metrics(df["Cum_Strategy"], df["Strategy_Return"])

    # 오늘 실행 포지션 = Target_Asset(shift(1)) 의 마지막 값 (전일 종가 시그널 → 오늘 시가 진입)
    target_today = str(df["Target_Asset"].iloc[-1]) if pd.notna(df["Target_Asset"].iloc[-1]) else C.INIT_ASSET
    last_close_date = str(df.index[-1].date())
    reason = build_reason(info)
    n_days = int(df["Strategy_Return"].dropna().shape[0])

    return BacktestResult(
        target_today=target_today,
        last_close_date=last_close_date,
        reason=reason,
        cagr=float(s_cagr),
        sharpe=float(s_sharpe),
        mdd=float(s_mdd),
        n_days=n_days,
    )


# ── 공개 API ──────────────────────────────────────────────────────

def run() -> BacktestResult:
    """전체 파이프라인: 다운로드 → 마스터DF → 전략 → 결과."""
    data = load_data()
    master = build_master(data)
    df, info = run_strategy(master)
    return build_result(df, info)


if __name__ == "__main__":
    res = run()
    print(f"오늘 포지션: {res.target_today}  (기준종가 {res.last_close_date})")
    print(f"선정 근거: {res.reason}")
    print(f"CAGR={res.cagr:.4f}  Sharpe={res.sharpe:.2f}  MDD={res.mdd:.4f}  N={res.n_days}")