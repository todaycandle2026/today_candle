from pathlib import Path

import pandas as pd

from briefing.channel import MID_TERM, MID_TERM_BIG, SHORT_TERM, find_channel, line_value
from briefing.signals import MA_PERIODS

DAILY_BARS = 240  # 일봉 차트에 그리는 봉 수
UP, DOWN = "#e34948", "#2a78d6"  # 양봉, 음봉
INK, SUB, MUTED, GRID = "#0b0b0b", "#52514e", "#898781", "#e1e0d9"
# 추세선: (이름, 고점·저점 기준, 색, 점선 모양, 그릴 선)
# 중기 큰 추세의 상단선은 중기 추세선 상단과 같아서 하단선만 그립니다.
TRENDLINES = (
    ("중기 추세선", MID_TERM, "#c2188f", "7 4", ("upper", "lower")),
    ("중기 큰 추세", MID_TERM_BIG, "#000000", "10 3 2 3", ("lower",)),
    ("단기 추세선", SHORT_TERM, "#0e8fb5", "3 3", ("upper", "lower")),
)
CHANNEL_NAMES = {"upper": "상단", "lower": "하단"}
MA_COLORS = dict(zip(MA_PERIODS, ("#eda100", "#1baf7a", "#6250d6", "#eb6834", "#52514e")))
FONT = "-apple-system, 'Apple SD Gothic Neo', 'Noto Sans CJK KR', 'WenQuanYi Zen Hei', sans-serif"
LABEL_GAP = 16  # 겹치는 라벨을 벌리는 최소 간격(px)


def bars_required() -> int:
    """일봉 차트 전 구간에 가장 긴 이평선이 나오려면 필요한 일봉 수."""
    return DAILY_BARS + max(MA_PERIODS)


def render_charts(df: pd.DataFrame, report: dict, out_dir: str) -> dict:
    """이격도 이미지와 일봉 차트를 SVG로 저장하고 경로를 돌려줍니다.

    ``df``는 ``signals.enrich``를 거친 일봉입니다.
    """
    directory = Path(out_dir)
    directory.mkdir(parents=True, exist_ok=True)
    paths = {
        "disparity": directory / f"{report['code']}_disparity.svg",
        "daily": directory / f"{report['code']}_daily_{DAILY_BARS}.svg",
    }
    paths["disparity"].write_text(disparity_svg(report), encoding="utf-8")
    paths["daily"].write_text(daily_svg(df, report), encoding="utf-8")
    return {name: str(path.resolve()) for name, path in paths.items()}


def disparity_svg(report: dict) -> str:
    """기준일 캔들과 이동평균선의 가격 위치·이격도를 한 축에 그립니다."""
    candle, mas = report["candle"], report["moving_averages"]
    width, height, left, line_end, top, bottom = 760, 460, 80, 500, 70, 30
    values = [candle["high"], candle["low"]] + [ma["value"] for ma in mas.values()]
    low, high = _padded(min(values), max(values), 0.08)

    def y(value: float) -> float:
        return top + (high - value) / (high - low) * (height - top - bottom)

    out = _open_svg(width, height, _title(report, "캔들과 이동평균선 이격"))
    for tick in _ticks(low, high):
        out.append(f'<line x1="{left}" x2="{line_end}" y1="{y(tick):.1f}" y2="{y(tick):.1f}" stroke="{GRID}"/>')
        out.append(f'<text x="{left - 8}" y="{y(tick) + 4:.1f}" text-anchor="end" fill="{MUTED}">{tick:,}</text>')
    for period, ma in mas.items():
        out.append(
            f'<line x1="{left}" x2="{line_end}" y1="{y(ma["value"]):.1f}" y2="{y(ma["value"]):.1f}" '
            f'stroke="{MA_COLORS[int(period)]}" stroke-width="1.6" stroke-dasharray="6 4"/>'
        )

    cx, body = left + 70, 30
    color = UP if candle["close"] >= candle["open"] else DOWN
    body_top, body_bottom = y(max(candle["open"], candle["close"])), y(min(candle["open"], candle["close"]))
    out.append(f'<line x1="{cx}" x2="{cx}" y1="{y(candle["high"]):.1f}" y2="{y(candle["low"]):.1f}" stroke="{color}" stroke-width="2"/>')
    out.append(f'<rect x="{cx - body / 2}" y="{body_top:.1f}" width="{body}" height="{max(body_bottom - body_top, 1):.1f}" fill="{color}"/>')
    close_name = "현재" if report["provisional"] else "종가"
    candle_labels = [
        (y(candle["high"]), f'고가 {candle["high"]:,.0f}', SUB),
        (y(candle["open"]), f'시가 {candle["open"]:,.0f}', SUB),
        (y(candle["close"]), f'{close_name} {candle["close"]:,.0f} ({candle["change_pct"]:+.2f}%)', INK),
        (y(candle["low"]), f'저가 {candle["low"]:,.0f}', SUB),
    ]
    for label_y, text, fill in _spread_labels(candle_labels):
        # 이평선과 겹쳐도 읽히도록 글자 뒤에 흰 테두리를 둡니다.
        out.append(f'<text x="{cx + body}" y="{label_y + 4:.1f}" fill="{fill}" stroke="#ffffff" stroke-width="4" paint-order="stroke">{text}</text>')

    out.append(f'<text x="{width - 10}" y="{top - 14}" text-anchor="end" fill="{MUTED}">이격도 ({close_name}가 기준)</text>')
    ma_labels = [(y(ma["value"]), (period, ma), MA_COLORS[int(period)]) for period, ma in mas.items()]
    for label_y, (period, ma), fill in _spread_labels(ma_labels):
        out.append(f'<text x="{line_end + 10}" y="{label_y + 4:.1f}" fill="{fill}">{period}일선 {ma["value"]:,.0f}</text>')
        out.append(f'<text x="{width - 10}" y="{label_y + 4:.1f}" text-anchor="end" fill="{INK}">{ma["disparity_pct"]:+.2f}%</text>')
    out.append("</svg>")
    return "\n".join(out)


