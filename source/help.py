# help.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple
import webbrowser

import pygame

import config
from util import clamp


@dataclass(frozen=True)
class HelpUITheme:
    text: tuple[int, int, int]
    text_bright: tuple[int, int, int]
    muted: tuple[int, int, int]
    border: tuple[int, int, int]
    panel_bg: tuple[int, int, int, int]


def _ui_scale() -> float:
    try:
        return float(getattr(config, "UI_SCALE", 1.0))
    except Exception:
        return 1.0


def _s(x: float, min_v: int = 1) -> int:
    v = int(round(float(x) * _ui_scale()))
    return max(int(min_v), v)


def _wrap_text(font: pygame.font.Font, text: str, max_w: int) -> List[str]:
    if max_w <= 8:
        return [str(text)]

    lines: List[str] = []
    for para in str(text).splitlines():
        if para.strip() == "":
            lines.append("")
            continue

        words = para.split(" ")
        cur = ""
        for w in words:
            cand = w if cur == "" else (cur + " " + w)
            if font.size(cand)[0] <= max_w:
                cur = cand
            else:
                if cur:
                    lines.append(cur)
                    cur = w
                else:
                    # Hard-break a single long token.
                    cut = w
                    while cut:
                        lo = 1
                        hi = len(cut)
                        best = 1
                        while lo <= hi:
                            mid = (lo + hi) // 2
                            part = cut[:mid]
                            if font.size(part)[0] <= max_w:
                                best = mid
                                lo = mid + 1
                            else:
                                hi = mid - 1
                        lines.append(cut[:best])
                        cut = cut[best:]
                    cur = ""
        if cur:
            lines.append(cur)

    return lines


