# simulation.py
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Optional, Tuple

import pygame

import config
from util import clamp, distance_sq


@dataclass
class BallVisual:
    active_blink_color: Tuple[int, int, int] = config.BALL_BASE_COLOR
    glow_elapsed: float = config.GLOW_DURATION_S


@dataclass
class TargetState:
    enabled: bool = False
    pos: pygame.Vector2 = field(default_factory=lambda: pygame.Vector2(0.0, 0.0))
    vel: pygame.Vector2 = field(default_factory=lambda: pygame.Vector2(1.0, 0.0))

    size_pct: int = config.TARGET_SIZE_PCT_DEFAULT
    speed_px_s: int = config.TARGET_SPEED_PX_S_DEFAULT
    radius_px: int = 0

    hit_flash_elapsed: float = config.TARGET_FLASH_DURATION_S

    def _compute_radius(self, ball_radius: int) -> int:
        return int(round(ball_radius * (self.size_pct / 100.0)))

    def set_params(self, ball_radius: int, size_pct: int, speed_px_s: int) -> None:
        self.size_pct = int(clamp(float(size_pct), float(config.TARGET_SIZE_PCT_MIN), float(config.TARGET_SIZE_PCT_MAX)))
        self.speed_px_s = int(clamp(float(speed_px_s), float(config.TARGET_SPEED_PX_S_MIN), float(config.TARGET_SPEED_PX_S_MAX)))
        self.radius_px = self._compute_radius(ball_radius)

        if self.vel.length_squared() < 1e-9:
            self.vel.update(1.0, 0.0)
        self.vel = self.vel.normalize() * float(self.speed_px_s)

    def reset(self, w: int, h: int, margin: int, ball_radius: int) -> None:
        self.radius_px = self._compute_radius(ball_radius)

        self.pos.update(w * 0.65, h * 0.45)

        ang = random.random() * math.tau
        self.vel.update(math.cos(ang), math.sin(ang))
        if self.vel.length_squared() < 1e-9:
            self.vel.update(1.0, 0.0)
        self.vel = self.vel.normalize() * float(self.speed_px_s)

        self.hit_flash_elapsed = config.TARGET_FLASH_DURATION_S

        tr = self.radius_px
        self.pos.x = clamp(self.pos.x, float(margin + tr), float(w - margin - tr))
        self.pos.y = clamp(self.pos.y, float(margin + tr), float(h - margin - tr))


@dataclass
class EngineState:
    pos: pygame.Vector2
    prev_pos: pygame.Vector2

    ball_radius: int
    ball_speed: float

    visual: BallVisual
    target: TargetState


def make_initial_state(w: int, h: int, margin: int) -> EngineState:
    r = config.BALL_RADIUS
    p = pygame.Vector2(w * 0.5, h * 0.5)

    t = TargetState(enabled=False)
    t.set_params(ball_radius=r, size_pct=config.TARGET_SIZE_PCT_DEFAULT, speed_px_s=config.TARGET_SPEED_PX_S_DEFAULT)
    t.reset(w, h, margin, ball_radius=r)

    return EngineState(
        pos=p,
        prev_pos=p.copy(),
        ball_radius=r,
        ball_speed=config.BALL_SPEED_PX_S,
        visual=BallVisual(),
        target=t,
    )


def set_target_enabled(state: EngineState, enabled: bool, w: int, h: int, margin: int) -> None:
    state.target.enabled = enabled
    if enabled:
        state.target.reset(w, h, margin, ball_radius=state.ball_radius)


def clamp_state_to_bounds(state: EngineState, w: int, h: int, margin: int) -> None:
    br = state.ball_radius
    state.pos.x = clamp(state.pos.x, float(margin + br), float(w - margin - br))
    state.pos.y = clamp(state.pos.y, float(margin + br), float(h - margin - br))
    state.prev_pos.x = clamp(state.prev_pos.x, float(margin + br), float(w - margin - br))
    state.prev_pos.y = clamp(state.prev_pos.y, float(margin + br), float(h - margin - br))

    if state.target.enabled:
        tr = state.target.radius_px
        state.target.pos.x = clamp(state.target.pos.x, float(margin + tr), float(w - margin - tr))
        state.target.pos.y = clamp(state.target.pos.y, float(margin + tr), float(h - margin - tr))


def engine_step(
    state: EngineState,
    dt: float,
    w: int,
    h: int,
    margin: int,
    stick_lx: float,
    stick_ly: float,
    button_down_edges: Tuple[int, ...],
    any_button_edge: bool,
    ball_override_pos: Optional[Tuple[float, float]] = None,
) -> None:
    state.prev_pos = state.pos.copy()

    if ball_override_pos is None:
        state.pos.x += (stick_lx * state.ball_speed) * dt
        state.pos.y += (stick_ly * state.ball_speed) * dt
    else:
        state.pos.x = float(ball_override_pos[0])
        state.pos.y = float(ball_override_pos[1])

    br = state.ball_radius
    state.pos.x = clamp(state.pos.x, float(margin + br), float(w - margin - br))
    state.pos.y = clamp(state.pos.y, float(margin + br), float(h - margin - br))

    if state.visual.glow_elapsed < config.GLOW_DURATION_S:
        state.visual.glow_elapsed += dt
        if state.visual.glow_elapsed > config.GLOW_DURATION_S:
            state.visual.glow_elapsed = config.GLOW_DURATION_S

    for b in button_down_edges:
        state.visual.active_blink_color = config.get_button_color(int(b))
        state.visual.glow_elapsed = 0.0

    if state.target.enabled:
        state.target.pos += state.target.vel * dt

        tr = state.target.radius_px
        min_tx = float(margin + tr)
        max_tx = float(w - margin - tr)
        min_ty = float(margin + tr)
        max_ty = float(h - margin - tr)

        if state.target.pos.x < min_tx:
            state.target.pos.x = min_tx
            state.target.vel.x = abs(state.target.vel.x)
        elif state.target.pos.x > max_tx:
            state.target.pos.x = max_tx
            state.target.vel.x = -abs(state.target.vel.x)

        if state.target.pos.y < min_ty:
            state.target.pos.y = min_ty
            state.target.vel.y = abs(state.target.vel.y)
        elif state.target.pos.y > max_ty:
            state.target.pos.y = max_ty
            state.target.vel.y = -abs(state.target.vel.y)

        if state.target.hit_flash_elapsed < config.TARGET_FLASH_DURATION_S:
            state.target.hit_flash_elapsed += dt
            if state.target.hit_flash_elapsed > config.TARGET_FLASH_DURATION_S:
                state.target.hit_flash_elapsed = config.TARGET_FLASH_DURATION_S

        if any_button_edge:
            inner = max(0.0, float(tr - br))
            d2 = distance_sq(state.pos.x, state.pos.y, state.target.pos.x, state.target.pos.y)
            if d2 <= inner * inner:
                state.target.hit_flash_elapsed = 0.0