def daily_svg(df: pd.DataFrame, report: dict) -> str:
    """최근 ``DAILY_BARS``개 일봉 캔들과 이동평균선, 채널선을 그립니다."""
    bars = df.tail(DAILY_BARS).reset_index(drop=True)
    ma_columns = [f"ma{period}" for period in MA_PERIODS]
    width, height, left, right, top, bottom = 1200, 660, 70, 110, 90, 40
    trends = [
        (label, color, dash, {name: line for name, line in find_channel(bars, horizon).items() if line and name in sides})
        for label, horizon, color, dash, sides in TRENDLINES
    ]
    # 추세선이 오른쪽 끝에서 캔들 범위를 벗어나도 보이도록 축에 넣습니다.
    channel_ends = [line_value(line, len(bars) - 1) for *_, lines in trends for line in lines.values()]
    low, high = _padded(
        min([bars[["low"] + ma_columns].min().min()] + channel_ends),
        max([bars[["high"] + ma_columns].max().max()] + channel_ends),
        0.04,
    )
    step = (width - left - right) / len(bars)

    def x(index: int) -> float:
        return left + step * (index + 0.5)

    def y(value: float) -> float:
        return top + (high - value) / (high - low) * (height - top - bottom)

    title = f"일봉 {len(bars)}개 · {bars['date'].iloc[0]} ~ {bars['date'].iloc[-1]}"
    out = _open_svg(width, height, _title(report, title))
    for tick in _ticks(low, high):
        out.append(f'<line x1="{left}" x2="{width - right}" y1="{y(tick):.1f}" y2="{y(tick):.1f}" stroke="{GRID}"/>')
        out.append(f'<text x="{left - 8}" y="{y(tick) + 4:.1f}" text-anchor="end" fill="{MUTED}">{tick:,}</text>')
    for index in range(1, len(bars)):
        date = bars["date"].iloc[index]
        if date[:6] != bars["date"].iloc[index - 1][:6]:
            edge = x(index) - step / 2
            out.append(f'<line x1="{edge:.1f}" x2="{edge:.1f}" y1="{top}" y2="{height - bottom}" stroke="#f0efec"/>')
            out.append(f'<text x="{x(index):.1f}" y="{height - bottom + 18}" fill="{MUTED}">{date[2:4]}.{date[4:6]}</text>')

    body = max(step * 0.65, 1.5)
    for index, bar in bars.iterrows():
        color = UP if bar["close"] >= bar["open"] else DOWN
        body_top, body_bottom = y(max(bar["open"], bar["close"])), y(min(bar["open"], bar["close"]))
        out.append(f'<line x1="{x(index):.1f}" x2="{x(index):.1f}" y1="{y(bar["high"]):.1f}" y2="{y(bar["low"]):.1f}" stroke="{color}"/>')
        out.append(f'<rect x="{x(index) - body / 2:.1f}" y="{body_top:.1f}" width="{body:.1f}" height="{max(body_bottom - body_top, 1):.1f}" fill="{color}"/>')

    last = bars.iloc[-1]
    end_labels = [(y(last["close"]), f'{last["close"]:,.0f}', INK)]
    legend_x = left
    for period, column in zip(MA_PERIODS, ma_columns):
        color = MA_COLORS[period]
        points = " ".join(f"{x(index):.1f},{y(value):.1f}" for index, value in enumerate(bars[column]) if pd.notna(value))
        out.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="1.6" stroke-linejoin="round"/>')
        end_labels.append((y(last[column]), f"{period}일", color))
        out.append(f'<line x1="{legend_x}" x2="{legend_x + 18}" y1="50" y2="50" stroke="{color}" stroke-width="2"/>')
        out.append(f'<text x="{legend_x + 24}" y="54" fill="{SUB}">{period}일선 {last[column]:,.0f}</text>')
        legend_x += 165
    legend_x = left  # 추세선과 캔들 범례는 둘째 줄에 둡니다.
    for label, color, dash, lines in trends:
        for name, line in lines.items():
            prices = bars["high" if name == "upper" else "low"]
            end = line_value(line, len(bars) - 1)
            out.append(
                f'<line x1="{x(line["start"]):.1f}" x2="{x(len(bars) - 1):.1f}" y1="{y(line["value"]):.1f}" y2="{y(end):.1f}" '
                f'stroke="{color}" stroke-width="1.6" stroke-dasharray="{dash}"/>'
            )
            for touch in line["touches"]:
                out.append(f'<circle cx="{x(touch):.1f}" cy="{y(prices[touch]):.1f}" r="4.5" fill="none" stroke="{color}" stroke-width="1.6"/>')
            end_labels.append((y(end), f"{CHANNEL_NAMES[name]} {end:,.0f}", color))
        if lines:
            out.append(f'<line x1="{legend_x}" x2="{legend_x + 18}" y1="72" y2="72" stroke="{color}" stroke-width="2" stroke-dasharray="{dash}"/>')
            out.append(f'<text x="{legend_x + 24}" y="76" fill="{SUB}">{label}</text>')
            legend_x += 165
    out.append(f'<rect x="{legend_x}" y="67" width="10" height="10" fill="{UP}"/><text x="{legend_x + 16}" y="76" fill="{SUB}">양봉</text>')
    out.append(f'<rect x="{legend_x + 60}" y="67" width="10" height="10" fill="{DOWN}"/><text x="{legend_x + 76}" y="76" fill="{SUB}">음봉</text>')
    for label_y, text, fill in _spread_labels(end_labels):
        out.append(f'<text x="{width - right + 8}" y="{label_y + 4:.1f}" fill="{fill}">{text}</text>')
    out.append("</svg>")
    return "\n".join(out)


