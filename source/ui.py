from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence, Tuple

import pygame

import config
from util import clamp, nearest_snap


@dataclass
class UITheme:
    text: Tuple[int, int, int]
    text_bright: Tuple[int, int, int]
    muted: Tuple[int, int, int]
    border: Tuple[int, int, int]
    panel_bg: Tuple[int, int, int, int]
    line: Tuple[int, int, int]


def _ui_scale() -> float:
    try:
        return float(getattr(config, "UI_SCALE", 1.0))
    except Exception:
        return 1.0


def _s(x: float, min_v: int = 1) -> int:
    v = int(round(float(x) * _ui_scale()))
    return max(int(min_v), v)


def _ellipsize_info(font: pygame.font.Font, s: str, max_w: int) -> Tuple[str, bool]:
    s = str(s)
    if max_w <= 0:
        return ("", (s != ""))
    if font.size(s)[0] <= max_w:
        return (s, False)

    ell = "..."
    ell_w = font.size(ell)[0]
    if ell_w > max_w:
        return ("", True)

    lo = 0
    hi = len(s)
    best = ell
    while lo <= hi:
        mid = (lo + hi) // 2
        cand = s[:mid].rstrip() + ell
        if font.size(cand)[0] <= max_w:
            best = cand
            lo = mid + 1
        else:
            hi = mid - 1

    return (best, True)


def _ellipsize(font: pygame.font.Font, s: str, max_w: int) -> str:
    return _ellipsize_info(font, s, max_w)[0]


def _draw_tooltip_at_mouse(surface: pygame.Surface, font: pygame.font.Font, theme: UITheme, text: str) -> None:
    if not text:
        return

    mx, my = pygame.mouse.get_pos()
    pad_x = _s(10, 8)
    pad_y = _s(7, 6)
    off_x = _s(14, 10)
    off_y = _s(16, 10)

    t = font.render(text, True, theme.text_bright)
    w = t.get_width() + pad_x * 2
    h = t.get_height() + pad_y * 2

    x = mx + off_x
    y = my + off_y

    sw, sh = surface.get_size()
    if x + w > sw - 2:
        x = max(2, mx - off_x - w)
    if y + h > sh - 2:
        y = max(2, my - off_y - h)

    rect = pygame.Rect(int(x), int(y), int(w), int(h))
    panel = pygame.Surface((rect.w, rect.h), flags=pygame.SRCALPHA)
    panel.fill((0, 0, 0, 230))
    surface.blit(panel, (rect.x, rect.y))
    pygame.draw.rect(surface, theme.border, rect, width=1)
    surface.blit(t, (rect.x + pad_x, rect.y + pad_y))


class Widget:
    rect: pygame.Rect

    def handle_event(self, event: pygame.event.Event) -> bool:
        raise NotImplementedError

    def draw(self, surface: pygame.Surface) -> None:
        raise NotImplementedError


