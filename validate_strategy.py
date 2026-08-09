"""ZeroLag Trend Signal — 전략 유효성 & 초과수익 검증 스크립트.

목적: 이 전략이 단순 벤치마크(QQQ/QLD) 대비 통계적으로 유의미한 초과수익(alpha)을
내는지, 그리고 그 초과수익이 우연(과적합)이 아닌지 검증한다.

검증 항목:
  1) 기본 성과 — 전략 vs QQQ vs QLD (CAGR/Sharpe/MDD/Vol)
  2) 초과수익(alpha) — 일별 초과수익의 평균·t-통계량·연환산 alpha
  3) 정보비율(IR) & 승률 — 초과수익의 위험조정 품질
  4) 국면별 성과 — 공격(BULL) vs 방어(BEAR) 국면 기여도
  5) 파라미터 민감도 — LENGTH_IN / MOM_WINDOW / MULT_OUT 그리드
  6) 롤링 윈도우 안정성 — 3년 롤링 CAGR/Sharpe (과적합 여부)
  7) 벤치마크 대비 초과수익 누적 곡선

실행: python3 validate_strategy.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config as C
import engine

SEP = "=" * 72


# ── 데이터 로드 (1회) ─────────────────────────────────────────────

def load_master() -> pd.DataFrame:
    data = engine.load_data()
    return engine.build_master(data)


# ── 성과 지표 ─────────────────────────────────────────────────────

def perf_stats(ret: pd.Series) -> dict:
    ret = ret.dropna()
    eq = (1 + ret).cumprod()
    n_years = len(ret) / 252
    cagr = eq.iloc[-1] ** (1 / n_years) - 1 if eq.iloc[-1] > 0 else -0.99
    vol = ret.std() * np.sqrt(252)
    sharpe = (ret.mean() * 252) / vol if vol > 0 else 0
    mdd = (eq / eq.cummax() - 1).min()
    return {"CAGR": cagr, "Vol": vol, "Sharpe": sharpe, "MaxDD": mdd, "Multiple": eq.iloc[-1]}


def fmt_pct(x: float) -> str:
    return f"{x * 100:+.2f}%"


def fmt_metric(name: str, v: float) -> str:
    if name == "Sharpe":
        return f"{v:.2f}"
    if name == "Multiple":
        return f"${v:.1f}"
    return f"{v:.1%}"


def cum_excess_ratio(strat_ret: pd.Series, bench_ret: pd.Series) -> float:
    """정확한 누적 초과수익 = 상대부(relative wealth) 비율 - 1.
    산술차(strat-bench)를 복리화하는 대신 로그차분으로 정확히 계산.
    """
    strat_eq = (1 + strat_ret).cumprod()
    bench_eq = (1 + bench_ret).cumprod()
    return (strat_eq / bench_eq).iloc[-1] - 1


def _newey_west_t(x: pd.Series) -> tuple[float, float]:
    """Newey-West HAC t-통계량 (자기상관 보정). lag = n^(1/3) 근사."""
    x = x.dropna().to_numpy()
    n = len(x)
    if n < 2:
        return 0.0, 1.0
    mean = x.mean()
    resid = x - mean
    # HAC 분산 (Bartlett kernel)
    lag = int(np.floor(n ** (1 / 3)))
    gamma0 = (resid @ resid) / n
    var = gamma0
    for l in range(1, lag + 1):
        w = 1 - l / (lag + 1)
        gamma_l = (resid[l:] @ resid[:-l]) / n
        var += 2 * w * gamma_l
    se = np.sqrt(var / n) if var > 0 else 0.0
    t = mean / se if se > 0 else 0.0
    p = 2 * (1 - stats.t.cdf(abs(t), df=n - 1))
    return t, p


# ── 1) 기본 성과 ──────────────────────────────────────────────────

def section_baseline(df: pd.DataFrame) -> None:
    print(SEP)
    print("1) 기본 성과 — 전략 vs QQQ vs QLD (수수료 차감 후)")
    print(SEP)

    strat_ret = df["Strategy_Return"].fillna(0)
    qqq_ret = df[f"{C.REGIME_TICKER}_RetClose"].fillna(0)
    qld_ret = df[f"{C.ATTACK_TICKERS[0]}_RetClose"].fillna(0)

    rows = {
        "ZeroLag 전략": perf_stats(strat_ret),
        "QQQ (벤치마크)": perf_stats(qqq_ret),
        "QLD (2x)": perf_stats(qld_ret),
    }
    metric_order = ["CAGR", "Vol", "Sharpe", "MaxDD", "Multiple"]
    table = pd.DataFrame(
        {name: {k: fmt_metric(k, rows[name][k]) for k in metric_order} for name in rows}
    )
    print(table.to_string())
    print()

    # 전략 vs QQQ 초과수익 (정확한 상대부 비율)
    print(f"전략 vs QQQ 누적 초과수익: {fmt_pct(cum_excess_ratio(strat_ret, qqq_ret))}")
    print(f"전략 vs QLD 누적 초과수익: {fmt_pct(cum_excess_ratio(strat_ret, qld_ret))}")
    print()


# ── 2) 초과수익 alpha & 통계 유의성 ───────────────────────────────

def section_alpha(df: pd.DataFrame) -> None:
    print(SEP)
    print("2) 초과수익(alpha) — 일별 초과수익의 통계적 유의성")
    print(SEP)

    strat_ret = df["Strategy_Return"].fillna(0)
    qqq_ret = df[f"{C.REGIME_TICKER}_RetClose"].fillna(0)
    excess = strat_ret - qqq_ret
    excess = excess.dropna()

    n = len(excess)
    mean_daily = excess.mean()
    std_daily = excess.std()
    t_stat = mean_daily / (std_daily / np.sqrt(n)) if std_daily > 0 else 0
    p_value = 2 * (1 - stats.t.cdf(abs(t_stat), df=n - 1))

    # ★ Newey-West HAC t-통계량: 일별 초과수익은 자기상관이 있어 i.i.d. t-test가
    #   표준오차를 과소평가. HAC로 자기상관을 보정한 유의성도 함께 제시.
    nw_t, nw_p = _newey_west_t(excess)

    ann_alpha = mean_daily * 252
    ann_vol = std_daily * np.sqrt(252)
    info_ratio = ann_alpha / ann_vol if ann_vol > 0 else 0

    print(f"일별 초과수익 평균: {fmt_pct(mean_daily)}")
    print(f"일별 초과수익 표준편차: {fmt_pct(std_daily)}")
    print(f"연환산 alpha (vs QQQ): {fmt_pct(ann_alpha)}")
    print(f"정보비율 (IR): {info_ratio:.2f}")
    print(f"t-통계량 (i.i.d.): {t_stat:.2f}  (p-value: {p_value:.4f})")
    print(f"t-통계량 (Newey-West HAC): {nw_t:.2f}  (p-value: {nw_p:.4f})")
    print(f"  → {'유의미한 초과수익 (HAC p<0.05)' if nw_p < 0.05 else '통계적으로 유의미하지 않음 (HAC p≥0.05)'}")
    print()

    # 승률
    win_rate = (excess > 0).mean()
    print(f"일별 초과수익 승률: {win_rate:.1%}")
    print(f"양수 초과수익 일수: {(excess > 0).sum()} / {n}")
    print()


# ── 3) 정보비율 & 위험조정 품질 ──────────────────────────────────

def section_quality(df: pd.DataFrame) -> None:
    print(SEP)
    print("3) 위험조정 품질 — 전략이 벤치마크 대비 위험 대비 보상이 나은가")
    print(SEP)

    strat_ret = df["Strategy_Return"].fillna(0)
    qqq_ret = df[f"{C.REGIME_TICKER}_RetClose"].fillna(0)

    s = perf_stats(strat_ret)
    b = perf_stats(qqq_ret)

    # Sharpe 비율 비교
    print(f"전략 Sharpe: {s['Sharpe']:.2f}  vs  QQQ Sharpe: {b['Sharpe']:.2f}")
    print(f"전략 MDD: {s['MaxDD']:.1%}  vs  QQQ MDD: {b['MaxDD']:.1%}")
    print(f"전략 CAGR: {s['CAGR']:.1%}  vs  QQQ CAGR: {b['CAGR']:.1%}")

    # Calmar 비율 (CAGR/MDD)
    calmar_s = s["CAGR"] / abs(s["MaxDD"]) if s["MaxDD"] != 0 else 0
    calmar_b = b["CAGR"] / abs(b["MaxDD"]) if b["MaxDD"] != 0 else 0
    print(f"Calmar 비율 (CAGR/|MDD|): 전략 {calmar_s:.2f}  vs  QQQ {calmar_b:.2f}")

    # Sortino (하방변동성 기준)
    downside = strat_ret[strat_ret < 0].std() * np.sqrt(252)
    sortino_s = s["CAGR"] / downside if downside > 0 else 0
    downside_b = qqq_ret[qqq_ret < 0].std() * np.sqrt(252)
    sortino_b = b["CAGR"] / downside_b if downside_b > 0 else 0
    print(f"Sortino 비율: 전략 {sortino_s:.2f}  vs  QQQ {sortino_b:.2f}")
    print()


# ── 4) 국면별 성과 ────────────────────────────────────────────────

def section_regime(df: pd.DataFrame) -> None:
    print(SEP)
    print("4) 국면별 성과 — 공격(BULL) vs 방어(BEAR) 국면 기여도")
    print(SEP)

    strat_ret = df["Strategy_Return"].fillna(0)
    qqq_ret = df[f"{C.REGIME_TICKER}_RetClose"].fillna(0)

    # ★ 국면 기여도는 실행 포지션(Target_Asset) 기준으로 정렬해야 수익률과 일치.
    #   Chosen_Asset(시그널)의 레짐을 shift(1)해서 실행일의 레짐으로 사용.
    #   BIL은 BULL 안전피난처일 수 있으므로 자산명이 아닌 레짐 상태로 분류.
    attack_set = set(C.ATTACK_TICKERS)
    chosen_regime = df["Chosen_Asset"].map(lambda a: "BULL" if a in attack_set else "BEAR")
    regime = chosen_regime.shift(1).fillna("BEAR")

    for r in ["BULL", "BEAR"]:
        mask = regime == r
        if mask.sum() == 0:
            continue
        r_ret = strat_ret[mask]
        b_ret = qqq_ret[mask]
        eq = (1 + r_ret).cumprod()
        n_years = len(r_ret) / 252
        cagr = eq.iloc[-1] ** (1 / n_years) - 1 if eq.iloc[-1] > 0 else -0.99
        print(f"[{r}] 일수 {mask.sum():4d} ({mask.mean():.0%}) | "
              f"전략 CAGR {cagr:+.1%} | QQQ CAGR {(1+b_ret).prod()**(1/n_years)-1:+.1%} | "
              f"전략 누적 {(1+r_ret).prod()-1:+.1%} | QQQ 누적 {(1+b_ret).prod()-1:+.1%}")
    print()


# ── 5) 파라미터 민감도 ────────────────────────────────────────────

def section_sensitivity(master: pd.DataFrame) -> None:
    print(SEP)
    print("5) 파라미터 민감도 — 핵심 파라미터 그리드 (과적합 여부 확인)")
    print(SEP)

    grids = {
        "LENGTH_IN (레짐 ZLEMA)": [75, 90, 105, 120, 135],
        "MOM_WINDOW (모멘텀)": [40, 55, 70, 85],
        "MULT_OUT (샹들리에)": [3.0, 3.5, 4.0, 4.5, 5.0],
    }

    for label, values in grids.items():
        print(f"--- {label} ---")
        results = []
        for v in values:
            kw = {}
            if "LENGTH_IN" in label:
                kw["length_in"] = v
            elif "MOM_WINDOW" in label:
                kw["mom_window"] = v
            else:
                kw["mult_out"] = v
            df, _ = engine.run_strategy(master, **kw)
            ret = df["Strategy_Return"].fillna(0)
            st = perf_stats(ret)
            results.append((v, st["CAGR"], st["Sharpe"], st["MaxDD"]))
        for v, cagr, sharpe, mdd in results:
            marker = " ◀ 현재값" if v == (105 if "LENGTH_IN" in label else 55 if "MOM_WINDOW" in label else 4.0) else ""
            print(f"  {v:>5} → CAGR {cagr:+.1%} | Sharpe {sharpe:.2f} | MDD {mdd:.1%}{marker}")
        print()


# ── 6) 롤링 윈도우 안정성 ─────────────────────────────────────────

def section_rolling(df: pd.DataFrame) -> None:
    print(SEP)
    print("6) 롤링 윈도우 안정성 — 3년 롤링 CAGR/Sharpe (과적합 여부)")
    print(SEP)

    strat_ret = df["Strategy_Return"].fillna(0)
    qqq_ret = df[f"{C.REGIME_TICKER}_RetClose"].fillna(0)

    window = 252 * 3
    strat_cagr = strat_ret.rolling(window).apply(
        lambda r: (1 + r).prod() ** (252 / len(r)) - 1, raw=True
    )
    qqq_cagr = qqq_ret.rolling(window).apply(
        lambda r: (1 + r).prod() ** (252 / len(r)) - 1, raw=True
    )

    valid = strat_cagr.dropna()
    print(f"3년 롤링 CAGR — 전략: 평균 {strat_cagr.mean():+.1%} | "
          f"최저 {strat_cagr.min():+.1%} | 최고 {strat_cagr.max():+.1%}")
    print(f"3년 롤링 CAGR — QQQ: 평균 {qqq_cagr.mean():+.1%} | "
          f"최저 {qqq_cagr.min():+.1%} | 최고 {qqq_cagr.max():+.1%}")
    beat = (strat_cagr > qqq_cagr).mean()
    print(f"전략이 QQQ를 이긴 3년 윈도우 비율: {beat:.1%}")
    print()


# ── 7) 초과수익 누적 곡선 요약 ───────────────────────────────────

def section_excess_curve(df: pd.DataFrame) -> None:
    print(SEP)
    print("7) 벤치마크 대비 초과수익 누적 곡선 요약")
    print(SEP)

    strat_ret = df["Strategy_Return"].fillna(0)
    qqq_ret = df[f"{C.REGIME_TICKER}_RetClose"].fillna(0)
    # ★ 정확한 상대부 비율 기반 초과수익 (산술차 복리화 대신)
    strat_eq = (1 + strat_ret).cumprod()
    bench_eq = (1 + qqq_ret).cumprod()
    rel = strat_eq / bench_eq
    cum_excess = rel

    # 연도별 초과수익 (상대부 비율의 연도별 변화)
    yearly = rel.groupby(rel.index.year).apply(lambda r: r.iloc[-1] / r.iloc[0] - 1)
    print("연도별 초과수익 (전략 - QQQ):")
    for y, v in yearly.items():
        print(f"  {y}: {v:+.1%}")
    print()
    print(f"전체 누적 초과수익: {fmt_pct(rel.iloc[-1] - 1)}")
    print(f"초과수익 최대 낙폭: {(cum_excess / cum_excess.cummax() - 1).min():.1%}")
    print()


# ── 메인 ─────────────────────────────────────────────────────────

def main() -> None:
    print("ZeroLag Trend Signal — 전략 유효성 & 초과수익 검증")
    print(f"데이터 기간: {C.DATA_START} ~ 오늘 · 수수료 왕복 {C.FEE_RATE * 2:.2%}")
    print("데이터 로드 중...")
    master = load_master()
    df, info = engine.run_strategy(master)
    print(f"완료 — {len(df)} 거래일, 기준종가 {df.index[-1].date()}\n")

    section_baseline(df)
    section_alpha(df)
    section_quality(df)
    section_regime(df)
    section_sensitivity(master)
    section_rolling(df)
    section_excess_curve(df)

    print(SEP)
    print("검증 완료")


if __name__ == "__main__":
    main()
