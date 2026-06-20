"""
Crucible — Decision Layer
Always-actionable decision, NO hard gate. Never freezes, never kills on thin data.
Robust to outliers (uses trimmed mean) and honest about zero-information inputs.

Decisions: LEAVE | WATCH | LEAN_AWAY | RETIRE
"""
from dataclasses import dataclass
from typing import List, Optional
import numpy as np

TREND_MIN_N = 10


@dataclass
class Decision:
    action: str
    confidence: float
    health: float
    reason: str
    n: int
    trend: Optional[float] = None


def _trimmed_mean(xs, trim=0.1):
    """Mean after dropping the top/bottom `trim` fraction — kills outlier dominance."""
    a = np.sort(np.asarray(xs, dtype=float))
    n = len(a)
    if n == 0:
        return 0.0
    k = int(n * trim)
    core = a[k:n - k] if n - 2 * k >= 1 else a
    return float(np.mean(core))


def _mean(xs):
    return float(np.mean(xs)) if len(xs) else 0.0


def _trend(returns):
    if len(returns) < TREND_MIN_N:
        return None
    mid = len(returns) // 2
    first, second = _trimmed_mean(returns[:mid]), _trimmed_mean(returns[mid:])
    diff = second - first
    scale = (abs(first) + abs(second)) / 2 + 1e-9
    return float(np.clip(diff / scale, -1.0, 1.0))


def _confidence(n, returns=None):
    """Trust grows with evidence. Consistent outcomes are strong signal, not weak."""
    return round(float(1.0 - np.exp(-n / 22.0)), 2)


def _trend_word(trend):
    if trend is None:
        return "trend n/a"
    if trend > 0.15:
        return "improving"
    if trend < -0.15:
        return "declining"
    return "flat"


def decide(returns: List[float], win_rate: float = None, soft_floor: int = 5) -> Decision:
    n = len(returns)

    if n < soft_floor:
        return Decision("WATCH", _confidence(n, returns), 0.5,
                        f"only {n} outcomes — keep running and gather signal", n, None)

    # robust center: trimmed mean resists a single freak value
    mean = _trimmed_mean(returns)
    wr = win_rate if win_rate is not None else float(np.mean([1.0 if r > 0 else 0.0 for r in returns]))
    trend = _trend(returns)
    conf = _confidence(n, returns)
    tw = _trend_word(trend)

    mean_score = float(1.0 / (1.0 + np.exp(-mean * 400)))
    trend_component = 0.5 if trend is None else (trend + 1) / 2
    health = float(np.clip(0.55 * mean_score + 0.25 * wr + 0.20 * trend_component, 0, 1))

    t = 0.0 if trend is None else trend
    strong_good = mean > 0 and t >= 0
    strong_bad = mean < 0 and t <= 0

    if strong_bad and conf >= 0.7 and mean < -0.002 and health < 0.4:
        return Decision("RETIRE", conf, round(health, 2),
                        f"sustained loss (mean={mean:+.4f}, {tw}) at confidence {conf:.2f} — cut", n, trend)

    if strong_good and conf >= 0.6:
        return Decision("LEAVE", conf, round(health, 2),
                        f"positive edge (mean={mean:+.4f}, {tw}) at confidence {conf:.2f} — keep", n, trend)

    if mean < 0:
        return Decision("LEAN_AWAY", conf, round(health, 2),
                        f"negative (mean={mean:+.4f}, {tw}) — reduce exposure", n, trend)

    if t < -0.15:
        return Decision("LEAN_AWAY", conf, round(health, 2),
                        f"declining (mean={mean:+.4f}, {tw}) — lean away", n, trend)

    if mean > 0:
        if conf >= 0.6:
            return Decision("LEAVE", conf, round(health, 2),
                            f"positive (mean={mean:+.4f}, {tw}) at confidence {conf:.2f} — keep", n, trend)
        return Decision("WATCH", conf, round(health, 2),
                        f"mildly positive (mean={mean:+.4f}, {tw}), confidence {conf:.2f} — watch", n, trend)

    return Decision("WATCH", conf, round(health, 2),
                    f"flat (mean={mean:+.4f}, {tw}) — observe", n, trend)
