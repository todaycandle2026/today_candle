from briefing.channel import TOUCH_PCT, BREAK_PCT, SHORT_TERM

def horizontal_levels(prices, closes, upper=True, window=SHORT_TERM.pivot_window, min_span=SHORT_TERM.min_span):
    """고점(저항) 또는 저점(지지) 2개 이상이 같은 가격대(TOUCH_PCT 이내)에서 막히고,
    그 사이 종가가 그 가격을 BREAK_PCT 넘게 넘어서지(지지는 밑돌지) 않은 가로선."""
    side, pick = (1, max) if upper else (-1, min)
    n = len(prices)
    piv = [i for i in range(window, n - window) if prices[i] == pick(prices[i-window:i+window+1])]
    broken = lambda k, lv: side * (closes[k] / lv - 1) * 100 > BREAK_PCT
    used, out = set(), []
    for a, i in enumerate(piv):
        if i in used: continue
        touches, level = [i], prices[i]
        for j in piv[a+1:]:
            if j in used: continue
            edge = pick(level, prices[j])
            if any(broken(k, edge) for k in range(i, j+1)): break
            if abs(prices[j] / level - 1) * 100 <= TOUCH_PCT:
                touches.append(j); level = edge
        overlap = any(abs(level / r['level'] - 1) * 100 <= TOUCH_PCT and touches[0] <= r['end'] and touches[-1] >= r['start'] for r in out)
        if len(touches) >= 2 and touches[-1] - touches[0] >= min_span and not overlap:
            used.update(touches)
            brk = next((k for k in range(touches[-1]+1, n) if broken(k, level)), None)
            out.append({"level": level, "start": touches[0], "end": touches[-1], "touches": touches, "break": brk})
    return out
