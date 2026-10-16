"""종목 뉴스를 Google 뉴스 RSS에서 모아 ``briefing.pdf --news``용 JSON으로 저장합니다.

    python3 -m briefing.news --code 373220 --out out/373220_news.json

기사 본문은 열지 않고 제목·매체·링크·게시 시각만 씁니다(요약 = 기사 제목).
클라우드에서 실행하려면 네트워크 허용 목록에 ``news.google.com``이 있어야 합니다.
"""

import argparse
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from briefing.run import NAMES

KST = ZoneInfo("Asia/Seoul")
RSS_URL = "https://news.google.com/rss/search?q={query}&hl=ko&gl=KR&ceid=KR:ko"
TIMEOUT_SECONDS = 15
DEFAULT_DAYS = 3
DEFAULT_LIMIT = 6
ALIASES = {"LG에너지솔루션": ("LG엔솔",)}  # 기사 제목에 자주 쓰는 줄임말
# 시세만 옮겨 적는 자동 생성 기사는 뺍니다.
EXCLUDE_PATTERNS = (
    r"주가,?\s*\d+월\s*\d+일",
    r"\[마감분석\]",
    r"\[(장중|오전|오후)\s*시황\]",
    r"\d+원\s*\d+(,\d+)*원\s*[\d.]+%\s*(상승|하락)",
)


def fetch_news(name: str, days: int = DEFAULT_DAYS, limit: int = DEFAULT_LIMIT, now: datetime | None = None) -> dict:
    """최근 ``days``일 안에 제목에 종목명(또는 줄임말)이 들어간 기사를 최신순으로 최대 ``limit``개 돌려줍니다."""
    now = now or datetime.now(KST)
    names = (name, *ALIASES.get(name, ()))
    query = urllib.parse.quote(" OR ".join(f'"{n}"' for n in names) + f" when:{days}d")
    request = urllib.request.Request(RSS_URL.format(query=query), headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            xml_text = response.read()
    except OSError as error:
        return {"items": [], "note": f"뉴스를 가져오지 못했습니다 ({type(error).__name__}: {error})."}
    items = parse_rss(xml_text, names, since=now - timedelta(days=days))[:limit]
    if items:
        note = f"Google 뉴스 검색 결과(최근 {days}일)의 기사 제목입니다. 본문은 확인하지 않았습니다."
    else:
        note = f"최근 {days}일 새 소식 없음"
    return {"items": items, "note": note}


def parse_rss(xml_text: bytes | str, names: tuple[str, ...], since: datetime) -> list[dict]:
    root = ET.fromstring(xml_text)
    seen, items = set(), []
    for node in root.iter("item"):
        source = (node.findtext("source") or "").strip()
        title = _strip_source(node.findtext("title") or "", source)
        published = _published(node.findtext("pubDate"))
        if not any(n in title for n in names) or published is None or published < since:
            continue
        if any(re.search(pattern, title) for pattern in EXCLUDE_PATTERNS):
            continue
        key = re.sub(r"\W", "", title)
        if key in seen:
            continue
        seen.add(key)
        items.append(
            {
                "summary": title,
                "source": source or "출처",
                "url": (node.findtext("link") or "").strip(),
                "date_note": published.strftime("%m/%d %H:%M"),
                "published": published.isoformat(),
            }
        )
    items.sort(key=lambda item: item["published"], reverse=True)
    return items


def _strip_source(title: str, source: str) -> str:
    """Google 뉴스 제목 끝의 ' - 매체명'을 뗍니다."""
    title = title.strip()
    if source and title.endswith(f" - {source}"):
        return title[: -len(source) - 3].strip()
    return title


def _published(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).astimezone(KST)
    except (TypeError, ValueError):
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="종목 뉴스 수집 (Google 뉴스 RSS)")
    parser.add_argument("--code", default="373220", help="종목코드")
    parser.add_argument("--name", help="검색할 종목명 (없으면 briefing.run.NAMES에서 찾음)")
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS, help="최근 며칠 기사를 볼지")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="최대 기사 수")
    parser.add_argument("--out", required=True, help="저장할 JSON 경로")
    args = parser.parse_args()

    name = args.name or NAMES.get(args.code)
    if not name:
        parser.error(f"종목명을 모릅니다. --name으로 지정하세요 ({args.code}).")
    news = fetch_news(name, days=args.days, limit=args.limit)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(news, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{out} · 기사 {len(news['items'])}건" + (f" · {news['note']}" if not news["items"] else ""))


if __name__ == "__main__":
    main()
