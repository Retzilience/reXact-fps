# util.py
from __future__ import annotations

from typing import Iterable, Tuple


def clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def lerp_color(c0: Tuple[int, int, int], c1: Tuple[int, int, int], t: float) -> Tuple[int, int, int]:
    t = clamp(t, 0.0, 1.0)
    return (
        int(round(lerp(c0[0], c1[0], t))),
        int(round(lerp(c0[1], c1[1], t))),
        int(round(lerp(c0[2], c1[2], t))),
    )


def ease_out_cubic(t: float) -> float:
    t = clamp(t, 0.0, 1.0)
    u = 1.0 - t
    return 1.0 - (u * u * u)


def apply_deadzone(v: float, deadzone: float) -> float:
    if abs(v) <= deadzone:
        return 0.0
    s = 1.0 if v > 0.0 else -1.0
    v = (abs(v) - deadzone) / (1.0 - deadzone) if deadzone < 1.0 else 0.0
    return s * clamp(v, 0.0, 1.0)


def distance_sq(x0: float, y0: float, x1: float, y1: float) -> float:
    dx = x1 - x0
    dy = y1 - y0
    return dx * dx + dy * dy


def nearest_snap(value: int, snaps: Iterable[int], window: int) -> int:
    best = value
    best_d = window + 1
    for s in snaps:
        d = abs(value - s)
        if d <= window and d < best_d:
            best = s
            best_d = d
    return best
