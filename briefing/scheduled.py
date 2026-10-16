"""정해진 시각에 브리핑 PDF를 만듭니다. 휴장일에는 아무것도 만들지 않습니다.

    python3 -m briefing.scheduled --code 373220 --out-dir out

마지막 줄에 ``PDF: <경로>`` 또는 ``SKIP: <이유>``를 출력합니다.
``--publish``를 주면 결과를 GitHub Pages(gh-pages 브랜치)에도 올립니다(briefing.publish).

휴장일 판정
1. 주말이거나 한국거래소 달력(exchange_calendars XKRX)에서 휴장일이면 건너뜁니다.
2. 달력에 없는 임시 휴장일(선거일 등)은 일봉으로 확인합니다. 10시 이후인데
   오늘 일봉이 없으면 휴장일로 보고 건너뜁니다.
"""

import argparse
import json
from datetime import datetime, time
from pathlib import Path

from briefing.news import fetch_news
from briefing.pdf import write_pdf
from briefing.publish import BRANCH, publish
from briefing.run import KST, NAMES, build_report

DATA_CHECK_AFTER = time(10, 0)  # 이 시각 이후에는 오늘 일봉이 있어야 거래일입니다.


def holiday_reason(now: datetime) -> str | None:
    """달력 기준 휴장 사유. 거래일이면 ``None``."""
    if now.weekday() >= 5:
        return "주말"
    try:
        import exchange_calendars as xc

        calendar = xc.get_calendar("XKRX")
        day = now.strftime("%Y-%m-%d")
        if calendar.first_session.strftime("%Y-%m-%d") <= day <= calendar.last_session.strftime("%Y-%m-%d"):
            return None if calendar.is_session(day) else "한국거래소 휴장일"
    except ImportError:
        pass
    return None  # 달력을 쓸 수 없으면 일봉 확인에 맡깁니다.


def main() -> None:
    parser = argparse.ArgumentParser(description="예약 실행용 브리핑 PDF 생성")
    parser.add_argument("--code", default="373220", help="종목코드")
    parser.add_argument("--out-dir", default="out", help="결과를 저장할 폴더")
    parser.add_argument("--news-days", type=int, default=3, help="뉴스를 볼 기간(일)")
    parser.add_argument("--publish", action="store_true", help="결과를 GitHub Pages에 올림")
    parser.add_argument("--repo", default=".", help="today_candle 저장소 경로 (--publish 때 origin으로 푸시)")
    args = parser.parse_args()

    now = datetime.now(KST)
    reason = holiday_reason(now)
    if reason:
        print(f"SKIP: {now:%Y-%m-%d} {reason}")
        return

    out = Path(args.out_dir)
    report = build_report(args.code, now=now, chart_dir=str(out / "charts"))
    if not report["bar_is_today"] and now.time() >= DATA_CHECK_AFTER:
        print(f"SKIP: {now:%Y-%m-%d} 오늘 일봉 없음 (임시 휴장일로 판단, 마지막 일봉 {report['date']})")
        return
    report_path = out / "charts" / f"{args.code}_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    news = fetch_news(NAMES.get(args.code, args.code), days=args.news_days, now=now)
    (out / f"{args.code}_news.json").write_text(json.dumps(news, ensure_ascii=False, indent=2), encoding="utf-8")

    pdf_path = write_pdf(report, news, str(out / "reports"))
    candle = report["candle"]
    close_name = "현재가" if report["provisional"] else "종가"
    print(f"{report['name']} {close_name} {candle['close']:,.0f}원 ({candle['change_pct']:+.2f}%) · 뉴스 {len(news['items'])}건")
    if args.publish:
        publish(report, news, pdf_path, out, Path(args.repo))
        print(f"PUBLISHED: {BRANCH}")
    print(f"PDF: {pdf_path}")


if __name__ == "__main__":
    main()
