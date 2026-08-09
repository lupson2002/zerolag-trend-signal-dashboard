# ZeroLag Trend Signal Dashboard

나스닥100 ZLEMA(105) 레짐 필터 + 2배 공격(QLD) + 4대 대안자산(55일 모멘텀 로테이션) 하이브리드 전략의
Streamlit 대시보드. 매일 아침 포지션을 실시간 산출해 보여줍니다.

## 전략 스펙
- 레짐 필터: `QQQ` 종가 ≥ ZLEMA(105) → 공격 국면
- 공격 자산: `QLD`(2배 레버리지). `USD`=현금(공격 내 보호)
- 방어 자산: `TLT`, `BIL`, `USO`, `GLD` — 55일 모멘텀 최대 & 양수 & 샹들리에(15,4.0) 청산선 위 → 1종, 아니면 `USD`
- 수수료: 왕복 `2×0.0015` (자산 전환일 차감, 백테스트에 반영)
- 룩어헤드 차단: 시그널 산출 후 실행 포지션에 `.shift(1)` (전일 종가 → 당일 시가 진입)

## 구조
```
zerolag-trend-signal-dashboard/
├── dashboard_app.py   # Streamlit 진입점 (streamlit run dashboard_app.py)
├── config.py          # 파라미터·유니버스 상수 (고정)
├── engine.py          # 데이터 로드 → 지표 → 상태머신 → 백테스트 → 오늘 포지션
├── views/
│   ├── dashboard.py   # 성과/차트/통계/연도별/보유자산
│   ├── position.py    # 오늘 포지션 + 신호 세부
│   └── methodology.py # 전략 설명
└── requirements.txt
```

## 로컬 실행
```bash
pip install -r requirements.txt
streamlit run dashboard_app.py
```

## Streamlit Cloud 배포
1. 이 저장소를 GitHub에 push
2. [Streamlit Cloud](https://streamlit.io/cloud)에서 New app → 이 repo 선택
3. Main file path: `dashboard_app.py`
4. Deploy

## 주의
- 대시보드는 엔진을 실시간 실행(yfinance 다운로드)하므로 첫 로드에 수 초가 걸립니다.
- 투자 지표 아님. 전략 오류·데이터 지연 가능성 존재.
