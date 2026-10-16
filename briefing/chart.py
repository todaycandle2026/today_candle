from datetime import datetime, timedelta

import FinanceDataReader as fdr
import pandas as pd

# 키움 ka10081(주식일봉차트조회, 수정주가) 대신 FinanceDataReader(네이버 금융 일봉)를 씁니다.
# 반환 형식은 키움 버전과 같습니다: date(YYYYMMDD 문자열), open, high, low, close, volume.
CALENDAR_DAYS_PER_ROW = 1.6  # 휴장일을 감안해 거래일 1개당 넉넉히 잡는 달력 일수


def fetch_daily_bars(stk_cd: str, base_dt: str, min_rows: int) -> pd.DataFrame:
    """수정주가 일봉을 과거→최근 순으로 최소 ``min_rows``개 조회합니다."""
    end = datetime.strptime(base_dt, "%Y%m%d")
    start = end - timedelta(days=int(min_rows * CALENDAR_DAYS_PER_ROW) + 30)
    raw = fdr.DataReader(stk_cd, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
    if raw.empty:
        raise RuntimeError(f"일봉 조회 실패: {stk_cd} 데이터가 없습니다.")
    df = pd.DataFrame(
        {
            "date": raw.index.strftime("%Y%m%d"),
            "open": raw["Open"].to_numpy(),
            "high": raw["High"].to_numpy(),
            "low": raw["Low"].to_numpy(),
            "close": raw["Close"].to_numpy(),
            "volume": raw["Volume"].to_numpy(),
        }
    )
    df = df[df["volume"] > 0].drop_duplicates(subset="date").sort_values("date").reset_index(drop=True)
    if len(df) < min_rows:
        raise RuntimeError(f"일봉이 {len(df)}개뿐입니다. 최소 {min_rows}개가 필요합니다.")
    return df
