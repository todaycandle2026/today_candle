from dataclasses import dataclass

import pandas as pd

MA_PERIODS = (20, 60, 100, 200, 300)
SPREAD_PERIODS = (60, 100, 200, 300)


@dataclass(frozen=True)
class Thresholds:
    oversold_disparity20_pct: float = -10.0  # 20일선 이격도가 이 값 이하면 낙폭과대
    oversold_drawdown_days: int = 60  # 고점 대비 하락률을 보는 기간
    oversold_drawdown_pct: float = -20.0  # 기간 고점 대비 하락률이 이 값 이하면 낙폭과대
    long_wick_ratio: float = 0.5  # 꼬리가 당일 고저 범위에서 차지하는 비율
    volume_avg_days: int = 20
    volume_spike_ratio: float = 2.0  # 평균 대비 이 배수 이상이면 급증
    volume_dry_ratio: float = 0.5  # 평균 대비 이 배수 이하면 급감
    spread_lookback_days: int = 20  # 이평선 수렴/확산을 비교하는 기간
    spread_change_pct: float = 10.0  # 폭이 이 비율 이상 변해야 수렴/확산으로 판정
    history_days: int = 5


def min_rows_required(thresholds: Thresholds = Thresholds()) -> int:
    return max(MA_PERIODS) + thresholds.spread_lookback_days + thresholds.history_days


def enrich(bars: pd.DataFrame, thresholds: Thresholds = Thresholds()) -> pd.DataFrame:
    """일봉에 이동평균과 캔들·거래량 지표 열을 붙입니다."""
    df = bars.copy()
    for period in MA_PERIODS:
        df[f"ma{period}"] = df["close"].rolling(period).mean()

    candle_range = df["high"] - df["low"]
    body_top = df[["open", "close"]].max(axis=1)
    body_bottom = df[["open", "close"]].min(axis=1)
    df["upper_wick_ratio"] = ((df["high"] - body_top) / candle_range).where(candle_range > 0, 0.0)
    df["lower_wick_ratio"] = ((body_bottom - df["low"]) / candle_range).where(candle_range > 0, 0.0)
    df["range_pct"] = candle_range / df["close"] * 100
    df["change_pct"] = df["close"].pct_change() * 100

    # 당일을 제외한 직전 N일 평균과 비교합니다.
    volume_avg = df["volume"].shift(1).rolling(thresholds.volume_avg_days).mean()
    df["volume_ratio"] = df["volume"] / volume_avg

    df["disparity20_pct"] = (df["close"] / df["ma20"] - 1) * 100
    rolling_high = df["high"].rolling(thresholds.oversold_drawdown_days).max()
    df["drawdown_pct"] = (df["close"] / rolling_high - 1) * 100

    spread_mas = df[[f"ma{period}" for period in SPREAD_PERIODS]]
    df["ma_spread_pct"] = (spread_mas.max(axis=1) - spread_mas.min(axis=1)) / spread_mas.mean(axis=1) * 100
    return df


def analyze(bars: pd.DataFrame, thresholds: Thresholds = Thresholds(), *, provisional: bool = False) -> dict:
    """가장 최근 일봉 기준의 신호를 판정합니다.

    ``provisional``은 마지막 일봉이 아직 진행 중(장중)임을 뜻합니다.
    """
    if len(bars) < min_rows_required(thresholds):
        raise ValueError(f"일봉이 {len(bars)}개뿐입니다. 최소 {min_rows_required(thresholds)}개가 필요합니다.")

    df = enrich(bars, thresholds)
    last = df.iloc[-1]
    close = float(last["close"])

    return {
        "date": last["date"],
        "provisional": provisional,
        "candle": {
            "open": float(last["open"]),
            "high": float(last["high"]),
            "low": float(last["low"]),
            "close": close,
            "change_pct": _round(last["change_pct"]),
            "range_pct": _round(last["range_pct"]),
            "type": "양봉" if close > last["open"] else "음봉" if close < last["open"] else "보합",
        },
        "moving_averages": {
            str(period): {
                "value": _round(last[f"ma{period}"], 0),
                "disparity_pct": _round((close / last[f"ma{period}"] - 1) * 100),
            }
            for period in MA_PERIODS
        },
        "ma_alignment": _alignment(last),
        "oversold": _oversold(last, thresholds),
        "long_wick": _long_wick(last, thresholds),
        "volume": _volume(last, thresholds, provisional),
        "ma_spread": _ma_spread(df, thresholds),
        "recent_events": _recent_events(df, thresholds),
    }


