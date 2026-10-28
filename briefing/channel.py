from dataclasses import dataclass
from itertools import combinations

import pandas as pd

TOUCH_PCT = 2.0  # 선에서 이 비율 안에 들어온 고점·저점은 선에 닿은 것으로 봅니다.
BREAK_PCT = 0.5  # 선을 이 비율 넘게 벗어난 봉이 있으면 그 선은 쓰지 않습니다.
MAX_TOUCHES = 3


@dataclass(frozen=True)
class Horizon:
    pivot_window: int  # 앞뒤 이 봉 수 안에서 가장 높거나 낮아야 고점·저점으로 봅니다.
    min_span: int  # 선을 긋는 두 점 사이 최소 봉 수
    lookback: int | None  # 최근 이 봉 수 안의 고점·저점만 씁니다. None이면 보이는 봉 전체.
    parallel: bool = False  # True면 하단선을 저점 하나에서 상단선과 평행하게 긋습니다.
    # 평행 하단선의 기점: "first_low"는 상단선 시작 뒤 첫 저점,
    # "support"는 저점들을 잇는 하단선(평행이 아닌 선)이 처음 닿은 저점,
    # "lowest"는 lookback 구간 안의 최저점(상승이 시작된 바닥)입니다.
    anchor: str = "first_low"


MID_TERM = Horizon(pivot_window=5, min_span=20, lookback=None, parallel=True)
SHORT_TERM = Horizon(pivot_window=3, min_span=5, lookback=60, parallel=True)
# 일봉 브리핑 차트의 단기 추세선: 하단선을 최근 70봉 안 최저점에서 상단선과 평행하게 긋습니다.
SHORT_TERM_DAILY = Horizon(pivot_window=3, min_span=5, lookback=70, parallel=True, anchor="lowest")
MID_TERM_BIG = Horizon(pivot_window=5, min_span=20, lookback=None, parallel=True, anchor="support")


def find_channel(bars: pd.DataFrame, horizon: Horizon = MID_TERM) -> dict:
    """보이는 일봉에서 고점 2~3개를 잇는 상단선과 저점 2~3개를 잇는 하단선을 찾습니다.

    ``horizon.parallel``이면 하단선은 저점을 잇지 않고, 상단선 시작 뒤 첫 저점을 지나며
    상단선과 기울기가 같은 선입니다.

    선마다 ``{"start": 봉 위치, "slope": 봉당 기울기, "value": 시작 가격, "touches": [봉 위치]}``를
    돌려주고, 조건에 맞는 선이 없으면 ``None``입니다. ``bars``의 인덱스는 0부터여야 합니다.
    """
    upper = _line(bars["high"].tolist(), horizon, upper=True)
    if horizon.parallel:
        return {"upper": upper, "lower": upper and _parallel_lower(bars["low"].tolist(), horizon, upper)}
    return {"upper": upper, "lower": _line(bars["low"].tolist(), horizon, upper=False)}


def line_value(line: dict, index: int) -> float:
    return line["value"] + line["slope"] * (index - line["start"])


def _pivots(prices: list[float], horizon: Horizon, upper: bool) -> list[int]:
    pick = max if upper else min
    window = horizon.pivot_window
    first = 0 if horizon.lookback is None else max(len(prices) - horizon.lookback, 0)
    return [
        index
        for index in range(max(first, window), len(prices) - window)
        if prices[index] == pick(prices[index - window : index + window + 1])
    ]


def _parallel_lower(prices: list[float], horizon: Horizon, upper: dict) -> dict | None:
    if horizon.anchor == "support":
        support = _line(prices, horizon, upper=False)
        first_low = support and support["touches"][0]
    elif horizon.anchor == "lowest":
        first = 0 if horizon.lookback is None else max(len(prices) - horizon.lookback, 0)
        first_low = min(range(first, len(prices)), key=lambda index: prices[index])
    else:
        first_low = next((pivot for pivot in _pivots(prices, horizon, upper=False) if pivot > upper["start"]), None)
    if first_low is None:
        return None
    return {"start": first_low, "slope": upper["slope"], "value": prices[first_low], "touches": [first_low]}


def _line(prices: list[float], horizon: Horizon, upper: bool) -> dict | None:
    side = 1 if upper else -1  # 상단선은 봉이 선 아래에, 하단선은 선 위에 있어야 합니다.
    pivots = _pivots(prices, horizon, upper)
    best, best_score = None, None
    for first, second in combinations(pivots, 2):
        if second - first < horizon.min_span:
            continue
        slope = (prices[second] - prices[first]) / (second - first)
        line = {"start": first, "slope": slope, "value": prices[first]}
        # 첫 점부터 마지막 봉까지 선을 넘은 봉이 없어야 바깥을 감싸는 선입니다.
        if any(
            side * (prices[index] / line_value(line, index) - 1) * 100 > BREAK_PCT
            for index in range(first, len(prices))
        ):
            continue
        touches = [
            pivot
            for pivot in pivots
            if pivot >= first and abs(prices[pivot] / line_value(line, pivot) - 1) * 100 <= TOUCH_PCT
        ]
        # 닿은 점이 많은 선, 같으면 더 긴 구간을 잇는 선을 고릅니다.
        score = (min(len(touches), MAX_TOUCHES), touches[-1] - touches[0])
        if best_score is None or score > best_score:
            best, best_score = {**line, "touches": touches}, score
    return best
