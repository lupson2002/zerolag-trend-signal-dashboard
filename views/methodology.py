"""Strategy description and calculation methodology - static reference page."""

import streamlit as st

st.markdown(
    """
    <style>
    div.block-container { padding-top: 2.6rem; }
    .ic-intro { font-size: 15px; color: #52564d; margin: 0 0 4px; line-height: 1.6; }
    .ic-body p, .ic-body ul { margin: 0 0 8px; font-size: 14px; line-height: 1.48; }
    .ic-body ul { padding-left: 20px; }
    .ic-body li { margin-bottom: 3px; }
    .ic-body h4 { font-size: 14px; margin: 10px 0 4px; font-weight: 700; color: #16191a; }
    .ic-body h4:first-child { margin-top: 0; }
    .ic-body code { font-size: 13px; background: #f2f3ee; padding: 1px 5px; border-radius: 3px; }
    .ic-body .formula { background: #f2f3ee; border-radius: 5px; padding: 8px 12px; font-size: 13px; margin: 4px 0 8px; line-height: 1.6; }
    </style>
    """,
    unsafe_allow_html=True,
)

tab_strategy, tab_signals, tab_cost = st.tabs(["전략설명", "신호", "매매비용"])

with tab_strategy:
    st.markdown(
        """
        <div class="ic-body">
        <ul>
        <li><b>나스닥100 레짐 필터</b>와 <b>2배 레버리지 공격 자산</b>, 그리고 <b>4대 매크로 대안 자산</b>의
        모멘텀 로테이션을 결합한 하이브리드 전략입니다.</li>
        <li>QQQ 종가가 105일 지연제어 이동평균(ZLEMA) 위에 있으면 <b>공격 국면</b>, 아래로 이탈하면
        <b>방어 국면</b>으로 판정합니다.</li>
        <li>공격 국면에서는 나스닥100 2배(QLD)에 투자하고, 방어 국면에서는 채권/원유/금/현금 중
        55일 모멘텀이 가장 높은 자산으로 로테이션합니다.</li>
        <li>보유 자산은 샹들리에 추적 손절선(ATR 기반)을 붕괴하면 차순위 자산으로 교체합니다.</li>
        </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )

with tab_signals:
    st.markdown(
        """
        <div class="ic-body">
        <h4>레짐 필터 (ZLEMA + 완충지대)</h4>
        <p>정통 Ehlers ZLEMA(105)에 변동성 밴드를 더해 대세 상승장을 판별합니다. 상단 돌파 시
        공격 국면, 하단 이탈 시 방어 국면으로 전환하며, 사이 구간(완충지대)에서는 기존 국면을
        유지해 잦은 핑퐁 매매를 차단합니다.</p>
        <div class="formula">
        ZLEMA = EWM( src + (src − src.shift(lag)) , span=105 )<br/>
        Upper = ZLEMA + ATR(105)·3일 최대 · Lower = ZLEMA
        </div>

        <h4>공격 자산</h4>
        <p>공격 국면에서는 <b>QLD</b>(나스닥100 2배 레버리지)와 <b>USD</b>(현금) 중 55일 모멘텀이
        높은 쪽을 선택합니다. 공격 2종이 동시에 손절선을 이탈하면 현금(BIL)으로 대피합니다.</p>

        <h4>방어 자산</h4>
        <p>방어 국면에서는 <b>TLT</b>(장기국채), <b>BIL</b>(초단기국채), <b>USO</b>(원유),
        <b>GLD</b>(금) 중 55일 모멘텀이 가장 높은 자산을 선택합니다.</p>

        <h4>샹들리에 추적 손절선</h4>
        <p>보유 자산의 최고점에서 ATR(15, 4.0) 배수를 뺀 선을 추적합니다. 종가가 이 선 아래로
        내려가면 차순위 자산으로 교체합니다.</p>
        <div class="formula">chandelier = highest_high − ATR(15) × 4.0</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with tab_cost:
    st.markdown(
        """
        <div class="ic-body">
        <h4>매매비용 가정</h4>
        <p>자산 전환일마다 왕복 수수료 <b>0.30%</b>(0.0015 × 2)를 차감합니다. 같은 포지션을
        유지하는 날은 비용이 0입니다.</p>

        <h4>룩어헤드 차단</h4>
        <p>시그널은 종가 기준으로 산출하지만, 실행 포지션은 반드시 1일 시프트(shift(1))해서
        새벽 미국장 종가 확정 후 아침 한국장 시가에 진입하는 것을 모사합니다.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
