# ZeroLag Trend Signal — 전문가 검수용 프로젝트 명세서

> 이 문서는 독립적인 전문가 AI(또는 퀀트 리뷰어)가 이 전략의 **이론적 타당성**과
> **논리적/구현적 정확성**을 판단할 수 있도록, 프로젝트의 목적·방법론·워크플로우·코드
> 구조·알려진 한계를 구체적으로 기술한다. 코드는 `engine.py`가 단일 소스이며,
> 대시보드(`views/`)와 검증 스크립트(`validate_strategy.py`)는 이를 소비한다.

---

## 1. 프로젝트 목적

**나스닥100의 대세 추세(레짐)를 필터로 삼아, 상승장에서는 2배 레버리지 ETF에 공격적으로
투자하고 하락장에서는 4대 매크로 대안자산으로 로테이션하는 하이브리드 전략**의
매일 아침 포지션을 산출하고, 그 유효성(초과수익 존재 여부)을 백테스트로 검증한다.

- **실전 용도**: 매일 아침(한국장 시가 전) "오늘 보유할 자산" 1종을 결정해 텔레그램으로 통지.
- **검증 용도**: 전략이 단순 벤치마크(QQQ/QLD) 대비 통계적으로 유의미한 초과수익(alpha)을
  내는지, 그리고 그 초과수익이 과적합이 아닌지 판단.

---

## 2. 전략 방법론 (이론적 설계)

### 2.1 유니버스 (`config.py`)
| 구분 | 티커 | 의미 |
|---|---|---|
| 레짐 필터 | `QQQ` | 나스닥100 추종 ETF |
| 공격 자산 | `QLD`, `USD` | QLD=나스닥100 2배 레버리지. **`USD`는 yfinance에서 ProShares Ultra Semiconductors(반도체 2배 ETF)로 해석됨** — 현금이 아님(사용자 결정으로 유지) |
| 방어 자산 | `TLT`, `BIL`, `USO`, `GLD` | 장기국채 / 초단기국채(현금 대용) / 원유 / 금 |
| 초기 보유 | `BIL` | 상태머신 시작 자산 |

### 2.2 레짐 필터 — ZLEMA + 대칭 완충지대 (Hysteresis)
- **ZLEMA(105)**: Ehlers Zero-Lag EMA. `src_adj = close + (close − close.shift(lag))`,
  `lag = floor((105−1)/2) = 52`, 이후 `ewm(span=105, adjust=False)`.
- **변동성 밴드**: `QQQ_ATR = TR.ewm(alpha=1/105)`, `QQQ_Vol = ATR.rolling(315).max() × 1.0`.
- **판별선** (대칭 완충지대):
  - `Upper_In = ZLEMA + QQQ_Vol`
  - `Lower_In = ZLEMA − QQQ_Vol`
- **레짐 판정** (완충지대 = 잦은 핑퐁 방지):
  - `close > Upper_In` → **BULL**
  - `close < Lower_In` → **BEAR**
  - 그 사이 → **이전 레짐 유지**
- **이론적 근거**: 대세 상승장에서만 레버리지 공격, 하락장에서는 방어. 완충지대는
  노이즈에 의한 잦은 전환(휩쏘)을 줄이는 히스테리시스.

### 2.3 자산 선택 — 모멘텀 로테이션
- **공격(BULL)**: `QLD`/`USD` 중 55일 모멘텀(`pct_change(55)`)이 **최대**인 자산.
  (NaN 가드: 유효한 모멘텀만 후보)
- **방어(BEAR)**: `TLT`/`BIL`/`USO`/`GLD` 중 55일 모멘텀이 **양수 & 최대**인 자산.
  양수 후보가 없으면 `BIL`(현금) 대피.
- **이론적 근거**: 모멘텀 지속성(자산군 로테이션). 방어 국면에서 음수 모멘텀 자산을
  붙잡지 않도록 양수 필터 적용.

