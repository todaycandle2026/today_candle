"""브리핑 보고서를 PDF로 저장합니다.

    uv run python -m briefing.pdf --report briefing/charts/373220_report.json \\
        --news briefing/charts/373220_news.json --out-dir briefing/reports

``--report``는 ``briefing.run --json --charts``가 저장한 JSON이고,
``--news``는 ``{"items": [{"summary", "source", "url", "date_note"}], "note": ""}`` 형태입니다.
파일명은 ``종목명_생성일_시간.pdf``입니다.
"""

import argparse
import json
import subprocess
from html import escape
from pathlib import Path

from briefing.run import SLOTS

import os

# Mac은 Google Chrome, 클라우드는 미리 설치된 Chromium을 씁니다. BRIEFING_CHROME으로 바꿀 수 있습니다.
_CHROME_CANDIDATES = (
    os.environ.get("BRIEFING_CHROME", ""),
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
)
CHROME = next((path for path in _CHROME_CANDIDATES if path and Path(path).exists()), _CHROME_CANDIDATES[1])
CHROME_TIMEOUT_SECONDS = 60
STYLE = """
@page { size: A4; margin: 14mm 13mm; }
body { font-family: -apple-system, 'Apple SD Gothic Neo', 'Noto Sans CJK KR', 'WenQuanYi Zen Hei', sans-serif; font-size: 10.5pt; color: #0b0b0b; line-height: 1.55; }
h1 { font-size: 17pt; margin: 0 0 2pt; }
h2 { font-size: 12.5pt; margin: 16pt 0 6pt; border-bottom: 0.6pt solid #c3c2b7; padding-bottom: 3pt; }
p { margin: 4pt 0; }
.meta { color: #52514e; font-size: 9.5pt; }
.summary { font-size: 12pt; margin: 10pt 0; }
table { border-collapse: collapse; margin: 6pt 0; }
th, td { border-bottom: 0.4pt solid #e1e0d9; padding: 3pt 12pt 3pt 0; text-align: right; font-variant-numeric: tabular-nums; }
th { color: #52514e; font-weight: 500; }
th:first-child, td:first-child { text-align: left; }
figure { margin: 10pt 0; break-inside: avoid; }
.keep { break-inside: avoid; }
figure svg { width: 100%; height: auto; }
li { margin-bottom: 5pt; }
a { color: #185fa5; }
"""


