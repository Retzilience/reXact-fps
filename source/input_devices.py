# input_devices.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import pygame

import config
from util import apply_deadzone


@dataclass
class ControllerSample:
    lx: float = 0.0
    ly: float = 0.0
    button_down_edges: Tuple[int, ...] = ()
    any_button_edge: bool = False


class ControllerManager:
    """
    Controller selection and polling via pygame.joystick.

    - sample() updates button edge state (engine should call this).
    - peek_axes() reads axes only and does NOT touch button edge state (render may call this).
    """

    def __init__(self) -> None:
        pygame.joystick.init()
        self._active: Optional[pygame.joystick.Joystick] = None
        self._active_device_index: Optional[int] = None
        self._active_instance_id: Optional[int] = None

        self.axis_lx = 0
        self.axis_ly = 1

        self._prev_buttons: List[bool] = []

        self.last_axis_debug: str = ""
        self.last_button_debug: str = ""

    def list_devices(self) -> List[Tuple[int, str]]:
        n = pygame.joystick.get_count()
        out: List[Tuple[int, str]] = []
        for i in range(n):
            try:
                j = pygame.joystick.Joystick(i)
                name = j.get_name() or f"Controller {i}"
                out.append((i, name))
            except Exception:
                out.append((i, f"Controller {i} (unreadable)"))
        return out

    def active_index(self) -> Optional[int]:
        return self._active_device_index

    def active_label(self) -> str:
        if self._active is None:
            return "No controller"
        name = self._active.get_name() or "Controller"
        idx = self._active_device_index if self._active_device_index is not None else -1
        return f"{name} (idx {idx})"

    def select_device(self, device_index: Optional[int]) -> None:
        if device_index is None:
            self._detach()
            return

        if self._active_device_index == device_index and self._active is not None:
            return

        self._detach()
        try:
            j = pygame.joystick.Joystick(device_index)
            j.init()
            self._active = j
            self._active_device_index = device_index
            self._active_instance_id = j.get_instance_id()
            self._prev_buttons = [False] * j.get_numbuttons()
        except Exception:
            self._active = None
            self._active_device_index = None
            self._active_instance_id = None
            self._prev_buttons = []

    def auto_select_first(self) -> None:
        if pygame.joystick.get_count() > 0:
            self.select_device(0)
        else:
            self.select_device(None)

    def handle_device_added(self, device_index: int) -> None:
        if self._active is None:
            self.select_device(device_index)

    def handle_device_removed(self, instance_id: int) -> None:
        if self._active_instance_id == instance_id:
            self.select_device(None)

    def _detach(self) -> None:
        if self._active is not None:
            try:
                self._active.quit()
            except Exception:
                pass
        self._active = None
        self._active_device_index = None
        self._active_instance_id = None
        self._prev_buttons = []

    def _read_axes(self, deadzone: float) -> Tuple[float, float]:
        if self._active is None:
            self.last_axis_debug = ""
            return (0.0, 0.0)

        pygame.event.pump()

        na = self._active.get_numaxes()
        lx = 0.0
        ly = 0.0
        if na > max(self.axis_lx, self.axis_ly):
            lx = float(self._active.get_axis(self.axis_lx))
            ly = float(self._active.get_axis(self.axis_ly))
            lx = apply_deadzone(lx, deadzone)
            ly = apply_deadzone(ly, deadzone)

        self.last_axis_debug = f"lx={lx:+.3f} ly={ly:+.3f}"
        return (lx, ly)

    def peek_axes(self, deadzone: float) -> Tuple[float, float]:
        """
        Axes-only polling for rendering. Does NOT update button edge state.
        """
        return self._read_axes(deadzone)

    def sample(self, deadzone: float) -> ControllerSample:
        s = ControllerSample()

        if self._active is None:
            self.last_axis_debug = ""
            self.last_button_debug = ""
            return s

        lx, ly = self._read_axes(deadzone)
        s.lx, s.ly = lx, ly

        nb = self._active.get_numbuttons()
        if len(self._prev_buttons) != nb:
            self._prev_buttons = [False] * nb

        edges: List[int] = []
        for i in range(nb):
            cur = bool(self._active.get_button(i))
            prev = self._prev_buttons[i]
            if cur and not prev:
                edges.append(i)
                self.last_button_debug = config.get_button_label(i)
            self._prev_buttons[i] = cur

        if edges:
            s.button_down_edges = tuple(edges)
            s.any_button_edge = True

        return s