class CheckboxRow(Widget):
    def __init__(
        self,
        rect: pygame.Rect,
        label: str,
        checked: bool,
        font: pygame.font.Font,
        theme: UITheme,
        on_change: Optional[Callable[[bool], None]] = None,
    ) -> None:
        self.rect = rect
        self.label = label
        self.checked = checked
        self.font = font
        self.theme = theme
        self.on_change = on_change

        self._tooltip_text: Optional[str] = None
        self._tooltip_rect: Optional[pygame.Rect] = None

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self.checked = not self.checked
                if self.on_change is not None:
                    self.on_change(self.checked)
                return True
        return False

    def draw(self, surface: pygame.Surface) -> None:
        box_sz = _s(18, 12)
        gap = _s(10, 6)

        box = pygame.Rect(0, 0, box_sz, box_sz)
        box.x = self.rect.x
        box.centery = self.rect.centery

        label_x = box.right + gap
        label_max_w = max(0, self.rect.w - (label_x - self.rect.x))

        label_fit, was_trunc = _ellipsize_info(self.font, self.label, label_max_w)
        label_txt = self.font.render(label_fit, True, self.theme.text)
        surface.blit(label_txt, (label_x, self.rect.y + (self.rect.h - label_txt.get_height()) // 2))

        pygame.draw.rect(surface, self.theme.border, box, width=1)
        if self.checked:
            inner = box.inflate(-_s(6, 4), -_s(6, 4))
            pygame.draw.rect(surface, self.theme.text_bright, inner, border_radius=_s(2, 2))

        if was_trunc:
            self._tooltip_text = str(self.label)
            self._tooltip_rect = pygame.Rect(label_x, self.rect.y, max(1, label_max_w), self.rect.h)
        else:
            self._tooltip_text = None
            self._tooltip_rect = None

    def draw_overlay(self, surface: pygame.Surface) -> None:
        if not self._tooltip_text or self._tooltip_rect is None:
            return
        mx, my = pygame.mouse.get_pos()
        if self._tooltip_rect.collidepoint(mx, my):
            _draw_tooltip_at_mouse(surface, self.font, self.theme, self._tooltip_text)


class TextRow(Widget):
    def __init__(self, rect: pygame.Rect, text: str, font: pygame.font.Font, theme: UITheme) -> None:
        self.rect = rect
        self.text = text
        self.font = font
        self.theme = theme

    def handle_event(self, event: pygame.event.Event) -> bool:
        return False

    def draw(self, surface: pygame.Surface) -> None:
        txt = self.font.render(self.text, True, self.theme.muted)
        surface.blit(txt, (self.rect.x, self.rect.y + (self.rect.h - txt.get_height()) // 2))


class DropdownRow(Widget):
    """
    Two-pass dropdown:
    - draw() renders only the closed row
    - draw_overlay() renders the expanded list on top of everything else + tooltips

    Fixes:
    - long selected/value strings are ellipsized to avoid overflow
    - MOUSEWHEEL uses precise_y when available (touchpads) and accumulates fractional deltas
    - scrollbar area no longer selects items; it supports click-jump and thumb dragging
    """

    def __init__(
        self,
        rect: pygame.Rect,
        label: str,
        font: pygame.font.Font,
        theme: UITheme,
        get_items: Callable[[], List[Tuple[str, object]]],
        get_selected_payload: Callable[[], Optional[object]],
        on_select_payload: Callable[[Optional[object]], None],
        label_w: int = 150,
    ) -> None:
        self.rect = rect
        self.label = label
        self.font = font
        self.theme = theme
        self.get_items = get_items
        self.get_selected_payload = get_selected_payload
        self.on_select_payload = on_select_payload
        self.label_w = int(label_w)

        self.expanded = False

        self.item_h = _s(24, 16)
        self.max_visible = 10
        self.scroll = 0

        self._scroll_accum = 0.0
        self._scroll_dragging = False
        self._scroll_drag_offset_y = 0

        self._tooltip_text: Optional[str] = None
        self._tooltip_rect: Optional[pygame.Rect] = None

    def _value_rect(self) -> pygame.Rect:
        pad_y = _s(2, 2)
        return pygame.Rect(self.rect.x + self.label_w, self.rect.y + pad_y, self.rect.w - self.label_w, self.rect.h - pad_y * 2)

    def _drop_rect(self, vrect: pygame.Rect, n_visible: int) -> pygame.Rect:
        gap = _s(2, 2)
        return pygame.Rect(vrect.x, vrect.bottom + gap, vrect.w, n_visible * self.item_h + gap)

    def _clamp_scroll(self, total: int) -> None:
        if total <= self.max_visible:
            self.scroll = 0
            return
        max_scroll = max(0, total - self.max_visible)
        if self.scroll < 0:
            self.scroll = 0
        elif self.scroll > max_scroll:
            self.scroll = max_scroll

    def _scroll_by(self, dy: int) -> None:
        total = len(self.get_items())
        if total <= self.max_visible:
            self.scroll = 0
            return
        self.scroll += int(dy)
        self._clamp_scroll(total)

    def _scrollbar_rects(self, drop: pygame.Rect, total: int, n_visible: int) -> Tuple[Optional[pygame.Rect], Optional[pygame.Rect]]:
        if total <= n_visible:
            return (None, None)
        track = pygame.Rect(drop.right - _s(6, 4), drop.y + _s(2, 2), _s(4, 3), drop.h - _s(4, 4))
        frac = n_visible / float(total)
        thumb_h = max(_s(10, 8), int(round(track.h * frac)))
        max_scroll = max(1, total - n_visible)
        tpos = int(round((self.scroll / float(max_scroll)) * (track.h - thumb_h)))
        thumb = pygame.Rect(track.x, track.y + tpos, track.w, thumb_h)
        return (track, thumb)

    def _set_scroll_from_thumb(self, track: pygame.Rect, thumb_h: int, thumb_y: int, total: int, n_visible: int) -> None:
        max_scroll = max(0, total - n_visible)
        if max_scroll <= 0:
            self.scroll = 0
            return
        denom = float(max(1, track.h - thumb_h))
        t = (thumb_y - track.y) / denom
        t = clamp(t, 0.0, 1.0)
        self.scroll = int(round(t * max_scroll))
        self._clamp_scroll(total)

    def _collapse(self) -> None:
        self.expanded = False
        self._scroll_dragging = False
        self._scroll_drag_offset_y = 0
        self._scroll_accum = 0.0

    def handle_event(self, event: pygame.event.Event) -> bool:
        vrect = self._value_rect()

        if self.expanded and self._scroll_dragging:
            items = self.get_items()
            total = len(items)
            n_vis = min(total, self.max_visible)
            drop = self._drop_rect(vrect, n_vis)
            track, thumb = self._scrollbar_rects(drop, total, n_vis)

            if event.type == pygame.MOUSEMOTION and track is not None and thumb is not None:
                mx, my = event.pos
                if drop.collidepoint(mx, my):
                    thumb_y = my - self._scroll_drag_offset_y
                    self._set_scroll_from_thumb(track, thumb.h, thumb_y, total, n_vis)
                    return True

            if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                self._scroll_dragging = False
                self._scroll_drag_offset_y = 0
                return True

            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self._collapse()
                return True

            return True

        if event.type == pygame.MOUSEWHEEL and self.expanded:
            mx, my = pygame.mouse.get_pos()
            items = self.get_items()
            total = len(items)
            n_vis = min(total, self.max_visible)
            drop = self._drop_rect(vrect, n_vis)
            if vrect.collidepoint(mx, my) or drop.collidepoint(mx, my):
                dy = float(getattr(event, "precise_y", event.y))
                # Pygame: up = +, down = -. We want down => +scroll.
                self._scroll_accum += -dy
                step = 0
                if self._scroll_accum >= 1.0:
                    step = int(self._scroll_accum)
                elif self._scroll_accum <= -1.0:
                    step = int(self._scroll_accum)
                if step != 0:
                    self._scroll_by(step)
                    self._scroll_accum -= float(step)
                return True
            return False

        if event.type == pygame.MOUSEBUTTONDOWN and self.expanded and event.button in (4, 5):
            mx, my = event.pos
            items = self.get_items()
            total = len(items)
            n_vis = min(total, self.max_visible)
            drop = self._drop_rect(vrect, n_vis)
            if vrect.collidepoint(mx, my) or drop.collidepoint(mx, my):
                self._scroll_by(-1 if event.button == 5 else 1)
                return True
            return False

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            if vrect.collidepoint(mx, my):
                self.expanded = not self.expanded
                self._scroll_dragging = False
                self._scroll_drag_offset_y = 0
                self._scroll_accum = 0.0
                if self.expanded:
                    self.scroll = 0
                    self._clamp_scroll(len(self.get_items()))
                return True

            if self.expanded:
                items = self.get_items()
                total = len(items)
                n_vis = min(total, self.max_visible)
                self._clamp_scroll(total)
                drop = self._drop_rect(vrect, n_vis)

                if drop.collidepoint(mx, my):
                    track, thumb = self._scrollbar_rects(drop, total, n_vis)
                    if track is not None and thumb is not None and track.collidepoint(mx, my):
                        if thumb.collidepoint(mx, my):
                            self._scroll_dragging = True
                            self._scroll_drag_offset_y = my - thumb.y
                        else:
                            target_thumb_y = my - (thumb.h // 2)
                            self._set_scroll_from_thumb(track, thumb.h, target_thumb_y, total, n_vis)
                        return True

                    scrollbar_reserve = _s(10, 8)
                    if mx >= drop.right - scrollbar_reserve:
                        return True

                    rel_y = my - (drop.y + 1)
                    row = int(rel_y // self.item_h)
                    idx = self.scroll + row
                    if 0 <= idx < total:
                        _display, payload = items[idx]
                        self.on_select_payload(payload)
                        self._collapse()
                        return True

                self._collapse()
                return True

        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            if self.expanded:
                self._collapse()
                return True
            return False

        return False

    def draw(self, surface: pygame.Surface) -> None:
        label_fit, label_trunc = _ellipsize_info(self.font, self.label, max(0, self.label_w - _s(6, 4)))
        label_txt = self.font.render(label_fit, True, self.theme.text)
        label_rect = pygame.Rect(self.rect.x, self.rect.y, self.label_w, self.rect.h)
        surface.blit(label_txt, (self.rect.x, self.rect.y + (self.rect.h - label_txt.get_height()) // 2))

        vrect = self._value_rect()
        pygame.draw.rect(surface, self.theme.border, vrect, width=1)

        items = self.get_items()
        sel = self.get_selected_payload()
        shown: Optional[str] = None
        for display, payload in items:
            if payload == sel:
                shown = display
                break
        if shown is None:
            if isinstance(sel, tuple) and len(sel) == 2:
                try:
                    w = int(sel[0])
                    h = int(sel[1])
                    shown = f"{w}×{h} (custom)"
                except Exception:
                    shown = "(none)"
            else:
                shown = "(none)"

        pad_l = _s(6, 4)
        arrow_reserve = _s(22, 16)
        max_w = max(0, vrect.w - pad_l - arrow_reserve)

        shown_fit, shown_trunc = _ellipsize_info(self.font, str(shown), max_w)
        val_txt = self.font.render(shown_fit, True, self.theme.text_bright)
        surface.blit(val_txt, (vrect.x + pad_l, vrect.y + (vrect.h - val_txt.get_height()) // 2))

        pygame.draw.polygon(
            surface,
            self.theme.text_bright,
            [
                (vrect.right - _s(14, 12), vrect.y + _s(9, 7)),
                (vrect.right - _s(6, 5), vrect.y + _s(9, 7)),
                (vrect.right - _s(10, 8), vrect.y + _s(15, 12)),
            ],
        )

        # Tooltip selection priority: truncated value if hovered, else truncated label if hovered.
        self._tooltip_text = None
        self._tooltip_rect = None

        mx, my = pygame.mouse.get_pos()
        if shown_trunc and vrect.collidepoint(mx, my):
            self._tooltip_text = str(shown)
            self._tooltip_rect = vrect.copy()
        elif label_trunc and label_rect.collidepoint(mx, my):
            self._tooltip_text = str(self.label)
            self._tooltip_rect = label_rect.copy()

    def draw_overlay(self, surface: pygame.Surface) -> None:
        if self.expanded:
            vrect = self._value_rect()
            items = self.get_items()
            total = len(items)
            n_vis = min(total, self.max_visible)
            self._clamp_scroll(total)

            drop = self._drop_rect(vrect, n_vis)
            pygame.draw.rect(surface, (0, 0, 0), drop)
            pygame.draw.rect(surface, self.theme.border, drop, width=1)

            track, thumb = self._scrollbar_rects(drop, total, n_vis)
            scrollbar_reserve = _s(10, 8) if track is not None else 0

            start = self.scroll
            end = min(total, start + n_vis)
            for i, idx in enumerate(range(start, end)):
                display, _payload = items[idx]
                row = pygame.Rect(drop.x + 1, drop.y + 1 + i * self.item_h, drop.w - 2, self.item_h)
                if i % 2 == 0:
                    pygame.draw.rect(surface, (18, 20, 26), row)
                text_max_w = max(0, row.w - _s(12, 10) - scrollbar_reserve)
                disp_fit = _ellipsize(self.font, display, text_max_w)
                t = self.font.render(disp_fit, True, self.theme.text_bright)
                surface.blit(t, (row.x + _s(6, 4), row.y + (row.h - t.get_height()) // 2))

            if track is not None and thumb is not None:
                pygame.draw.rect(surface, (60, 70, 90), track)
                pygame.draw.rect(surface, (140, 160, 190), thumb)

        if self._tooltip_text and self._tooltip_rect is not None:
            mx, my = pygame.mouse.get_pos()
            if self._tooltip_rect.collidepoint(mx, my):
                _draw_tooltip_at_mouse(surface, self.font, self.theme, self._tooltip_text)


class SliderWithBoxRow(Widget):
    def __init__(
        self,
        rect: pygame.Rect,
        label: str,
        min_value: int,
        max_value: int,
        value: int,
        font: pygame.font.Font,
        theme: UITheme,
        on_change: Callable[[int], None],
        snaps: Sequence[int] = (),
        snap_window: int = 5,
        allow_empty: bool = False,
        empty_value: int = 0,
        label_w: int = 150,
        box_w: int = 84,
    ) -> None:
        self.rect = rect
        self.label = label
        self.min_value = int(min_value)
        self.max_value = int(max_value)
        self.value = int(clamp(float(value), float(self.min_value), float(self.max_value)))
        self.font = font
        self.theme = theme
        self.on_change = on_change
        self.snaps = list(snaps)
        self.snap_window = int(max(1, snap_window))
        self.allow_empty = allow_empty
        self.empty_value = int(empty_value)
        self.label_w = int(label_w)
        self.box_w = int(box_w)

        self.dragging = False
        self.focused = False
        self.edit_text = str(self.value)

        self._tooltip_text: Optional[str] = None
        self._tooltip_rect: Optional[pygame.Rect] = None

    def _slider_rect(self) -> pygame.Rect:
        x = self.rect.x + self.label_w
        h = _s(18, 14)
        y = self.rect.y + (self.rect.h - h) // 2
        w = self.rect.w - self.label_w - self.box_w - _s(10, 8)
        return pygame.Rect(x, y, max(_s(10, 10), w), h)

    def _box_rect(self) -> pygame.Rect:
        x = self.rect.right - self.box_w
        h = _s(24, 18)
        y = self.rect.y + (self.rect.h - h) // 2
        return pygame.Rect(x, y, self.box_w, h)

    def _value_from_mouse(self, mx: int) -> int:
        srect = self._slider_rect()
        t = (mx - srect.x) / float(max(1, srect.w))
        t = clamp(t, 0.0, 1.0)
        raw = int(round(self.min_value + t * (self.max_value - self.min_value)))
        if self.snaps:
            raw = nearest_snap(raw, self.snaps, self.snap_window)
        return int(clamp(float(raw), float(self.min_value), float(self.max_value)))

    def _knob_x(self) -> int:
        srect = self._slider_rect()
        denom = float(self.max_value - self.min_value) if self.max_value != self.min_value else 1.0
        t = (self.value - self.min_value) / denom
        return int(round(srect.x + t * srect.w))

    def _commit_value(self, v: int) -> None:
        v = int(clamp(float(v), float(self.min_value), float(self.max_value)))
        if v != self.value:
            self.value = v
            self.edit_text = str(self.value)
            self.on_change(self.value)
        else:
            self.edit_text = str(self.value)

    def _commit_text(self) -> None:
        txt = self.edit_text.strip()
        if txt == "" and self.allow_empty:
            self._commit_value(self.empty_value)
            return
        if txt == "":
            self.edit_text = str(self.value)
            return
        try:
            v = int(txt, 10)
        except Exception:
            self.edit_text = str(self.value)
            return
        if self.snaps and not (self.allow_empty and v == self.empty_value):
            v = nearest_snap(v, self.snaps, self.snap_window)
        self._commit_value(v)

    def handle_event(self, event: pygame.event.Event) -> bool:
        srect = self._slider_rect()
        brect = self._box_rect()

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            if srect.inflate(_s(8, 6), _s(10, 8)).collidepoint(mx, my):
                self.dragging = True
                self.focused = False
                self.value = self._value_from_mouse(mx)
                self.edit_text = str(self.value)
                self.on_change(self.value)
                return True

            if brect.collidepoint(mx, my):
                self.focused = True
                self.edit_text = "" if (self.allow_empty and self.value == self.empty_value) else str(self.value)
                return True

            if self.focused:
                self._commit_text()
                self.focused = False
                return True

        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self.dragging:
                self.dragging = False
                return True

        if event.type == pygame.MOUSEMOTION:
            if self.dragging:
                mx, _my = event.pos
                self.value = self._value_from_mouse(mx)
                self.edit_text = str(self.value)
                self.on_change(self.value)
                return True

        if event.type == pygame.KEYDOWN and self.focused:
            if event.key == pygame.K_RETURN:
                self._commit_text()
                self.focused = False
                return True
            if event.key == pygame.K_ESCAPE:
                self.edit_text = str(self.value)
                self.focused = False
                return True
            if event.key == pygame.K_BACKSPACE:
                if self.edit_text:
                    self.edit_text = self.edit_text[:-1]
                return True
            ch = event.unicode
            if ch.isdigit():
                self.edit_text += ch
                return True

        return False

    def draw(self, surface: pygame.Surface) -> None:
        label_fit, was_trunc = _ellipsize_info(self.font, self.label, max(0, self.label_w - _s(6, 4)))
        label_txt = self.font.render(label_fit, True, self.theme.text)
        label_rect = pygame.Rect(self.rect.x, self.rect.y, self.label_w, self.rect.h)
        surface.blit(label_txt, (self.rect.x, self.rect.y + (self.rect.h - label_txt.get_height()) // 2))

        srect = self._slider_rect()
        brect = self._box_rect()

        pygame.draw.rect(surface, self.theme.border, srect, width=1)
        pygame.draw.line(surface, self.theme.line, (srect.x, srect.centery), (srect.right, srect.centery), width=_s(2, 1))

        for s in self.snaps:
            if s < self.min_value or s > self.max_value:
                continue
            denom = float(self.max_value - self.min_value) if self.max_value != self.min_value else 1.0
            t = (s - self.min_value) / denom
            x = int(round(srect.x + t * srect.w))
            pygame.draw.line(surface, (80, 90, 110), (x, srect.y + _s(2, 2)), (x, srect.bottom - _s(2, 2)), width=1)

        kx = self._knob_x()
        knob_w = _s(10, 8)
        knob_h = srect.h + _s(10, 8)
        knob = pygame.Rect(0, 0, knob_w, knob_h)
        knob.center = (kx, srect.centery)
        pygame.draw.rect(surface, self.theme.text_bright, knob, border_radius=_s(2, 2))

        pygame.draw.rect(surface, self.theme.border, brect, width=1)

        text_to_show = self.edit_text if self.focused else str(self.value)
        if self.allow_empty and self.value == self.empty_value and not self.focused:
            text_to_show = "0"
        txt = self.font.render(text_to_show, True, self.theme.text_bright)
        surface.blit(txt, (brect.x + _s(6, 4), brect.y + (brect.h - txt.get_height()) // 2))

        if was_trunc:
            self._tooltip_text = str(self.label)
            self._tooltip_rect = label_rect.copy()
        else:
            self._tooltip_text = None
            self._tooltip_rect = None

    def draw_overlay(self, surface: pygame.Surface) -> None:
        if not self._tooltip_text or self._tooltip_rect is None:
            return
        mx, my = pygame.mouse.get_pos()
        if self._tooltip_rect.collidepoint(mx, my):
            _draw_tooltip_at_mouse(surface, self.font, self.theme, self._tooltip_text)


class MiniPanel(Widget):
    def __init__(
        self,
        font: pygame.font.Font,
        theme: UITheme,
        get_ui_visible: Callable[[], bool],
        toggle_ui: Callable[[], None],
        get_mouse_mode: Callable[[], bool],
        toggle_mouse_mode: Callable[[], None],
        get_rates_line: Callable[[], str],
    ) -> None:
        self.font = font
        self.theme = theme
        self.get_ui_visible = get_ui_visible
        self.toggle_ui = toggle_ui
        self.get_mouse_mode = get_mouse_mode
        self.toggle_mouse_mode = toggle_mouse_mode
        self.get_rates_line = get_rates_line

        self.rect = pygame.Rect(12, 12, 310, 44)
        self._win_w = 0
        self._win_h = 0

        self._tooltip_text: Optional[str] = None
        self._tooltip_rect: Optional[pygame.Rect] = None

    def layout(self, win_w: int, win_h: int) -> None:
        self._win_w = int(win_w)
        self._win_h = int(win_h)

        ui_label = "UI (Shift)"
        mm_label = "Mouse (Ctrl)"
        ui_w, ui_h = self.font.size(ui_label)
        mm_w, mm_h = self.font.size(mm_label)

        box_sz = _s(18, 12)
        pad_l = _s(12, 10)
        pad_r = _s(12, 10)
        gap_x = _s(22, 14)

        row_w = pad_l + box_sz + _s(8, 6) + ui_w + gap_x + box_sz + _s(8, 6) + mm_w + pad_r

        line = self.get_rates_line()
        line_w = self.font.size(line)[0]
        line_need_w = pad_l + line_w + pad_r

        w = max(row_w, line_need_w)

        max_w = max(_s(220, 180), win_w - 2 * int(config.CANVAS_MARGIN))
        w = int(clamp(float(w), float(_s(220, 180)), float(max_w)))

        pad_top = _s(10, 8)
        pad_bottom = _s(10, 8)
        row_h = max(box_sz, ui_h, mm_h)
        gap_y = _s(8, 6)
        line_h = int(self.font.get_linesize())
        h = int(pad_top + row_h + gap_y + line_h + pad_bottom)

        border_gap = _s(6, 4)
        x = int(config.CANVAS_MARGIN)
        y = int(win_h - int(config.CANVAS_MARGIN) - border_gap - h)
        if y < int(config.CANVAS_MARGIN):
            y = int(config.CANVAS_MARGIN)

        self.rect = pygame.Rect(x, y, w, h)

    def _ui_box_rect(self) -> pygame.Rect:
        box_sz = _s(18, 12)
        return pygame.Rect(self.rect.x + _s(10, 8), self.rect.y + _s(10, 8), box_sz, box_sz)

    def _mouse_box_rect(self) -> pygame.Rect:
        ui_label = "UI (Shift)"
        ui_w, _ui_h = self.font.size(ui_label)
        box_sz = _s(18, 12)
        x = self.rect.x + _s(10, 8) + box_sz + _s(8, 6) + ui_w + _s(22, 14)
        return pygame.Rect(x, self.rect.y + _s(10, 8), box_sz, box_sz)

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            ui_box = self._ui_box_rect().inflate(_s(6, 4), _s(6, 4))
            if ui_box.collidepoint(mx, my):
                self.toggle_ui()
                return True
            mm_box = self._mouse_box_rect().inflate(_s(6, 4), _s(6, 4))
            if mm_box.collidepoint(mx, my):
                self.toggle_mouse_mode()
                return True
        return False

    def draw(self, surface: pygame.Surface) -> None:
        # Intentionally no background/border.
        ui_checked = self.get_ui_visible()
        ui_box = self._ui_box_rect()
        pygame.draw.rect(surface, self.theme.border, ui_box, width=1)
        if ui_checked:
            pygame.draw.rect(surface, self.theme.text_bright, ui_box.inflate(-_s(6, 4), -_s(6, 4)), border_radius=_s(2, 2))
        t = self.font.render("UI (Shift)", True, self.theme.text_bright)
        surface.blit(t, (ui_box.right + _s(8, 6), ui_box.y + (ui_box.h - t.get_height()) // 2))

        mm_checked = self.get_mouse_mode()
        mm_box = self._mouse_box_rect()
        pygame.draw.rect(surface, self.theme.border, mm_box, width=1)
        if mm_checked:
            pygame.draw.rect(surface, self.theme.text_bright, mm_box.inflate(-_s(6, 4), -_s(6, 4)), border_radius=_s(2, 2))
        t2 = self.font.render("Mouse (Ctrl)", True, self.theme.text_bright)
        surface.blit(t2, (mm_box.right + _s(8, 6), mm_box.y + (mm_box.h - t2.get_height()) // 2))

        line = self.get_rates_line()
        status_x = self.rect.x + _s(10, 8)
        status_y = ui_box.bottom + _s(8, 6)
        max_w = max(0, self.rect.w - _s(20, 16))

        line_fit, was_trunc = _ellipsize_info(self.font, line, max_w)
        t3 = self.font.render(line_fit, True, self.theme.muted)
        surface.blit(t3, (status_x, status_y))

        if was_trunc:
            self._tooltip_text = line
            self._tooltip_rect = pygame.Rect(status_x, status_y, max_w, t3.get_height())
        else:
            self._tooltip_text = None
            self._tooltip_rect = None

    def draw_overlay(self, surface: pygame.Surface) -> None:
        if not self._tooltip_text or self._tooltip_rect is None:
            return
        mx, my = pygame.mouse.get_pos()
        if self._tooltip_rect.collidepoint(mx, my):
            _draw_tooltip_at_mouse(surface, self.font, self.theme, self._tooltip_text)