def build_html(report: dict, news: dict) -> str:
    candle, volume, oversold = report["candle"], report["volume"], report["oversold"]
    wick, spread = report["long_wick"], report["ma_spread"]
    name = report.get("name", report["code"])
    slot = SLOTS[report["slot"]]
    close_name = "현재가" if report["provisional"] else "종가"

    ma_rows = "".join(
        f"<tr><td>{period}일선</td><td>{ma['value']:,.0f}</td><td>{ma['disparity_pct']:+.2f}%</td></tr>"
        for period, ma in report["moving_averages"].items()
    )
    pair_rows = "".join(
        f"<tr><td>{pair}일선</td><td>{gap['gap_pct_before']:+.2f}%</td><td>{gap['gap_pct']:+.2f}%</td></tr>"
        for pair, gap in spread["pairs"].items()
    )
    wick_tags = [tag for tag, on in (("긴 아래꼬리", wick["lower"]), ("긴 위꼬리", wick["upper"])) if on]
    events = "".join(
        f"<li>{event['date']} ({event['change_pct']:+.2f}%) {escape(', '.join(event['tags']))}</li>"
        for event in report["recent_events"]
    )
    disparity, daily = (
        f"<figure>{Path(report['charts'][key]).read_text(encoding='utf-8')}</figure>" for key in ("disparity", "daily")
    )

    parts = [
        f"<h1>{escape(name)} ({report['code']}) 브리핑</h1>",
        f"<p class='meta'>{report['generated_at']} 생성 · {slot} · {report['date']} 일봉 "
        f"({'장중 잠정' if report['provisional'] else '확정'})</p>",
        f"<p class='summary'>{slot} {close_name} {candle['close']:,.0f}원 ({candle['change_pct']:+.2f}%) · "
        f"{candle['type']} · 이평 배열 {report['ma_alignment']} · 이평선 간격 {spread['trend']}</p>",
        "<h2>차트</h2>",
        f"<p>시가 {candle['open']:,.0f} / 고가 {candle['high']:,.0f} / 저가 {candle['low']:,.0f} / "
        f"{close_name} {candle['close']:,.0f} · 당일 변동폭 {candle['range_pct']:.2f}%</p>",
        f"<table><tr><th>이동평균</th><th>값(원)</th><th>이격도</th></tr>{ma_rows}</table>",
        f"<p>이평선 간격(60/100/200/300일선): {spread['trend']} — 폭 {spread['spread_pct_before']:.2f}% → "
        f"{spread['spread_pct']:.2f}% ({spread['lookback_days']}거래일 전 대비 {spread['change_pct']:+.1f}%)</p>",
        f"<table><tr><th>인접 선 간격</th><th>{spread['lookback_days']}거래일 전</th><th>현재</th></tr>{pair_rows}</table>",
        f"<p>낙폭과대: {'해당' if oversold['flag'] else '아님'} (20일선 이격도 {oversold['disparity20_pct']:+.2f}%, "
        f"{oversold['drawdown_days']}일 고점 대비 {oversold['drawdown_pct']:+.2f}%)</p>",
        f"<p>긴꼬리: {', '.join(wick_tags) or '없음'} (아래 {wick['lower_ratio']:.0%}, 위 {wick['upper_ratio']:.0%})</p>",
        f"<p>거래량: {volume['status']} ({volume['volume']:,}주, {volume['avg_days']}일 평균의 {volume['ratio_to_avg']:.2f}배)</p>",
        f"<p>최근 신호</p><ul>{events}</ul>" if events else "<p>최근 신호: 없음</p>",
        # 제목만 앞 쪽에 남지 않도록 첫 이미지와 묶습니다.
        f"<div class='keep'><h2>차트 이미지</h2>{disparity}</div>",
        daily,
        "<h2>뉴스</h2>",
        _news_html(news),
    ]
    return f"<!doctype html><html lang='ko'><head><meta charset='utf-8'><style>{STYLE}</style></head><body>{''.join(parts)}</body></html>"


def _news_html(news: dict) -> str:
    items = news.get("items") or []
    note = f"<p>{escape(news['note'])}</p>" if news.get("note") else ""
    if not items:
        return note or "<p>새 소식 없음</p>"
    rows = []
    for item in items:
        source = escape(item.get("source", "출처"))
        link = f"<a href='{escape(item['url'], quote=True)}'>{source}</a>" if item.get("url") else source
        date_note = f" ({escape(item['date_note'])})" if item.get("date_note") else ""
        rows.append(f"<li>{escape(item['summary'])} — {link}{date_note}</li>")
    return f"<ol>{''.join(rows)}</ol>{note}"


def write_pdf(report: dict, news: dict, out_dir: str) -> Path:
    directory = Path(out_dir).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    stamp = report["generated_at"].replace("-", "").replace(":", "").replace(" ", "_")
    pdf_path = directory / f"{report.get('name', report['code'])}_{stamp}.pdf"
    html_path = directory / f".{pdf_path.stem}.html"
    html_path.write_text(build_html(report, news), encoding="utf-8")
    try:
        subprocess.run(
            [CHROME, "--headless=new", "--disable-gpu", "--no-sandbox", "--no-pdf-header-footer", f"--print-to-pdf={pdf_path}", html_path.as_uri()],
            check=True,
            capture_output=True,
            timeout=CHROME_TIMEOUT_SECONDS,
        )
    finally:
        html_path.unlink(missing_ok=True)
    if not pdf_path.exists():
        raise RuntimeError("PDF 파일이 만들어지지 않았습니다.")
    return pdf_path


def main() -> None:
    parser = argparse.ArgumentParser(description="브리핑 PDF 생성")
    parser.add_argument("--report", required=True, help="briefing.run이 저장한 보고서 JSON")
    parser.add_argument("--news", help="뉴스 JSON (없으면 뉴스를 확인하지 못했다고 적습니다)")
    parser.add_argument("--out-dir", default="briefing/reports", help="PDF를 저장할 폴더")
    args = parser.parse_args()

    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    news = json.loads(Path(args.news).read_text(encoding="utf-8")) if args.news else {"note": "뉴스는 확인하지 못했습니다."}
    print(write_pdf(report, news, args.out_dir))


if __name__ == "__main__":
    main()