def _alignment(row: pd.Series) -> str:
    values = [row[f"ma{period}"] for period in MA_PERIODS]
    if all(a > b for a, b in zip(values, values[1:])):
        return "정배열"
    if all(a < b for a, b in zip(values, values[1:])):
        return "역배열"
    return "혼조"


def _oversold(row: pd.Series, thresholds: Thresholds) -> dict:
    by_disparity = bool(row["disparity20_pct"] <= thresholds.oversold_disparity20_pct)
    by_drawdown = bool(row["drawdown_pct"] <= thresholds.oversold_drawdown_pct)
    return {
        "flag": by_disparity or by_drawdown,
        "disparity20_pct": _round(row["disparity20_pct"]),
        "by_disparity20": by_disparity,
        "drawdown_pct": _round(row["drawdown_pct"]),
        "drawdown_days": thresholds.oversold_drawdown_days,
        "by_drawdown": by_drawdown,
    }


def _long_wick(row: pd.Series, thresholds: Thresholds) -> dict:
    return {
        "lower": bool(row["lower_wick_ratio"] >= thresholds.long_wick_ratio),
        "upper": bool(row["upper_wick_ratio"] >= thresholds.long_wick_ratio),
        "lower_ratio": _round(row["lower_wick_ratio"]),
        "upper_ratio": _round(row["upper_wick_ratio"]),
    }


def _volume(row: pd.Series, thresholds: Thresholds, provisional: bool) -> dict:
    ratio = row["volume_ratio"]
    if ratio >= thresholds.volume_spike_ratio:
        status = "급증"
    elif provisional:
        # 하루치가 다 차지 않은 거래량으로는 급감·평이를 가릴 수 없습니다.
        status = "집계 중"
    elif ratio <= thresholds.volume_dry_ratio:
        status = "급감"
    else:
        status = "평이"
    return {
        "volume": int(row["volume"]),
        "ratio_to_avg": _round(ratio),
        "avg_days": thresholds.volume_avg_days,
        "status": status,
    }


def _ma_spread(df: pd.DataFrame, thresholds: Thresholds) -> dict:
    """60/100/200/300일선이 한 지점으로 모이는지, 벌어지는지 판정합니다."""
    lookback = thresholds.spread_lookback_days
    now, past = df.iloc[-1], df.iloc[-1 - lookback]
    change_pct = (now["ma_spread_pct"] / past["ma_spread_pct"] - 1) * 100 if past["ma_spread_pct"] else 0.0
    if change_pct <= -thresholds.spread_change_pct:
        trend = "수렴"
    elif change_pct >= thresholds.spread_change_pct:
        trend = "확산"
    else:
        trend = "유지"

    pairs = {}
    for short, long in zip(SPREAD_PERIODS, SPREAD_PERIODS[1:]):
        pairs[f"{short}-{long}"] = {
            "gap_pct": _round((now[f"ma{short}"] / now[f"ma{long}"] - 1) * 100),
            "gap_pct_before": _round((past[f"ma{short}"] / past[f"ma{long}"] - 1) * 100),
        }
    return {
        "trend": trend,
        "spread_pct": _round(now["ma_spread_pct"]),
        "spread_pct_before": _round(past["ma_spread_pct"]),
        "change_pct": _round(change_pct),
        "lookback_days": lookback,
        "pairs": pairs,
    }


def _recent_events(df: pd.DataFrame, thresholds: Thresholds) -> list[dict]:
    """직전 며칠(당일 제외) 동안 나온 신호를 날짜별로 모읍니다."""
    events = []
    for _, row in df.iloc[-1 - thresholds.history_days : -1].iterrows():
        tags = []
        if row["lower_wick_ratio"] >= thresholds.long_wick_ratio:
            tags.append("긴 아래꼬리")
        if row["upper_wick_ratio"] >= thresholds.long_wick_ratio:
            tags.append("긴 위꼬리")
        if row["volume_ratio"] >= thresholds.volume_spike_ratio:
            tags.append("거래량 급증")
        elif row["volume_ratio"] <= thresholds.volume_dry_ratio:
            tags.append("거래량 급감")
        if (
            row["disparity20_pct"] <= thresholds.oversold_disparity20_pct
            or row["drawdown_pct"] <= thresholds.oversold_drawdown_pct
        ):
            tags.append("낙폭과대")
        if tags:
            events.append({"date": row["date"], "change_pct": _round(row["change_pct"]), "tags": tags})
    return events


def _round(value: float, digits: int = 2) -> float:
    return round(float(value), digits)
