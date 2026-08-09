"""ZEROLAG TREND SIGNAL — Telegram 알림 모듈.

requests 로 Telegram Bot API 호출, 마크다운 포맷 메시지 전송.
성과 지표는 engine.run() 의 실시간 산출값을 사용 (고정값 아님).
"""

import os

import requests

import config as C

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def build_message(target_ticker: str, reason: str = "",
                  cagr: float = 0.0, sharpe: float = 0.0, mdd: float = 0.0,
                  n_days: int = 0, last_close_date: str = "") -> str:
    """실시간 성과 + 오늘 포지션 템플릿 생성."""
    cagr_pct = f"{cagr * 100:.2f}"
    mdd_pct = f"{mdd * 100:.1f}"
    sharpe_s = f"{sharpe:.2f}"
    reason = reason.strip() or "해당일 지표 기준 선정"

    return (
        "📢 *ZEROLAG TREND SIGNAL REPORT*\n"
        "\n"
        "본 전략은 나스닥100 지수의 105일 지연제어 레짐 필터(ZLEMA + 대칭 완충지대)와 "
        "2배 레버리지 공격 자산(QLD/반도체 2배), 그리고 4대 매크로 대안 자산 "
        "(채권/원유/금/현금)의 55일 모멘텀 로테이션을 결합한 실전형 알고리즘입니다. "
        "V2: 공격 2종 동시 손절 시 현금(BIL) 대피 로직 추가.\n"
        "\n"
        "📊 *백테스트 성과 (수수료 차감 후, 실시간 산출)*\n"
        f"• 연복리 수익률 (CAGR): {cagr_pct}%\n"
        f"• 위험 대비 보상 (Sharpe Ratio): {sharpe_s}\n"
        f"• 최고점 대비 최대 낙폭 (MDD): {mdd_pct}%\n"
        f"• 백테스트 기간: {n_days} 거래일\n"
        "\n"
        "--------------------------------------------------\n"
        "🎯 *[오늘 아침 한국장 실행 포지션]*\n"
        f"▶ *신규 진입/유지 자산: {target_ticker}*\n"
        f"📌 *기준종가: {last_close_date}*\n"
        "\n"
        f"📌 *선정 근거:* {reason}\n"
        "--------------------------------------------------"
    )


def send_telegram(target_ticker: str, reason: str = "",
                  cagr: float = 0.0, sharpe: float = 0.0, mdd: float = 0.0,
                  n_days: int = 0, last_close_date: str = "",
                  token: str | None = None, chat_id: str | None = None) -> dict:
    """Telegram 메시지 전송. 성공 시 API 응답 dict 반환."""
    token = token or os.environ.get("TELEGRAM_BOT_TOKEN", "").strip().strip('"')
    chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID", "").strip().strip('"')

    if not token or token == "YOUR_BOT_TOKEN_HERE":
        raise ValueError("TELEGRAM_BOT_TOKEN 미설정(.env 확인)")
    if not chat_id or chat_id == "YOUR_CHAT_ID_HERE":
        raise ValueError("TELEGRAM_CHAT_ID 미설정(.env 확인)")

    url = TELEGRAM_API.format(token=token)
    payload = {
        "chat_id": chat_id,
        "text": build_message(target_ticker, reason, cagr, sharpe, mdd, n_days, last_close_date),
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    resp = requests.post(url, json=payload, timeout=15)
    resp.raise_for_status()
    return resp.json()


if __name__ == "__main__":
    # 단독 실행: 템플릿 콘솔 출력
    msg = build_message("BIL", "방어 국면 유지(완충지대) → BIL 보유(샹들리에 추적 손절선 위)",
                        cagr=0.4523, sharpe=1.15, mdd=-0.3768, n_days=2664, last_close_date="2026-08-07")
    print(msg)
