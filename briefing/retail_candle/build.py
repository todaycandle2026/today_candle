"""삼성전자 개인 대량 순매수 하락일 캔들차트를 오늘까지 데이터로 다시 만듭니다.

    uv run --env-file .env python -m briefing.retail_candle.build

결과: briefing/data/retail_candle/005930_candle_retail8m_YYYYMMDD_HHMMSS.html (실행 시각, 과거 파일은 그대로 쌓임)

- 투자자별 순매수 수량: ka10059, 005930_AL (KRX+NXT 통합), 수량·순매수·단주
- 캔들(시고저종)·등락률: ka10081 KRX 공식 일봉, 등락률 = 당일 종가 / 전일 종가 - 1
- 검정 캔들: 개인 순매수 >= 800만주 이면서 등락률 < 0
- 단기 추세선: 최근 봉부터 60봉씩 구간을 나눠 구간마다 SHORT_TERM 규칙(briefing/channel.py)
- 가로 저항선(분홍)·지지선(진한 파랑): briefing/retail_candle/levels.py
조회 전용 API만 씁니다.
"""

import json
import time
from datetime import datetime, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from briefing.channel import SHORT_TERM, find_channel
from briefing.chart import fetch_daily_bars
from briefing.retail_candle.levels import horizontal_levels
from kiwoom import get_client

CODE = "005930"
START = "2025-03-04"  # NXT 출범일: 통합 데이터가 있는 첫날
RETAIL_MIN = 8_000_000
KST = ZoneInfo("Asia/Seoul")
HERE = Path(__file__).parent
DATA = HERE.parent / "data"
OUT_DIR = DATA / "retail_candle"  # 만들 때마다 날짜시간을 붙여 쌓습니다.


def fetch_investor(stk_cd: str, today: str) -> pd.DataFrame:
    client = get_client()
    body = {"dt": today, "stk_cd": stk_cd, "amt_qty_tp": "2", "trde_tp": "0", "unit_tp": "1"}
    rows, cont, key = [], None, None
    for _ in range(60):
        r = client.fetch_page(api_id="ka10059", path="/api/dostk/stkinfo", body=body, cont_yn=cont, next_key=key)
        b = r.body
        if b.get("return_code") not in (None, 0):
            raise RuntimeError(f"ka10059 실패: {b.get('return_msg')}")
        recs = b.get("stk_invsr_orgn") or []
        rows.extend(recs)
        cont, key = r.continuation.cont_yn, r.continuation.next_key
        if cont != "Y" or not recs or min(x["dt"] for x in recs) < START.replace("-", ""):
            break
        time.sleep(0.3)
    df = pd.DataFrame(rows).drop_duplicates("dt")
    df["일자"] = pd.to_datetime(df["dt"]).dt.strftime("%Y-%m-%d")
    df["개인"] = pd.to_numeric(df["ind_invsr"].astype(str).str.replace("+", "", regex=False))
    return df[df["일자"] >= START][["일자", "개인"]]


def build(now: datetime | None = None) -> Path:
    now = now or datetime.now(KST)
    today = now.strftime("%Y%m%d")
    inv = fetch_investor(f"{CODE}_AL", today)
    bars = fetch_daily_bars(CODE, today, 900)
    bars["일자"] = pd.to_datetime(bars["date"].astype(str)).dt.strftime("%Y-%m-%d")
    bars = bars.sort_values("일자").reset_index(drop=True)
    bars["등락률"] = (bars["close"] / bars["close"].shift() - 1) * 100
    m = bars[bars["일자"] >= START].merge(inv, on="일자", how="inner").reset_index(drop=True)

    rows = [{"d": r["일자"], "o": int(r["open"]), "h": int(r["high"]), "l": int(r["low"]), "c": int(r["close"]),
             "r": round(float(r["등락률"]), 2), "i": int(r["개인"]),
             "k": bool(r["개인"] >= RETAIL_MIN and r["등락률"] < 0)} for _, r in m.iterrows()]
    ohlc = m[["open", "high", "low", "close"]].astype(float)

    segments, end = [], len(ohlc)
    while end > 0:
        beg = max(0, end - SHORT_TERM.lookback)
        ch = find_channel(ohlc.iloc[:end], SHORT_TERM)
        segments.append({"beg": beg, "end": end - 1, **{k: v and {**v} for k, v in ch.items()}})
        end = beg
    segments.reverse()
    res = horizontal_levels(ohlc["high"].tolist(), ohlc["close"].tolist(), upper=True)
    sup = horizontal_levels(ohlc["low"].tolist(), ohlc["close"].tolist(), upper=False)

    last = rows[-1]["d"]
    live = last == now.strftime("%Y-%m-%d") and now.time() < dtime(15, 30)
    html = (HERE / "template.html").read_text()
    html = (html.replace("__DATA__", json.dumps(rows, ensure_ascii=False))
                .replace("__LINES__", json.dumps(segments)).replace("__RES__", json.dumps(res)).replace("__SUP__", json.dumps(sup))
                .replace("__PERIOD__", f"{rows[0]['d']} ~ {last}")
                .replace("__LASTNOTE__", f"마지막 날({last[5:]})은 장중 잠정치입니다. " if live else ""))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"005930_candle_retail8m_{now:%Y%m%d_%H%M%S}.html"
    out.write_text(html)
    print(f"{out} | {rows[0]['d']} ~ {last} {len(rows)}봉 | 검정 {sum(x['k'] for x in rows)}건 | 저항 {len(res)} 지지 {len(sup)} | 추세 구간 {len(segments)}")
    return out


if __name__ == "__main__":
    build()
