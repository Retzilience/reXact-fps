# video.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import pygame

import config


@dataclass(frozen=True)
class ResolutionPreset:
    w: int
    h: int
    aspect: str

    def label(self) -> str:
        return f"{self.w}×{self.h} ({self.aspect})"

    def as_tuple(self) -> Tuple[int, int]:
        return (self.w, self.h)


def default_presets() -> List[ResolutionPreset]:
    return [
        # 4:3
        ResolutionPreset(800, 600, "4:3"),
        ResolutionPreset(1024, 768, "4:3"),
        ResolutionPreset(1280, 960, "4:3"),
        ResolutionPreset(1600, 1200, "4:3"),
        # 16:9
        ResolutionPreset(1280, 720, "16:9"),
        ResolutionPreset(1600, 900, "16:9"),
        ResolutionPreset(1920, 1080, "16:9"),
        ResolutionPreset(2560, 1440, "16:9"),
        ResolutionPreset(3840, 2160, "16:9"),
        # 21:9
        ResolutionPreset(2560, 1080, "21:9"),
        ResolutionPreset(3440, 1440, "21:9"),
        ResolutionPreset(3840, 1600, "21:9"),
    ]


def available_fullscreen_modes() -> Optional[set[Tuple[int, int]]]:
    try:
        modes = pygame.display.list_modes()
    except Exception:
        return None

    if modes == -1 or modes is None:
        return None

    out: set[Tuple[int, int]] = set()
    for m in modes:
        try:
            out.add((int(m[0]), int(m[1])))
        except Exception:
            pass
    return out


def build_resolution_items(fullscreen: bool) -> List[Tuple[str, object]]:
    presets = default_presets()

    if fullscreen:
        modes = available_fullscreen_modes()
        if modes is not None:
            presets = [p for p in presets if p.as_tuple() in modes]

    items: List[Tuple[str, object]] = []
    for p in presets:
        items.append((p.label(), p.as_tuple()))
    return items


def normalize_windowed_size(size: Tuple[int, int]) -> Tuple[int, int]:
    # Do not enforce a minimum window size; allow presets to be achieved in windowed mode.
    w = max(1, int(size[0]))
    h = max(1, int(size[1]))
    return (w, h)


def apply_display_mode(size: Tuple[int, int], fullscreen: bool) -> pygame.Surface:
    if fullscreen:
        w, h = int(size[0]), int(size[1])
        return pygame.display.set_mode((w, h), pygame.FULLSCREEN)

    w, h = normalize_windowed_size(size)
    return pygame.display.set_mode((w, h), pygame.RESIZABLE)