def _open_svg(width: int, height: int, title: str) -> list[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" font-family="{FONT}" font-size="13">',
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
        f'<text x="16" y="28" font-size="16" fill="{INK}">{title}</text>',
    ]


def _title(report: dict, subject: str) -> str:
    state = "장중 잠정" if report["provisional"] else "확정"
    return f"[{report['code']}] {subject} · {report['date']} 일봉 ({state}) · 조회 {report['generated_at']}"


def _padded(low: float, high: float, ratio: float) -> tuple[float, float]:
    pad = (high - low) * ratio or 1.0
    return low - pad, high + pad


def _ticks(low: float, high: float) -> list[int]:
    span = high - low
    step = next((s for s in (1000, 2000, 5000, 10000, 20000, 50000, 100000, 200000) if span / s <= 8), 500000)
    first = int(low // step + 1) * step
    return list(range(first, int(high) + 1, step))


def _spread_labels(labels: list[tuple]) -> list[tuple]:
    """y좌표가 겹치는 라벨을 위에서부터 차례로 밀어냅니다."""
    spread = []
    for label_y, *rest in sorted(labels, key=lambda label: label[0]):
        if spread and label_y - spread[-1][0] < LABEL_GAP:
            label_y = spread[-1][0] + LABEL_GAP
        spread.append((label_y, *rest))
    return spread
