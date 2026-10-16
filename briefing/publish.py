"""브리핑 결과를 GitHub Pages(gh-pages 브랜치)에 올립니다.

    python3 -m briefing.publish --out-dir out          # out/에 만든 최신 결과를 올림
    python3 -m briefing.publish --out-dir out --no-push  # out/site에 사이트만 만들고 올리지 않음

사이트 구성 (gh-pages 브랜치 루트)
- index.html          가장 최근 보고서
- archive.html        보관 중인 보고서 목록 (최신순)
- latest.json         가장 최근 보고서 정보
- reports/<YYYYMMDD_HHMM>/index.html, briefing.pdf   회차별 보고서

gh-pages는 매번 커밋 하나짜리 브랜치로 새로 만들어 강제 푸시합니다. 저장소 크기가 계속
커지지 않도록 회차 폴더는 ``KEEP_DAYS``일만 남깁니다.
"""

import argparse
import io
import json
import shutil
import subprocess
import tarfile
from datetime import datetime, timedelta
from html import escape
from pathlib import Path

from briefing.pdf import build_html
from briefing.run import KST, SLOTS

BRANCH = "gh-pages"
KEEP_DAYS = 30
GIT_USER = ("todaycandle2026", "todaycandle2026@users.noreply.github.com")
PAGE_STYLE = """
<meta name='viewport' content='width=device-width, initial-scale=1'>
<style>
body { max-width: 900px; margin: 0 auto; padding: 16px; }
nav { display: flex; flex-wrap: wrap; gap: 6px 16px; align-items: baseline; padding: 10px 0 12px;
      border-bottom: 0.6pt solid #c3c2b7; margin-bottom: 12px; font-size: 10pt; color: #52514e; }
nav a { color: #185fa5; }
nav .age { margin-left: auto; }
figure svg { max-width: 100%; }
table { display: block; overflow-x: auto; }
</style>
"""
AGE_SCRIPT = """
<script>
(function () {
  var el = document.querySelector('[data-generated]');
  if (!el) return;
  var minutes = Math.round((Date.now() - Date.parse(el.dataset.generated)) / 60000);
  el.textContent = minutes < 60 ? minutes + '분 전 생성'
    : minutes < 1440 ? Math.floor(minutes / 60) + '시간 ' + (minutes % 60) + '분 전 생성'
    : Math.floor(minutes / 1440) + '일 전 생성';
})();
</script>
"""


def build_site(site: Path, report: dict, news: dict, pdf_path: Path, now: datetime | None = None) -> str:
    """``site`` 폴더에 이번 회차를 더하고 index·archive를 다시 씁니다. 회차 폴더 이름을 돌려줍니다."""
    now = now or datetime.now(KST)
    stamp = report["generated_at"].replace("-", "").replace(":", "").replace(" ", "_")
    run_dir = site / "reports" / stamp
    run_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(pdf_path, run_dir / "briefing.pdf")
    meta = {
        "stamp": stamp,
        "generated_at": report["generated_at"],
        "generated_iso": datetime.strptime(report["generated_at"], "%Y-%m-%d %H:%M").replace(tzinfo=KST).isoformat(),
        "slot": SLOTS[report["slot"]],
        "name": report.get("name", report["code"]),
        "code": report["code"],
        "date": report["date"],
        "provisional": report["provisional"],
        "close": report["candle"]["close"],
        "change_pct": report["candle"]["change_pct"],
        "news_count": len(news.get("items") or []),
    }
    (run_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_dir / "index.html").write_text(_page(build_html(report, news), meta, prefix=""), encoding="utf-8")

    _prune(site / "reports", now - timedelta(days=KEEP_DAYS))
    runs = _runs(site / "reports")
    latest = runs[0]
    latest_html = (site / "reports" / latest["stamp"] / "index.html").read_text(encoding="utf-8")
    # 회차 페이지의 상대 경로를 사이트 루트 기준으로 바꿉니다.
    latest_html = latest_html.replace("href='briefing.pdf'", f"href='reports/{latest['stamp']}/briefing.pdf'")
    latest_html = latest_html.replace("href='../../", "href='")
    (site / "index.html").write_text(latest_html, encoding="utf-8")
    (site / "latest.json").write_text(json.dumps(latest, ensure_ascii=False, indent=2), encoding="utf-8")
    (site / "archive.html").write_text(_archive(runs), encoding="utf-8")
    (site / ".nojekyll").write_text("", encoding="utf-8")
    return stamp


def _page(html_text: str, meta: dict, prefix: str) -> str:
    state = "장중 잠정" if meta["provisional"] else "확정"
    nav = (
        f"<nav><strong>{escape(meta['name'])} 브리핑</strong>"
        f"<span>{meta['generated_at']} · {meta['slot']} · {meta['date']} 일봉 ({state})</span>"
        f"<a href='briefing.pdf'>PDF</a><a href='../../archive.html'>지난 보고서</a><a href='../../index.html'>최신</a>"
        f"<span class='age' data-generated='{meta['generated_iso']}'></span></nav>"
    )
    html_text = html_text.replace("<head>", f"<head>{PAGE_STYLE}<title>{escape(meta['name'])} 브리핑 {meta['generated_at']}</title>", 1)
    return html_text.replace("<body>", f"<body>{nav}", 1).replace("</body>", f"{AGE_SCRIPT}</body>", 1)


