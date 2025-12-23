from __future__ import annotations

TITLE = "reXact-fps"
VERSION = "0.4"

# Project / update
PROJECT_URL = "https://github.com/Retzilience/reXact-fps"
RELEASES_URL = "https://github.com/Retzilience/reXact-fps/releases"
UPDATE_DESCRIPTOR_URL = "https://raw.githubusercontent.com/Retzilience/reXact-fps/main/version.upd"
UPDATE_CHECK_DELAY_S = 2.0
UPDATE_HTTP_TIMEOUT_S = 6.0

# Window (defaults / presets)
WINDOW_W = 1280
WINDOW_H = 720

# Minimum window size (prevents HUD overlap / unusable dropdowns)
MIN_WINDOW_W = 800
MIN_WINDOW_H = 600

CANVAS_MARGIN = 12

# Global UI scale (0.80 = 20% smaller)
UI_SCALE = 1

# Ball
BALL_RADIUS = 14
BALL_SPEED_PX_S = 700.0
GLOW_DURATION_S = 0.5

# Target (defaults)
TARGET_SIZE_PCT_DEFAULT = 165
TARGET_SIZE_PCT_MIN = 120
TARGET_SIZE_PCT_MAX = 500

TARGET_SPEED_PX_S_DEFAULT = 170
TARGET_SPEED_PX_S_MIN = 60
TARGET_SPEED_PX_S_MAX = 420

TARGET_FLASH_DURATION_S = 0.35

# Engine and visual FPS ranges
ENGINE_FPS_MIN = 10
ENGINE_FPS_MAX = 360

VISUAL_FPS_MIN = 0  # 0 means uncapped
VISUAL_FPS_MAX = 360

# Slider snapping points (soft snap)
SNAP_POINTS = [24, 30, 40, 60, 120, 144, 210, 300]

# Default rates
DEFAULT_ENGINE_FPS = 120
DEFAULT_VISUAL_FPS = 60

# Deadzone relaxation (enabled by default)
DEFAULT_DEADZONE_RELAXATION = True
RELAXED_DEADZONE = 0.16
UNRELAXED_DEADZONE = 0.00

# Visual style
BG_COLOR = (14, 16, 20)
BORDER_COLOR = (40, 46, 60)

HUD_BG = (0, 0, 0, 150)
HUD_BORDER = (90, 100, 120)
HUD_TEXT = (210, 210, 210)
HUD_TEXT_BRIGHT = (235, 235, 235)
HUD_MUTED = (170, 180, 195)

MINIPANEL_BG = (0, 0, 0, 165)

BALL_BASE_COLOR = (235, 235, 235)

# Colors are kept (purely index-based). Labels are intentionally raw (“button N”).
BUTTON_COLORS = {
    0: (80, 160, 255),
    1: (255, 90, 90),
    2: (255, 110, 255),
    3: (120, 255, 130),
    4: (180, 200, 255),
    5: (90, 255, 255),
    6: (255, 210, 90),
    15: (200, 190, 255),
    7: (185, 135, 255),
    8: (125, 255, 225),
    9: (255, 150, 80),
    10: (220, 255, 90),
    16: (255, 120, 190),
    17: (120, 190, 255),
    11: (130, 175, 255),
    12: (255, 130, 175),
    13: (175, 255, 130),
    14: (255, 175, 130),
}

BUTTON_COLOR_PALETTE = [
    (80, 160, 255),
    (255, 90, 90),
    (255, 110, 255),
    (120, 255, 130),
    (255, 210, 90),
    (90, 255, 255),
    (255, 150, 80),
    (220, 255, 90),
    (185, 135, 255),
    (125, 255, 225),
    (180, 200, 255),
    (200, 190, 255),
    (255, 130, 175),
    (130, 175, 255),
    (175, 255, 130),
    (255, 175, 130),
]


def get_button_color(button_index: int) -> tuple[int, int, int]:
    if button_index in BUTTON_COLORS:
        return BUTTON_COLORS[button_index]
    if BUTTON_COLOR_PALETTE:
        return BUTTON_COLOR_PALETTE[button_index % len(BUTTON_COLOR_PALETTE)]
    return (235, 235, 235)


def get_button_label(button_index: int) -> str:
    return f"button {int(button_index)}"


TARGET_OUTLINE_COLOR = (200, 200, 200)
TARGET_HIT_COLOR = (255, 220, 80)