### 2.4 샹들리에 추적 손절선 (Chandelier Exit)
- 보유 자산의 `highest_high`에서 `ATR(15) × 4.0`을 뺀 선을 추적.
- `close < chandelier_line` → 손절.
  - **BULL**: 대안 공격 자산으로 교체. 대안도 손절선 아래면 `BIL` 대피.
  - **BEAR**: 나머지 방어 자산 중 양수 모멘텀 최대로 교체, 없으면 `BIL`.
- **앵커링**: 레짐 전환/손절 교체 시 `highest_high`를 0으로 두고 **다음날(실제 진입일)
  고가로 앵커링** — 시그널일 고가가 아닌 실제 진입 기준.

### 2.5 실행 모델 — 1-Day Lag + 시가 진입
- **룩어헤드 차단**: 시그널은 종가 기준. 실행 포지션 `Target_Asset = Chosen_Asset.shift(1)`.
  (새벽 미국장 종가 확정 → 아침 한국장 시가 진입 모사)
- **수익률 모델**:
  - **전환일**: `close[i]/open[i] − 1` (당일 시가 진입 → 당일 종가 청산, 전일종가→당일시가 갭 미노출)
  - **유지일**: `close[i]/close[i−1] − 1` (전일 종가 보유분 그대로)
- **수수료**: 자산 전환일마다 왕복 `0.0015 × 2 = 0.30%` 차감.
- **벤치마크**: QQQ/QLD는 순수 `close→close` 바이앤홀드.

---

## 3. 워크플로우 (코드 실행 흐름)

```
engine.load_data()          # yfinance: 2016-01-01 ~ 오늘, 7개 티커 OHLCV
        ↓
engine.build_master()       # {TICKER}_Close/Open/High/Low 단일 DF, dropna() 동기화
        ↓
engine.run_strategy()       # 지표 → 상태머신 → Chosen_Asset → Target_Asset(shift1) → 수익률
        ↓
engine.build_result()       # 오늘 포지션 + 근거 + CAGR/Sharpe/MDD
        ↓
[대시보드] views/dashboard.py, position.py, methodology.py  (Streamlit)
[검증]    validate_strategy.py  (초과수익/유의성/민감도/롤링)
```

### 상태머신 의사코드 (핵심)
```
curr_asset = 'BIL'; curr_regime = 'BEAR'; highest_high = 0
for i in range(size):
    if Upper/Lower NaN: Chosen = 'BIL'; continue
    # [A] 레짐 판정 (완충지대)
    new_regime = BULL if close>Upper else BEAR if close<Lower else curr_regime
    regime_changed = (new_regime != curr_regime); curr_regime = new_regime
    if regime_changed:
        # [B] 자산 교체 (모멘텀 max, NaN/양수 가드)
        curr_asset = pick_asset(curr_regime)
        highest_high = 0            # 다음날 진입일 고가로 앵커링
    else:
        # [C] 샹들리에 손절 검증
        highest_high = max(highest_high, asset_high)
        if close < highest_high - ATR*4.0:
            curr_asset = replace_asset(curr_regime)   # 손절 교체
            highest_high = 0
    Chosen[i] = curr_asset
Target = Chosen.shift(1)   # 실행 포지션
```

---

## 4. 코드 구조

| 파일 | 역할 |
|---|---|
| `config.py` | 파라미터·유니버스 상수 (LENGTH_IN=105, MOM=55, MULT_OUT=4.0, FEE=0.0015) |
| `engine.py` | 데이터 로드 → 지표 → 상태머신 → 백테스트 → 오늘 포지션 (단일 소스) |
| `dashboard_app.py` | Streamlit 진입점 (3페이지 네비게이션) |
| `views/dashboard.py` | 성과 차트/통계/연도별/보유자산 |
| `views/position.py` | 오늘 포지션 + 신호 세부 |
| `views/methodology.py` | 전략 설명 (정적) |
| `validate_strategy.py` | 유효성·초과수익·민감도·롤링 검증 |

---

## 5. 검증 방법론 (`validate_strategy.py`)