def _archive(runs: list[dict]) -> str:
    rows = "".join(
        f"<tr><td><a href='reports/{r['stamp']}/index.html'>{r['generated_at']}</a></td><td>{escape(r['slot'])}</td>"
        f"<td>{r['close']:,.0f}</td><td>{r['change_pct']:+.2f}%</td><td>{r['news_count']}</td>"
        f"<td><a href='reports/{r['stamp']}/briefing.pdf'>PDF</a></td></tr>"
        for r in runs
    )
    name = escape(runs[0]["name"]) if runs else "브리핑"
    return (
        "<!doctype html><html lang='ko'><head><meta charset='utf-8'>"
        f"{PAGE_STYLE}<title>{name} 지난 보고서</title><style>"
        "body{font-family:-apple-system,'Apple SD Gothic Neo','Noto Sans CJK KR',sans-serif;color:#0b0b0b}"
        "td,th{padding:4px 12px 4px 0;border-bottom:0.4pt solid #e1e0d9;text-align:right}"
        "td:first-child,th:first-child{text-align:left}th{color:#52514e;font-weight:500}a{color:#185fa5}</style></head><body>"
        f"<nav><strong>{name} 지난 보고서</strong><a href='index.html'>최신</a><span>최근 {KEEP_DAYS}일 보관</span></nav>"
        "<table><tr><th>생성 시각</th><th>구분</th><th>가격(원)</th><th>등락률</th><th>뉴스</th><th></th></tr>"
        f"{rows}</table></body></html>"
    )


def _runs(reports: Path) -> list[dict]:
    runs = [json.loads(p.read_text(encoding="utf-8")) for p in reports.glob("*/meta.json")]
    return sorted(runs, key=lambda r: r["stamp"], reverse=True)


def _prune(reports: Path, cutoff: datetime) -> None:
    for run_dir in reports.iterdir():
        try:
            created = datetime.strptime(run_dir.name, "%Y%m%d_%H%M").replace(tzinfo=KST)
        except ValueError:
            continue
        if created < cutoff:
            shutil.rmtree(run_dir)


# ---------------------------------------------------------------- git
def _git(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def checkout_site(repo: Path, site: Path) -> None:
    """원격 gh-pages의 파일을 ``site``에 풉니다. 브랜치가 없으면 빈 폴더로 시작합니다."""
    if site.exists():
        shutil.rmtree(site)
    site.mkdir(parents=True)
    try:
        _git("fetch", "--depth", "1", "origin", BRANCH, cwd=repo)
    except subprocess.CalledProcessError:
        return  # 첫 게시
    archive = subprocess.run(["git", "archive", "FETCH_HEAD"], cwd=repo, check=True, capture_output=True).stdout
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(site, filter="data")


def push_site(repo: Path, site: Path, message: str) -> None:
    """``site``를 커밋 하나짜리 gh-pages로 만들어 강제 푸시합니다."""
    remote = _git("remote", "get-url", "origin", cwd=repo).stdout.strip()
    shutil.rmtree(site / ".git", ignore_errors=True)
    _git("init", "-q", "-b", BRANCH, cwd=site)
    _git("add", "-A", cwd=site)
    _git("-c", f"user.name={GIT_USER[0]}", "-c", f"user.email={GIT_USER[1]}", "commit", "-q", "-m", message, cwd=site)
    _git("push", "-f", remote, f"HEAD:{BRANCH}", cwd=site)


def publish(report: dict, news: dict, pdf_path: Path, out_dir: Path, repo: Path, push: bool = True) -> Path:
    site = out_dir / "site"
    checkout_site(repo, site)
    stamp = build_site(site, report, news, pdf_path)
    if push:
        push_site(repo, site, f"브리핑 {report.get('name', report['code'])} {stamp}")
    return site


def main() -> None:
    parser = argparse.ArgumentParser(description="브리핑 결과를 GitHub Pages에 게시")
    parser.add_argument("--code", default="373220", help="종목코드")
    parser.add_argument("--out-dir", default="out", help="briefing.scheduled가 결과를 만든 폴더")
    parser.add_argument("--repo", default=".", help="today_candle 저장소 경로 (origin으로 푸시)")
    parser.add_argument("--no-push", action="store_true", help="사이트만 만들고 푸시하지 않음")
    args = parser.parse_args()

    out = Path(args.out_dir)
    report = json.loads((out / "charts" / f"{args.code}_report.json").read_text(encoding="utf-8"))
    news_path = out / f"{args.code}_news.json"
    news = json.loads(news_path.read_text(encoding="utf-8")) if news_path.exists() else {"note": "뉴스는 확인하지 못했습니다."}
    pdfs = sorted((out / "reports").glob("*.pdf"), key=lambda p: p.stat().st_mtime)
    if not pdfs:
        parser.error(f"{out / 'reports'}에 PDF가 없습니다.")
    site = publish(report, news, pdfs[-1], out, Path(args.repo), push=not args.no_push)
    print(f"SITE: {site}" + ("" if args.no_push else f" → {BRANCH} 푸시"))


if __name__ == "__main__":
    main()