def _draw_button(
    surface: pygame.Surface,
    font: pygame.font.Font,
    rect: pygame.Rect,
    theme: HelpUITheme,
    label: str,
    *,
    enabled: bool = True,
) -> None:
    mx, my = pygame.mouse.get_pos()
    pressed = pygame.mouse.get_pressed(3)[0]
    hover = rect.collidepoint(mx, my)
    down = hover and pressed and enabled

    base_a = 185 if enabled else 130
    a = base_a
    if hover and enabled:
        a = min(255, a + 25)
    if down:
        a = min(255, a + 50)

    panel = pygame.Surface((rect.w, rect.h), flags=pygame.SRCALPHA)
    panel.fill((0, 0, 0, a))
    surface.blit(panel, (rect.x, rect.y))

    border_col = theme.border
    if hover and enabled:
        border_col = tuple(min(255, int(c) + 25) for c in theme.border)
    pygame.draw.rect(surface, border_col, rect, width=1)

    col = theme.muted if (not enabled) else (theme.text_bright if hover else theme.muted)
    t = font.render(label, True, col)
    surface.blit(t, (rect.x + (rect.w - t.get_width()) // 2, rect.y + (rect.h - t.get_height()) // 2))


def _build_help_text() -> str:
    v = getattr(config, "VERSION", "")
    title = "reXact-fps" if not v else f"reXact-fps v{v}"

    return (
        f"{title}\n"
        "\n"
        "What this is\n"
        "reXact-fps is a timing/feel testbed. You drive a cursor with a controller stick or the mouse while you can set the "
        "simulation step rate (Engine FPS) and the presentation rate (Visual FPS) independently. It is meant to make responsiveness, "
        "stepping, and smoothing trade-offs visible and comparable.\n"
        "\n"
        "Practical use\n"
        "Use it to compare how timing choices feel across systems and display configurations: different refresh rates, different sync modes "
        "(fixed vs variable), different compositors, and different driver/presentation behavior. The same Engine/Visual numbers can feel different "
        "depending on the full pipeline from input sampling to display update.\n"
        "\n"
        "Engine FPS vs Visual FPS\n"
        "Engine FPS is the fixed-step simulation rate. The simulation (including when input becomes part of the simulated state) advances only on "
        "engine steps. Visual FPS is how often frames are presented.\n"
        "\n"
        "If Visual FPS is higher than Engine FPS, multiple frames may show the same simulation state unless interpolation is enabled. If Engine FPS is "
        "higher than Visual FPS, the simulation can advance multiple steps between frames; you see fewer frames, but each frame reflects a more recent "
        "simulation state.\n"
        "\n"
        "Real-time reticle vs simulated dot\n"
        "The wireframe reticle is a best-effort 'real time' reference of your input. The solid reticle is the simulated state, your 'character'.\n"
        "\n"
        "In controller mode, the reticle is integrated at render-time from the latest stick values to estimate where the cursor would be if the engine "
        "were stepping continuously. When Engine FPS is low (or when the engine cannot keep up), the wireframe reticle can move ahead of the simulated dot. That "
        "separation is intentional: it makes fixed-step latency and stair-stepping visible, 'where I'm pointing to be' vs 'where I am'.\n"
        "\n"
        "Mouse mode and polling\n"
        "Mouse mode uses a fixed-step approach: on each engine step, the simulation reads the mouse position and snaps the simulated dot to it. "
        "This means the input sampling that matters to the simulation is gated by Engine FPS. If Engine FPS is low, the simulation only receives new "
        "mouse positions at that cadence, even if the OS cursor and display are updating smoothly.\n"
        "\n"
        "Interpolation\n"
        "Interpolation is rendering-only. When enabled, the rendered glowing dot is blended between the previous and current simulated positions based on "
        "how far the main loop has progressed into the next engine step. This can reduce visible stepping when Visual FPS exceeds Engine FPS, but it does "
        "not change when input becomes simulation.\n"
        "\n"
        "The reticle is not interpolated by this toggle (it is already “as current as possible”), and the target is also not interpolated. The target is "
        "drawn at its simulated position for simplicity and to keep the control-side reticle rendering as stable as possible.\n"
        "\n"
        "Examples that tend to show differences clearly\n"
        "Engine 120 / Visual 60 often feels “snappier” than Engine 60 / Visual 120, even though the second configuration presents more frames. With a "
        "higher engine rate, the simulation reacts to input more often, and the frames you do present are less likely to show an old state. With a "
        "higher visual rate but a lower engine rate, interpolation can make motion look smoother, but input is still incorporated only on engine steps.\n"
        "\n"
        "This is also a decent stand-in for frame insertion / frame generation: extra in-between frames can look smoother, but if those frames are not "
        "advancing the simulation and not incorporating new input, responsiveness does not improve in the same way.\n"
        "\n"
        "Performance and limits\n"
        "The maximum achievable Engine FPS and Visual FPS depend on your system and display pipeline. The app is lightweight (pygame), but very high "
        "resolutions and/or very high FPS targets may be unattainable.\n"
        "\n"
        "If you are not reaching a desired Engine FPS, try raising Visual FPS substantially (or set Visual FPS to 0 for uncapped) while testing. A low "
        "Visual FPS cap can become the pacing ceiling for how often the main loop presents work, and lifting that ceiling can make it easier to see what "
        "the simulation can actually sustain on your system.\n"
        "\n"
        "This release is built with Nuitka. Nuitka translates Python modules into C and compiles them with a native compiler, bundling the CPython runtime. "
        "In practice this can reduce overhead and often runs faster than executing the same code as plain Python on the same machine.\n"
        "\n"
        "The on-screen measured Engine and Visual rates are what the program actually achieves, not what you requested.\n"
        "\n"
        "How to use it\n"
        "Adjust Engine FPS and Visual FPS and move the cursor. Try matched values (e.g. 120/120) and mismatched values (e.g. 60/240, 240/60, 30/240). "
        "Toggle interpolation and compare what changes visually versus what changes in response. Watch the reticle vs the simulated dot when the engine is "
        "intentionally slow: the gap is part of what you are measuring.\n"
        "\n"
        "Controls\n"
        "Shift: Toggle the main HUD.\n"
        "Ctrl: Toggle mouse mode.\n"
        "I: Toggle interpolation.\n"
        "Esc: Close this dialog.\n"
        "Mouse wheel / PgUp / PgDn: Scroll.\n"
        "\n"
        "Notes\n"
        "“Visual FPS = 0” means uncapped presentation.\n"
        "\n"
        "Repository\n"
        f"{getattr(config, 'PROJECT_URL', 'https://github.com/Retzilience/reXact-fps')}\n"
        "\n"
        "made by retzilience.\n"
        "\n"
        "License\n"
        "Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International (CC BY-NC-SA 4.0).\n"
        "Non-commercial use only. Derivative works and redistributions must credit the original project and creator and must be shared under the same license.\n"
    )



def _is_discreet_line(line: str) -> bool:
    return line.strip().lower() == "made by retzilience."


class _HelpDialog:
    def __init__(self, *, font: pygame.font.Font, theme: HelpUITheme, project_url: str) -> None:
        self.font = font
        self.theme = theme
        self.project_url = str(project_url)

        self.visible: bool = True

        self._rect = pygame.Rect(0, 0, 640, 420)
        self._btn_close_x = pygame.Rect(0, 0, 0, 0)
        self._btn_github = pygame.Rect(0, 0, 0, 0)

        self._title_y = 0
        self._body_rect = pygame.Rect(0, 0, 0, 0)

        self._scroll_y = 0
        self._content_h = 0
        self._wrapped_lines: List[str] = []

        self._scroll_dragging = False
        self._scroll_drag_offset_y = 0

        self._small_font: pygame.font.Font = self._make_small_font(self.font)
        self._text = _build_help_text()

    def _make_small_font(self, base: pygame.font.Font) -> pygame.font.Font:
        # Slightly smaller than the main body font, but not “ant sized”.
        try:
            base_h = int(base.get_height())
            small_px = max(12, int(round(float(base_h) * 0.92)))
            return pygame.font.Font(None, small_px)
        except Exception:
            return base

    def _clamp_scroll(self) -> None:
        max_scroll = max(0, int(self._content_h - self._body_rect.h))
        self._scroll_y = int(clamp(float(self._scroll_y), 0.0, float(max_scroll)))

    def _scrollbar_rects(self) -> Tuple[Optional[pygame.Rect], Optional[pygame.Rect]]:
        if self._content_h <= self._body_rect.h:
            return (None, None)

        track_w = _s(10, 7)
        track = pygame.Rect(
            self._body_rect.right - track_w - _s(4, 3),
            self._body_rect.y + _s(4, 3),
            track_w,
            self._body_rect.h - _s(8, 6),
        )

        frac = self._body_rect.h / float(max(1, self._content_h))
        thumb_h = max(_s(26, 16), int(round(float(track.h) * frac)))

        max_scroll = max(1, int(self._content_h - self._body_rect.h))
        denom = float(max(1, track.h - thumb_h))
        t = float(self._scroll_y) / float(max_scroll)
        t = clamp(t, 0.0, 1.0)
        tpos = int(round(t * denom))

        thumb = pygame.Rect(track.x, track.y + tpos, track.w, thumb_h)
        return (track, thumb)

    def _set_scroll_from_thumb(self, track: pygame.Rect, thumb_h: int, thumb_y: int) -> None:
        max_scroll = max(0, int(self._content_h - self._body_rect.h))
        if max_scroll <= 0:
            self._scroll_y = 0
            return

        denom = float(max(1, track.h - thumb_h))
        t = (float(thumb_y) - float(track.y)) / denom
        t = clamp(t, 0.0, 1.0)
        self._scroll_y = int(round(t * float(max_scroll)))
        self._clamp_scroll()

    def layout(self, win_w: int, win_h: int) -> None:
        # Recompute the discreet font in case the base font changed with UI scale.
        self._small_font = self._make_small_font(self.font)

        w = int(round(float(win_w) * 0.66))
        h = int(round(float(win_h) * 0.70))
        w = int(clamp(float(w), 560.0, float(max(560, win_w - _s(40)))))
        h = int(clamp(float(h), 380.0, float(max(380, win_h - _s(40)))))

        self._rect = pygame.Rect(0, 0, w, h)
        self._rect.center = (win_w // 2, win_h // 2)

        pad = _s(18, 10)
        btn_h = _s(34, 26)
        btn_w = _s(160, 120)

        self._btn_github = pygame.Rect(0, 0, btn_w, btn_h)
        self._btn_github.right = self._rect.right - pad
        self._btn_github.bottom = self._rect.bottom - pad

        x_size = _s(26, 20)
        self._btn_close_x = pygame.Rect(0, 0, x_size, x_size)
        self._btn_close_x.right = self._rect.right - pad
        self._btn_close_x.y = self._rect.y + pad

        title_h = max(_s(26, 20), int(self.font.get_linesize()))
        self._title_y = self._rect.y + pad

        body_top = self._title_y + title_h + _s(12, 8)
        body_bottom = self._btn_github.y - _s(12, 8)
        body_h = max(_s(120, 80), body_bottom - body_top)
        self._body_rect = pygame.Rect(self._rect.x + pad, body_top, self._rect.w - pad * 2, body_h)

        # Wrap text for the body width; reserve room for scrollbar.
        wrap_w = max(40, self._body_rect.w - _s(20, 14))
        self._wrapped_lines = _wrap_text(self.font, self._text, wrap_w)
        self._content_h = len(self._wrapped_lines) * int(self.font.get_linesize())

        self._clamp_scroll()

    def _open_github(self) -> None:
        try:
            webbrowser.open(self.project_url)
        except Exception:
            pass

    def _scroll_by_pixels(self, dy_px: int) -> None:
        self._scroll_y = int(self._scroll_y + int(dy_px))
        self._clamp_scroll()

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not self.visible:
            return False

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.visible = False
                return True

            line_h = int(self.font.get_linesize())
            page = max(line_h, int(self._body_rect.h * 0.85))

            if event.key == pygame.K_UP:
                self._scroll_by_pixels(-line_h * 2)
                return True
            if event.key == pygame.K_DOWN:
                self._scroll_by_pixels(line_h * 2)
                return True
            if event.key == pygame.K_PAGEUP:
                self._scroll_by_pixels(-page)
                return True
            if event.key == pygame.K_PAGEDOWN:
                self._scroll_by_pixels(page)
                return True
            if event.key == pygame.K_HOME:
                self._scroll_y = 0
                self._clamp_scroll()
                return True
            if event.key == pygame.K_END:
                self._scroll_y = max(0, int(self._content_h - self._body_rect.h))
                self._clamp_scroll()
                return True

        if self._scroll_dragging:
            if event.type == pygame.MOUSEMOTION:
                _mx, my = event.pos
                track, thumb = self._scrollbar_rects()
                if track is not None and thumb is not None:
                    thumb_y = my - self._scroll_drag_offset_y
                    self._set_scroll_from_thumb(track, thumb.h, thumb_y)
                return True

            if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                self._scroll_dragging = False
                self._scroll_drag_offset_y = 0
                return True

            return True  # modal drag: consume

        if event.type == pygame.MOUSEWHEEL:
            mx, my = pygame.mouse.get_pos()
            if self._body_rect.collidepoint(mx, my):
                dy = float(getattr(event, "precise_y", event.y))
                self._scroll_y -= int(round(dy * float(self.font.get_linesize()) * 2.0))
                self._clamp_scroll()
                return True
            return True  # modal: consume

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos

            # Click outside closes (fast exit, still modal).
            if not self._rect.collidepoint(mx, my):
                self.visible = False
                return True

            if self._btn_close_x.collidepoint(mx, my):
                self.visible = False
                return True

            if self._btn_github.collidepoint(mx, my):
                self._open_github()
                return True

            # Scrollbar click/drag.
            track, thumb = self._scrollbar_rects()
            if track is not None and thumb is not None and track.collidepoint(mx, my):
                if thumb.collidepoint(mx, my):
                    self._scroll_dragging = True
                    self._scroll_drag_offset_y = my - thumb.y
                else:
                    # Click-jump: center the thumb around the click.
                    target_thumb_y = my - (thumb.h // 2)
                    self._set_scroll_from_thumb(track, thumb.h, target_thumb_y)
                return True

            return True  # modal: consume

        return False

    def draw(self, surface: pygame.Surface) -> None:
        if not self.visible:
            return

        # Dim background (opaque enough to read cleanly).
        dim = pygame.Surface(surface.get_size(), flags=pygame.SRCALPHA)
        dim.fill((0, 0, 0, 210))
        surface.blit(dim, (0, 0))

        # Panel (force high opacity regardless of the global HUD theme alpha).
        panel = pygame.Surface((self._rect.w, self._rect.h), flags=pygame.SRCALPHA)
        bg = self.theme.panel_bg
        panel_alpha = max(235, int(bg[3]))
        panel.fill((int(bg[0]), int(bg[1]), int(bg[2]), panel_alpha))
        surface.blit(panel, (self._rect.x, self._rect.y))
        pygame.draw.rect(surface, self.theme.border, self._rect, width=1)

        pad = _s(18, 10)

        # Title.
        title = "Help / About"
        t = self.font.render(title, True, self.theme.text_bright)
        surface.blit(t, (self._rect.x + pad, self._title_y))

        # Close decoration (X).
        pygame.draw.rect(surface, self.theme.border, self._btn_close_x, width=1)
        x_col = self.theme.text_bright
        pygame.draw.line(surface, x_col, self._btn_close_x.topleft, self._btn_close_x.bottomright, width=1)
        pygame.draw.line(surface, x_col, self._btn_close_x.topright, self._btn_close_x.bottomleft, width=1)

        # Body (clipped).
        pygame.draw.rect(surface, self.theme.border, self._body_rect, width=1)
        clip_prev = surface.get_clip()
        surface.set_clip(self._body_rect)

        line_h = int(self.font.get_linesize())
        y0 = self._body_rect.y - int(self._scroll_y)
        x0 = self._body_rect.x + _s(8, 6)

        for i, ln in enumerate(self._wrapped_lines):
            y = y0 + i * line_h
            if y + line_h < self._body_rect.y:
                continue
            if y > self._body_rect.bottom:
                break

            if _is_discreet_line(ln):
                f = self._small_font
                col = self.theme.muted
                tt = f.render(ln, True, col)
                yy = y + max(0, (line_h - int(f.get_linesize())) // 2)
                surface.blit(tt, (x0, yy))
            else:
                col = self.theme.text_bright if ln.strip() else self.theme.muted
                tt = self.font.render(ln, True, col)
                surface.blit(tt, (x0, y))

        surface.set_clip(clip_prev)

        # Scrollbar (clickable + draggable).
        track, thumb = self._scrollbar_rects()
        if track is not None and thumb is not None:
            pygame.draw.rect(surface, (60, 70, 90), track)
            pygame.draw.rect(surface, (140, 160, 190), thumb)
            pygame.draw.rect(surface, self.theme.border, track, width=1)

        # Button.
        _draw_button(surface, self.font, self._btn_github, self.theme, "GitHub", enabled=True)


class HelpManager:
    def __init__(self, *, project_url: str, theme: HelpUITheme) -> None:
        self.project_url = str(project_url)
        self.theme = theme

        self._corner_pad = 12
        self._btn_help = pygame.Rect(0, 0, 0, 0)

        self._dialog: Optional[_HelpDialog] = None

        self._last_win_w: int = 0
        self._last_win_h: int = 0

    def dialog_active(self) -> bool:
        return self._dialog is not None and self._dialog.visible

    def layout(self, font: pygame.font.Font, win_w: int, win_h: int) -> None:
        self._last_win_w = int(win_w)
        self._last_win_h = int(win_h)

        label = "Help / About"
        tw, th = font.size(label)
        pad_x = _s(10, 8)
        pad_y = _s(6, 5)

        self._btn_help = pygame.Rect(
            win_w - self._corner_pad - (tw + pad_x * 2),
            self._corner_pad,
            tw + pad_x * 2,
            th + pad_y * 2,
        )

        if self._dialog is not None:
            self._dialog.font = font
            self._dialog.layout(win_w, win_h)

    def handle_event(self, event: pygame.event.Event, font: pygame.font.Font) -> bool:
        if self._dialog is not None and self._dialog.visible:
            return self._dialog.handle_event(event)

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            if self._btn_help.collidepoint(mx, my):
                self._dialog = _HelpDialog(font=font, theme=self.theme, project_url=self.project_url)
                if self._last_win_w > 0 and self._last_win_h > 0:
                    self._dialog.layout(self._last_win_w, self._last_win_h)
                else:
                    self._dialog.layout(font.get_height() * 60, font.get_height() * 40)
                return True

        return False

    def draw_corner_ui(self, surface: pygame.Surface, font: pygame.font.Font) -> None:
        mx, my = pygame.mouse.get_pos()
        pressed = pygame.mouse.get_pressed(3)[0]
        hover = self._btn_help.collidepoint(mx, my)
        down = hover and pressed

        base_a = int(self.theme.panel_bg[3])
        fill_a = base_a
        if hover:
            fill_a = min(255, base_a + 35)
        if down:
            fill_a = min(255, base_a + 70)

        panel = pygame.Surface((self._btn_help.w, self._btn_help.h), flags=pygame.SRCALPHA)
        panel.fill((0, 0, 0, fill_a))
        surface.blit(panel, (self._btn_help.x, self._btn_help.y))

        border_col = self.theme.border
        if hover:
            border_col = tuple(min(255, int(c) + 25) for c in self.theme.border)
        pygame.draw.rect(surface, border_col, self._btn_help, width=1)

        col = self.theme.text_bright if hover else self.theme.muted
        t = font.render("Help / About", True, col)
        surface.blit(
            t,
            (
                self._btn_help.x + (self._btn_help.w - t.get_width()) // 2,
                self._btn_help.y + (self._btn_help.h - t.get_height()) // 2,
            ),
        )

    def draw_dialog_overlay(self, surface: pygame.Surface) -> None:
        if self._dialog is None:
            return
        if not self._dialog.visible:
            return
        self._dialog.draw(surface)