1. **기본 성과**: 전략 vs QQQ vs QLD (CAGR/Vol/Sharpe/MDD/Multiple)
2. **초과수익 alpha**: 일별 초과수익의 평균·연환산 alpha·정보비율(IR)
   - **i.i.d. t-test** + **Newey-West HAC t-test** (자기상관 보정) 병기
3. **위험조정 품질**: Sharpe/Calmar/Sortino 비교
4. **국면별 성과**: BULL vs BEAR 기여도 (실행 포지션 기준 정렬)
5. **파라미터 민감도**: LENGTH_IN/MOM_WINDOW/MULT_OUT 그리드 (과적합 여부)
6. **롤링 안정성**: 3년 롤링 CAGR/Sharpe, QQQ 이긴 비율
7. **초과수익 곡선**: 연도별 + 누적 (상대부 비율 기반 정확 계산)

---

## 6. 현재 검증 결과 (2026-08-07 기준, 수수료 차감 후)

| 지표 | 전략 | QQQ | QLD |
|---|---|---|---|
| CAGR | 36.7% | 20.4% | 32.7% |
| Sharpe | 1.03 | 0.94 | 0.86 |
| MaxDD | -37.8% | -35.1% | -63.7% |
| 누적 초과수익(vs QQQ) | **+282.1%** | — | — |
| 초과수익 t (i.i.d.) | 1.58 (p=0.114) | — | — |
| 초과수익 t (HAC) | 1.64 (p=0.102) | — | — |

- **국면별**: BULL CAGR +58.3% (QQQ +22.6%) / BEAR CAGR +21.7% (QQQ +18.7%)
- **3년 롤링**: 전략 평균 +39.7% vs QQQ +19.8%, 이긴 비율 56.2%

---

## 7. 알려진 한계 & 검수 시 중점 판단 사항

### 7.1 이론적 우려
1. **`USD` = 반도체 2배 ETF** (현금 아님). 공격 자산이 QLD+USD 둘 다 레버리지 주식 ETF라
   "공격 + 현금 보호" 설계와 실제가 다름. **사용자 결정으로 유지** — 리스크만 문서화.
2. **초과수익의 통계적 유의성 부족** (HAC p≈0.10). 초과수익이 특정 구간(2023, 2026)에
   집중 — 구조적 특성인지, 과적합인지 판단 필요.
3. **레버리지 ETF의 복리/변동성 역학**: QLD/USD는 일일 리셋 레버리지라 장기 보유 시
   변동성 역학(volatility drag)이 발생. 백테스트가 이를 정확히 반영하는지.
4. **모멘텀 지속성의 붕괴 위험**: 55일 모멘텀 로테이션이 과거에 유효했지만, 시장 구조
   변화(2020년대)에서도 유효한지.

### 7.2 구현/논리적 검수 포인트
- **룩어헤드**: 시그널(i일 종가)이 i일 수익률에 적용되지 않는지 (shift(1) 검증).
- **시가 진입 모델**: 전환일 open→close, 유지일 close→close의 경계가 정확한지.
- **샹들리에 앵커**: highest_high가 실제 진입일 고가로 시작하는지.
- **완충지대 대칭성**: Upper/Lower가 ZLEMA±Vol로 대칭인지.
- **NaN 전파**: 모멘텀/ATR NaN이 상태머신을 오염시키지 않는지.
- **벤치마크 공정성**: 전략(시가 진입) vs 벤치마크(종가) 비교의 타당성.
- **수수료 타이밍**: 전환일 수수료 차감이 정확한지.

---

## 8. 재현 방법

```bash
cd /home/mikey/zerolag-trend-signal-dashboard
pip install -r requirements.txt
python3 engine.py            # 오늘 포지션 + 성과
python3 validate_strategy.py # 유효성·초과수익 검증
streamlit run dashboard_app.py  # 대시보드
```

- 데이터: yfinance (2016-01-01 ~ 오늘), 7개 티커 OHLCV.
- 파라미터: `config.py` 고정 (LENGTH_IN=105, MOM=55, MULT_OUT=4.0, FEE=0.0015).
