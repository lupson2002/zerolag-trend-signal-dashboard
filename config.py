"""ZEROLAG TREND SIGNAL — 하이퍼파라미터·유니버스 상수 (노트북 백테스트 100% 준용).

최적화 수렴 결과를 고정값으로 반영. 런타임 튜닝 금지(재현성 보장).
노트북 BEST_LENGTH_IN=105 / MULT_IN=1.0 / LENGTH_OUT=15 / MULT_OUT=4.0 / MOM=55 / FEE=0.0015.
"""

# ── 유니버스 ──────────────────────────────────────────────────────
# 레짐 필터용 지수
REGIME_TICKER = "QQQ"

# 공격 자산 (2종): QLD=나스닥100 2배, USD=현금(공격 내 보호 후보)
ATTACK_TICKERS = ["QLD", "USD"]

# 방어 자산 (4대 매크로 대안)
DEFENSE_TICKERS = ["TLT", "BIL", "USO", "GLD"]

# 전체 스위칭 대상 (공격 + 방어)
ALL_TICKERS = ATTACK_TICKERS + DEFENSE_TICKERS

# 상태머신 초기 보유 자산 (노트북: 'BIL')
INIT_ASSET = "BIL"

# 전체 데이터 수집 대상 (레짐 + 스위칭 전종목, USD 실제 다운로드 — 노트북과 동일)
PRICE_TICKERS = [REGIME_TICKER] + ALL_TICKERS

# ── 최적화 수렴 파라미터 (고정) ───────────────────────────────────
LENGTH_IN = 105       # ZLEMA 윈도우 — 대세 상승장 레짐 필터링
MULT_IN = 1.0          # 레짐 밴드 ATR 승수 (Keltner식)
LENGTH_OUT = 15        # 샹들리에 추적 청산 ATR 윈도우 (자산별 개별)
MULT_OUT = 4.0         # 샹들리에 ATR 승수
MOM_WINDOW = 55        # 국면 내 모멘텀 비교 주기(≈3개월 영업일)
FEE_RATE = 0.0015      # 왕복 1회 수수료(자산 전환일 차감)

# ── 데이터 기간 ────────────────────────────────────────────────────
DATA_START = "2016-01-01"   # 백테스트 시작
# 끝은 '오늘' (engine 가동 시점 동적)

# ── 백테스트 검증 성과 (수수료 차감 후, V2 코랩 발표값 — notifier 템플릿 고정) ──
# 기준: 2016-01-01 ~ 2026-06-01, QQQ ZLEMA(105) Hysteresis V2 로테이션
BACKTEST_CAGR = 0.4262      # 42.62%
BACKTEST_SHARPE = 1.22
BACKTEST_MDD = -0.2658      # -26.58%

# ── Kelly 비중별 포트폴리오 성과 (코랩 V2 시뮬레이션 발표값 — notifier 템플릿 고정) ──
# Full Kelly: 전략 40.83% / 현금·BIL 59.17% 혼합 계좌 성과
KELLY_FULL_WEIGHT = 0.4083     # f
KELLY_FULL_CAGR = 0.1865       # 18.65%
KELLY_FULL_SHARPE = 1.31
KELLY_FULL_MDD = -0.1123       # -11.23%
KELLY_FULL_GUIDE = "균형형: 시장 평균 수익 + MDD -11% 억제"