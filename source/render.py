# render.py
from __future__ import annotations

from typing import Tuple

import pygame

import config
from util import clamp, ease_out_cubic, lerp_color


class RateMeter:
    def __init__(self) -> None:
        import time
        self._time = time
        self._window_start = self._time.perf_counter()
        self._count = 0
        self.value = 0.0

    def tick(self) -> None:
        self._count += 1
        now = self._time.perf_counter()
        dt = now - self._window_start
        if dt >= 1.0:
            self.value = self._count / dt
            self._count = 0
            self._window_start = now


def draw_canvas_border(surface: pygame.Surface, w: int, h: int, margin: int) -> None:
    pygame.draw.rect(
        surface,
        config.BORDER_COLOR,
        pygame.Rect(margin, margin, w - 2 * margin, h - 2 * margin),
        width=2,
    )


def draw_glowing_ball(
    surface: pygame.Surface,
    pos: pygame.Vector2,
    radius: int,
    base_color: Tuple[int, int, int],
    blink_color: Tuple[int, int, int],
    glow_elapsed: float,
) -> None:
    t = glow_elapsed / config.GLOW_DURATION_S if config.GLOW_DURATION_S > 0.0 else 1.0
    t = clamp(t, 0.0, 1.0)
    e = ease_out_cubic(t)

    ball_color = lerp_color(blink_color, base_color, e)
    glow_strength = 1.0 - e

    glow_max = int(radius * 7)
    glow_surf = pygame.Surface((glow_max * 2, glow_max * 2), flags=pygame.SRCALPHA)
    cx, cy = glow_max, glow_max

    rings = [
        (int(radius * 6.5), 18),
        (int(radius * 5.0), 28),
        (int(radius * 3.8), 42),
        (int(radius * 2.8), 60),
        (int(radius * 2.0), 84),
    ]
    for rr, a0 in rings:
        a = int(round(a0 * glow_strength))
        if a <= 0:
            continue
        pygame.draw.circle(glow_surf, (blink_color[0], blink_color[1], blink_color[2], a), (cx, cy), rr)

    surface.blit(glow_surf, (int(pos.x - glow_max), int(pos.y - glow_max)))
    pygame.draw.circle(surface, ball_color, (int(pos.x), int(pos.y)), radius)


def draw_target(surface: pygame.Surface, pos: pygame.Vector2, radius: int, flash_elapsed: float) -> None:
    t = flash_elapsed / config.TARGET_FLASH_DURATION_S if config.TARGET_FLASH_DURATION_S > 0.0 else 1.0
    t = clamp(t, 0.0, 1.0)
    e = ease_out_cubic(t)
    flash_strength = 1.0 - e

    pygame.draw.circle(surface, config.TARGET_OUTLINE_COLOR, (int(pos.x), int(pos.y)), radius, width=2)

    if flash_strength > 0.001:
        glow_max = int(radius * 5)
        glow_surf = pygame.Surface((glow_max * 2, glow_max * 2), flags=pygame.SRCALPHA)
        cx, cy = glow_max, glow_max

        rings = [
            (int(radius * 4.5), 14),
            (int(radius * 3.5), 22),
            (int(radius * 2.8), 34),
            (int(radius * 2.1), 52),
        ]
        for rr, a0 in rings:
            a = int(round(a0 * flash_strength))
            if a <= 0:
                continue
            pygame.draw.circle(
                glow_surf,
                (config.TARGET_HIT_COLOR[0], config.TARGET_HIT_COLOR[1], config.TARGET_HIT_COLOR[2], a),
                (cx, cy),
                rr,
            )
        surface.blit(glow_surf, (int(pos.x - glow_max), int(pos.y - glow_max)))

        w = 2 + int(round(5 * flash_strength))
        pygame.draw.circle(surface, config.TARGET_HIT_COLOR, (int(pos.x), int(pos.y)), radius, width=w)


def draw_reticle(surface: pygame.Surface, x: int, y: int) -> None:
    pygame.draw.line(surface, (220, 220, 220), (x - 10, y), (x - 3, y), width=1)
    pygame.draw.line(surface, (220, 220, 220), (x + 3, y), (x + 10, y), width=1)
    pygame.draw.line(surface, (220, 220, 220), (x, y - 10), (x, y - 3), width=1)
    pygame.draw.line(surface, (220, 220, 220), (x, y + 3), (x, y + 10), width=1)
    pygame.draw.circle(surface, (220, 220, 220), (x, y), 12, width=1)
