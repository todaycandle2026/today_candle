"""일봉 차트 신호를 계산해 출력합니다.

    uv run --env-file .env python -m briefing.run
    uv run --env-file .env python -m briefing.run --json --charts briefing/charts
"""

import argparse
import json
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from briefing.chart import fetch_daily_bars
from briefing.render import bars_required, render_charts
from briefing.signals import analyze, enrich, min_rows_required

DEFAULT_CODE = "373220"  # LG에너지솔루션
NAMES = {"373220": "LG에너지솔루션"}  # 보고서 제목과 PDF 파일명에 씁니다.
KST = ZoneInfo("Asia/Seoul")
MARKET_OPEN = time(9, 0)
MARKET_CLOSE = time(15, 30)
# 장 마감 뒤에도 넥스트레이드(NXT) 애프터마켓이 20시까지 열려 일봉 종가·거래량이 계속 바뀝니다.
AFTER_MARKET_CLOSE = time(20, 0)
SLOTS = {
    "pre": "장 시작 전",
    "mid": "장중",
    "close": "장 마감 후",
}


def current_slot(now: datetime) -> str:
    if now.time() < MARKET_OPEN:
        return "pre"
    if now.time() < MARKET_CLOSE:
        return "mid"
    return "close"


def build_report(code: str, now: datetime | None = None, chart_dir: str | None = None) -> dict:
    now = now or datetime.now(KST)
    today = now.strftime("%Y%m%d")
    min_rows = max(min_rows_required(), bars_required()) if chart_dir else min_rows_required()
    bars = fetch_daily_bars(code, today, min_rows)
    # 장중과 애프터마켓(20시 전)에는 당일 캔들과 거래량이 아직 확정되지 않았습니다.
    provisional = bars["date"].iloc[-1] == today and now.time() < AFTER_MARKET_CLOSE
    report = analyze(bars, provisional=provisional)
    report["code"] = code
    report["name"] = NAMES.get(code, code)
    report["slot"] = current_slot(now)
    report["generated_at"] = now.strftime("%Y-%m-%d %H:%M")
    # 휴장일이나 장 시작 전에는 마지막 일봉이 이전 거래일입니다.
    report["bar_is_today"] = report["date"] == today
    if chart_dir:
        report["charts"] = render_charts(enrich(bars), report, chart_dir)
    return report


def format_text(report: dict) -> str:
    candle, volume, oversold = report["candle"], report["volume"], report["oversold"]
    wick, spread = report["long_wick"], report["ma_spread"]
    lines = [
        f"[{report['code']}] {report['generated_at']} {SLOTS[report['slot']]} · "
        f"{report['date']} 일봉 ({'잠정' if report['provisional'] else '확정'})",
        f"{'현재가' if report['provisional'] else '종가'} {candle['close']:,.0f} ({candle['change_pct']:+.2f}%) {candle['type']}, 당일 변동폭 {candle['range_pct']:.2f}%",
        "",
        f"이동평균 ({report['ma_alignment']})",
    ]
    for period, ma in report["moving_averages"].items():
        lines.append(f"  {period:>3}일선 {ma['value']:>10,.0f}  이격도 {ma['disparity_pct']:+.2f}%")

    lines += [
        "",
        f"이평선 간격(60/100/200/300): {spread['trend']} "
        f"— 폭 {spread['spread_pct_before']:.2f}% → {spread['spread_pct']:.2f}% "
        f"({spread['lookback_days']}거래일 전 대비 {spread['change_pct']:+.1f}%)",
    ]
    for pair, gap in spread["pairs"].items():
        lines.append(f"  {pair}일선 간격 {gap['gap_pct_before']:+.2f}% → {gap['gap_pct']:+.2f}%")

    wick_tags = [name for name, on in (("긴 아래꼬리", wick["lower"]), ("긴 위꼬리", wick["upper"])) if on]
    lines += [
        "",
        f"낙폭과대: {'해당' if oversold['flag'] else '아님'} "
        f"(20일선 이격도 {oversold['disparity20_pct']:+.2f}%, "
        f"{oversold['drawdown_days']}일 고점 대비 {oversold['drawdown_pct']:+.2f}%)",
        f"긴꼬리: {', '.join(wick_tags) or '없음'} "
        f"(아래 {wick['lower_ratio']:.0%}, 위 {wick['upper_ratio']:.0%})",
        f"거래량: {volume['status']} "
        f"({volume['volume']:,}주, {volume['avg_days']}일 평균의 {volume['ratio_to_avg']:.2f}배)",
    ]
    if report["recent_events"]:
        lines += ["", "최근 신호"]
        for event in report["recent_events"]:
            lines.append(f"  {event['date']} ({event['change_pct']:+.2f}%) {', '.join(event['tags'])}")
    if report.get("charts"):
        lines += ["", "차트 이미지"] + [f"  {path}" for path in report["charts"].values()]
    if report["provisional"]:
        lines += ["", "※ 장중 수치는 잠정이며 마감 때 달라질 수 있습니다."]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="일봉 차트 신호 브리핑")
    parser.add_argument("--code", default=DEFAULT_CODE, help="종목코드")
    parser.add_argument("--json", action="store_true", help="JSON으로 출력")
    parser.add_argument("--charts", metavar="DIR", help="이격도 이미지, 일봉 차트(SVG), 보고서 JSON을 저장할 폴더")
    args = parser.parse_args()

    report = build_report(args.code, chart_dir=args.charts)
    if args.charts:
        # PDF 생성(briefing.pdf)이 같은 수치를 쓰도록 보고서를 이미지 옆에 남깁니다.
        report["report_path"] = str((Path(args.charts) / f"{args.code}_report.json").resolve())
        Path(report["report_path"]).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(format_text(report))


if __name__ == "__main__":
    main()
