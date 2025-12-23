# main.py
from __future__ import annotations

import time
from typing import List, Optional, Tuple

import pygame

import config
import help
import updater
import video
from input_devices import ControllerManager
from render import RateMeter, draw_canvas_border, draw_glowing_ball, draw_reticle, draw_target
from simulation import clamp_state_to_bounds, engine_step, make_initial_state, set_target_enabled
from ui import CheckboxRow, DropdownRow, MiniPanel, SliderWithBoxRow, UITheme
from util import clamp


def _ui_scale() -> float:
    try:
        return float(getattr(config, "UI_SCALE", 1.0))
    except Exception:
        return 1.0


def main() -> None:
    pygame.init()
    pygame.display.set_caption(config.TITLE)

    fullscreen = False
    resolution: Tuple[int, int] = (config.WINDOW_W, config.WINDOW_H)

    screen = video.apply_display_mode(resolution, fullscreen)

    clock = pygame.time.Clock()
    win_w, win_h = screen.get_size()
    resolution = (win_w, win_h)

    base_font_px = 22
    font_px = max(12, int(round(float(base_font_px) * _ui_scale())))
    font = pygame.font.Font(None, font_px)

    theme = UITheme(
        text=config.HUD_TEXT,
        text_bright=config.HUD_TEXT_BRIGHT,
        muted=config.HUD_MUTED,
        border=config.HUD_BORDER,
        panel_bg=config.HUD_BG,
        line=(120, 140, 170),
    )

    update_mgr = updater.UpdateManager(
        app_id="reXact-fps",
        current_version=config.VERSION,
        descriptor_url=config.UPDATE_DESCRIPTOR_URL,
        project_url=config.PROJECT_URL,
        releases_url=config.RELEASES_URL,
        os_tag=updater.detect_os_tag(),
        http_timeout_s=config.UPDATE_HTTP_TIMEOUT_S,
        check_delay_s=config.UPDATE_CHECK_DELAY_S,
        theme=updater.UpdateUITheme(
            text=theme.text,
            text_bright=theme.text_bright,
            muted=theme.muted,
            border=theme.border,
            panel_bg=theme.panel_bg,
        ),
    )

    help_mgr = help.HelpManager(
        project_url=config.PROJECT_URL,
        theme=help.HelpUITheme(
            text=theme.text,
            text_bright=theme.text_bright,
            muted=theme.muted,
            border=theme.border,
            panel_bg=theme.panel_bg,
        ),
    )

    ctrl = ControllerManager()
    ctrl.auto_select_first()

    # Startup controller notice (drawn on-canvas and fades out after 3 seconds).
    startup_notice_s = 3.0
    startup_notice_start = time.perf_counter()
    startup_notice_font = pygame.font.Font(None, max(14, int(round(float(font_px) * 1.8))))

    _active_idx = ctrl.active_index()
    if _active_idx is None:
        startup_notice_text = "No controller detected. Press Ctrl to enable mouse mode."
    else:
        _name: Optional[str] = None
        for _idx, _nm in ctrl.list_devices():
            if _idx == _active_idx:
                _name = _nm
                break
        startup_notice_text = f"Controller: {_name or 'Controller'}"

    engine_fps = config.DEFAULT_ENGINE_FPS
    visual_fps = config.DEFAULT_VISUAL_FPS
    interp_enabled = True

    deadzone_relax = config.DEFAULT_DEADZONE_RELAXATION

    target_enabled = False
    target_size_pct = config.TARGET_SIZE_PCT_DEFAULT
    target_speed = config.TARGET_SPEED_PX_S_DEFAULT

    mouse_mode = False
    ui_visible = True

    prev_mouse_buttons = [False, False, False]
    last_input_axis = ""
    last_input_button = ""

    def current_deadzone() -> float:
        return config.RELAXED_DEADZONE if deadzone_relax else config.UNRELAXED_DEADZONE

    state = make_initial_state(win_w, win_h, config.CANVAS_MARGIN)
    state.target.set_params(state.ball_radius, target_size_pct, target_speed)

    # Controller “real-time cursor” (render-time integration) for visual-lag indication.
    controller_cursor = state.pos.copy()

    engine_meter = RateMeter()
    visual_meter = RateMeter()

    widgets: List[object] = []
    hud_rect = pygame.Rect(0, 0, 0, 0)
    mini_panel: Optional[MiniPanel] = None

    def any_text_focused() -> bool:
        for w in widgets:
            if getattr(w, "focused", False):
                return True
        return False

    def apply_video_mode() -> None:
        nonlocal screen, win_w, win_h, resolution, controller_cursor
        screen = video.apply_display_mode(resolution, fullscreen)
        win_w, win_h = screen.get_size()
        resolution = (win_w, win_h)
        clamp_state_to_bounds(state, win_w, win_h, config.CANVAS_MARGIN)
        controller_cursor.x = state.pos.x
        controller_cursor.y = state.pos.y
        build_ui(win_w, win_h)

    def set_resolution(payload: Optional[object]) -> None:
        nonlocal resolution
        if payload is None:
            return
        try:
            w, h = payload  # type: ignore[misc]
            resolution = (int(w), int(h))
            apply_video_mode()
        except Exception:
            return

    def set_fullscreen(v: bool) -> None:
        nonlocal fullscreen
        fullscreen = bool(v)
        apply_video_mode()

    def set_engine_fps(v: int) -> None:
        nonlocal engine_fps
        engine_fps = int(clamp(float(v), 1.0, 2000.0))

    def set_visual_fps(v: int) -> None:
        nonlocal visual_fps
        visual_fps = int(clamp(float(v), 0.0, 2000.0))

    def set_interp(v: bool) -> None:
        nonlocal interp_enabled
        interp_enabled = bool(v)

    def set_deadzone_relax(v: bool) -> None:
        nonlocal deadzone_relax
        deadzone_relax = bool(v)

    def set_target(v: bool) -> None:
        nonlocal target_enabled
        target_enabled = bool(v)
        set_target_enabled(state, target_enabled, win_w, win_h, config.CANVAS_MARGIN)

    def set_target_size(v: int) -> None:
        nonlocal target_size_pct
        target_size_pct = int(clamp(float(v), float(config.TARGET_SIZE_PCT_MIN), float(config.TARGET_SIZE_PCT_MAX)))
        state.target.set_params(state.ball_radius, target_size_pct, target_speed)
        if state.target.enabled:
            clamp_state_to_bounds(state, win_w, win_h, config.CANVAS_MARGIN)

    def set_target_speed(v: int) -> None:
        nonlocal target_speed
        target_speed = int(clamp(float(v), float(config.TARGET_SPEED_PX_S_MIN), float(config.TARGET_SPEED_PX_S_MAX)))
        state.target.set_params(state.ball_radius, target_size_pct, target_speed)

    def set_mouse_mode(v: bool) -> None:
        nonlocal mouse_mode, prev_mouse_buttons, controller_cursor
        mouse_mode = bool(v)
        prev_mouse_buttons = [False, False, False]
        pygame.mouse.set_visible(not mouse_mode)
        if not mouse_mode:
            controller_cursor.x = state.pos.x
            controller_cursor.y = state.pos.y

    def toggle_mouse_mode() -> None:
        set_mouse_mode(not mouse_mode)

    def toggle_ui_visible() -> None:
        nonlocal ui_visible
        ui_visible = not ui_visible

    def ui_rates_line() -> str:
        mode = "mouse" if mouse_mode else "controller"
        fs = "fullscreen" if fullscreen else "window"
        return (
            f"E {engine_meter.value:5.1f} Hz   V {visual_meter.value:5.1f} FPS   "
            f"Mode: {mode}   {resolution[0]}×{resolution[1]} {fs}   v{config.VERSION}"
        )

    def build_ui(w: int, h: int) -> None:
        nonlocal widgets, hud_rect, mini_panel

        sc = _ui_scale()

        def s(x: float, min_v: int = 1) -> int:
            return max(int(min_v), int(round(float(x) * sc)))

        # Smaller default HUD width; keep it usable.
        hud_w = min(s(620, 260), max(s(320, 220), w - s(24, 18)))
        row_w = max(s(240, 200), hud_w - s(20, 16) - s(20, 16))

        pad_outer = s(10, 8)
        pad_inner = s(10, 8)
        gap = s(6, 4)

        x0 = s(12, 10) + pad_inner
        y0 = s(12, 10) + pad_inner

        rows: List[Tuple[str, int]] = [
            ("video_res", s(30, 24)),
            ("video_fs", s(26, 22)),
            ("controller", s(30, 24)),
            ("cb_deadzone", s(26, 22)),
            ("cb_target", s(26, 22)),
            ("engine", s(34, 26)),
            ("visual", s(34, 26)),
            ("cb_interp", s(26, 22)),
            ("t_size", s(34, 26)),
            ("t_speed", s(34, 26)),
        ]
        n = len(rows)
        hud_h = pad_outer + sum(rh for _k, rh in rows) + (n - 1) * gap + pad_outer
        hud_rect = pygame.Rect(s(12, 10), s(12, 10), hud_w, hud_h)

        def row_rect(height: int, y: int) -> pygame.Rect:
            return pygame.Rect(x0, y, row_w, height)

        def res_items() -> List[Tuple[str, object]]:
            return video.build_resolution_items(fullscreen)

        def res_selected() -> Optional[object]:
            return (int(resolution[0]), int(resolution[1]))

        def res_select(payload: Optional[object]) -> None:
            set_resolution(payload)

        def devices_items() -> List[Tuple[str, object]]:
            devs = ctrl.list_devices()
            items: List[Tuple[str, object]] = []
            items.append(("None", None))
            for idx, name in devs:
                items.append((f"{idx}: {name}", idx))
            return items

        def get_selected_payload() -> Optional[object]:
            return ctrl.active_index()

        def on_select_payload(payload: Optional[object]) -> None:
            if payload is None:
                ctrl.select_device(None)
            else:
                ctrl.select_device(int(payload))

        label_w = s(150, 120)
        box_w = s(84, 68)

        y = y0
        built: List[object] = []

        built.append(
            DropdownRow(
                rect=row_rect(s(30, 24), y),
                label="Resolution",
                font=font,
                theme=theme,
                get_items=res_items,
                get_selected_payload=res_selected,
                on_select_payload=res_select,
                label_w=label_w,
            )
        )
        y += s(30, 24) + gap

        built.append(
            CheckboxRow(
                rect=row_rect(s(26, 22), y),
                label="Fullscreen",
                checked=fullscreen,
                font=font,
                theme=theme,
                on_change=set_fullscreen,
            )
        )
        y += s(26, 22) + gap

        built.append(
            DropdownRow(
                rect=row_rect(s(30, 24), y),
                label="Controller",
                font=font,
                theme=theme,
                get_items=devices_items,
                get_selected_payload=get_selected_payload,
                on_select_payload=on_select_payload,
                label_w=label_w,
            )
        )
        y += s(30, 24) + gap

        built.append(
            CheckboxRow(
                rect=row_rect(s(26, 22), y),
                label="Deadzone relaxation",
                checked=deadzone_relax,
                font=font,
                theme=theme,
                on_change=set_deadzone_relax,
            )
        )
        y += s(26, 22) + gap

        built.append(
            CheckboxRow(
                rect=row_rect(s(26, 22), y),
                label="Enable target",
                checked=target_enabled,
                font=font,
                theme=theme,
                on_change=set_target,
            )
        )
        y += s(26, 22) + gap

        built.append(
            SliderWithBoxRow(
                rect=row_rect(s(34, 26), y),
                label="Engine FPS",
                min_value=config.ENGINE_FPS_MIN,
                max_value=config.ENGINE_FPS_MAX,
                value=engine_fps,
                font=font,
                theme=theme,
                on_change=set_engine_fps,
                snaps=config.SNAP_POINTS,
                snap_window=5,
                label_w=label_w,
                box_w=box_w,
            )
        )
        y += s(34, 26) + gap

        built.append(
            SliderWithBoxRow(
                rect=row_rect(s(34, 26), y),
                label="Visual FPS (0 = uncapped)",
                min_value=config.VISUAL_FPS_MIN,
                max_value=config.VISUAL_FPS_MAX,
                value=visual_fps,
                font=font,
                theme=theme,
                on_change=set_visual_fps,
                snaps=[0] + config.SNAP_POINTS,
                snap_window=5,
                allow_empty=True,
                empty_value=0,
                label_w=label_w,
                box_w=box_w,
            )
        )
        y += s(34, 26) + gap

        built.append(
            CheckboxRow(
                rect=row_rect(s(26, 22), y),
                label="Interpolation (I)",
                checked=interp_enabled,
                font=font,
                theme=theme,
                on_change=set_interp,
            )
        )
        y += s(26, 22) + gap

        built.append(
            SliderWithBoxRow(
                rect=row_rect(s(34, 26), y),
                label="Target size (%)",
                min_value=config.TARGET_SIZE_PCT_MIN,
                max_value=config.TARGET_SIZE_PCT_MAX,
                value=target_size_pct,
                font=font,
                theme=theme,
                on_change=set_target_size,
                snaps=[140, 165, 200, 240, 300, 400, 500],
                snap_window=6,
                label_w=label_w,
                box_w=box_w,
            )
        )
        y += s(34, 26) + gap

        built.append(
            SliderWithBoxRow(
                rect=row_rect(s(34, 26), y),
                label="Target speed (px/s)",
                min_value=config.TARGET_SPEED_PX_S_MIN,
                max_value=config.TARGET_SPEED_PX_S_MAX,
                value=target_speed,
                font=font,
                theme=theme,
                on_change=set_target_speed,
                snaps=[120, 170, 220, 280, 340],
                snap_window=6,
                label_w=label_w,
                box_w=box_w,
            )
        )

        widgets = built

        mini_panel = MiniPanel(
            font=font,
            theme=theme,
            get_ui_visible=lambda: ui_visible,
            toggle_ui=toggle_ui_visible,
            get_mouse_mode=lambda: mouse_mode,
            toggle_mouse_mode=toggle_mouse_mode,
            get_rates_line=ui_rates_line,
        )
        mini_panel.layout(w, h)

    build_ui(win_w, win_h)
    set_mouse_mode(False)

    running = True
    last_time = time.perf_counter()
    accumulator = 0.0
    last_render = 0.0

    while running:
        now = time.perf_counter()
        frame_dt = now - last_time
        last_time = now
        frame_dt = min(frame_dt, 0.25)
        accumulator += frame_dt

        # Render-time controller cursor integration (shows “input ahead of sim” when engine is slow).
        if not mouse_mode:
            lx, ly = ctrl.peek_axes(deadzone=current_deadzone())

            # If the stick is effectively stopped, hard-snap the reticle to the simulated ball position.
            # This prevents “stopped but offset” drift from persisting forever.
            if lx == 0.0 and ly == 0.0:
                controller_cursor.x = state.pos.x
                controller_cursor.y = state.pos.y
            else:
                controller_cursor.x += (lx * state.ball_speed) * frame_dt
                controller_cursor.y += (ly * state.ball_speed) * frame_dt

                br = state.ball_radius
                controller_cursor.x = clamp(
                    controller_cursor.x,
                    float(config.CANVAS_MARGIN + br),
                    float(win_w - config.CANVAS_MARGIN - br),
                )
                controller_cursor.y = clamp(
                    controller_cursor.y,
                    float(config.CANVAS_MARGIN + br),
                    float(win_h - config.CANVAS_MARGIN - br),
                )

        update_mgr.pump(font)
        update_mgr.layout(font, win_w, win_h)
        help_mgr.layout(font, win_w, win_h)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                continue

            if update_mgr.handle_event(event, font):
                continue
            if update_mgr.dialog_active():
                continue  # modal dialog: swallow everything else

            if help_mgr.handle_event(event, font):
                # If the click opened the dialog, relayout immediately to avoid a one-frame wrong size.
                help_mgr.layout(font, win_w, win_h)
                continue
            if help_mgr.dialog_active():
                continue  # modal dialog: swallow everything else

            if event.type == pygame.VIDEORESIZE and not fullscreen:
                resolution = (int(event.w), int(event.h))
                screen = video.apply_display_mode(resolution, fullscreen=False)
                win_w, win_h = screen.get_size()
                resolution = (win_w, win_h)
                clamp_state_to_bounds(state, win_w, win_h, config.CANVAS_MARGIN)
                controller_cursor.x = state.pos.x
                controller_cursor.y = state.pos.y
                build_ui(win_w, win_h)
                continue

            if event.type == pygame.KEYDOWN and not any_text_focused():
                if event.key == pygame.K_ESCAPE:
                    running = False
                    continue
                if event.key == pygame.K_i:
                    interp_enabled = not interp_enabled
                    # Keep the checkbox in sync.
                    for wdg in widgets:
                        if getattr(wdg, "label", "") == "Interpolation (I)" and hasattr(wdg, "checked"):
                            try:
                                wdg.checked = bool(interp_enabled)  # type: ignore[attr-defined]
                            except Exception:
                                pass
                if event.key in (pygame.K_LSHIFT, pygame.K_RSHIFT):
                    toggle_ui_visible()
                if event.key in (pygame.K_LCTRL, pygame.K_RCTRL):
                    toggle_mouse_mode()

            if event.type == pygame.JOYDEVICEADDED:
                try:
                    ctrl.handle_device_added(event.device_index)
                except Exception:
                    pass
            elif event.type == pygame.JOYDEVICEREMOVED:
                try:
                    ctrl.handle_device_removed(event.instance_id)
                except Exception:
                    pass

            if mini_panel is not None:
                if mini_panel.handle_event(event):
                    continue

            if ui_visible:
                for wdg in widgets:
                    if wdg.handle_event(event):
                        break

        if update_mgr.should_quit():
            running = False

        engine_dt = 1.0 / float(max(1, engine_fps))

        while accumulator >= engine_dt:
            if mouse_mode:
                pygame.event.pump()
                mx, my = pygame.mouse.get_pos()

                pressed = pygame.mouse.get_pressed(3)
                mapping = {0: 0, 2: 1, 1: 2}

                edges: List[int] = []
                for idx in range(3):
                    cur = bool(pressed[idx])
                    prev = prev_mouse_buttons[idx]
                    if cur and not prev:
                        b = int(mapping.get(idx, 0))
                        edges.append(b)
                        last_input_button = config.get_button_label(b)
                    prev_mouse_buttons[idx] = cur

                any_edge = bool(edges)
                last_input_axis = f"mouse=({mx},{my})"

                engine_step(
                    state=state,
                    dt=engine_dt,
                    w=win_w,
                    h=win_h,
                    margin=config.CANVAS_MARGIN,
                    stick_lx=0.0,
                    stick_ly=0.0,
                    button_down_edges=tuple(edges),
                    any_button_edge=any_edge,
                    ball_override_pos=(float(mx), float(my)),
                )
            else:
                sample = ctrl.sample(deadzone=current_deadzone())
                last_input_axis = ctrl.last_axis_debug
                last_input_button = ctrl.last_button_debug

                engine_step(
                    state=state,
                    dt=engine_dt,
                    w=win_w,
                    h=win_h,
                    margin=config.CANVAS_MARGIN,
                    stick_lx=sample.lx,
                    stick_ly=sample.ly,
                    button_down_edges=sample.button_down_edges,
                    any_button_edge=sample.any_button_edge,
                    ball_override_pos=None,
                )

            accumulator -= engine_dt
            engine_meter.tick()

        do_render = False
        if visual_fps <= 0:
            do_render = True
        else:
            visual_dt = 1.0 / float(max(1, visual_fps))
            if (now - last_render) >= visual_dt:
                do_render = True

        if do_render:
            last_render = now
            screen.fill(config.BG_COLOR)

            draw_canvas_border(screen, win_w, win_h, config.CANVAS_MARGIN)

            if interp_enabled and engine_dt > 0.0:
                alpha = clamp(accumulator / engine_dt, 0.0, 1.0)
                render_pos = state.prev_pos.lerp(state.pos, alpha)
            else:
                render_pos = state.pos

            if state.target.enabled:
                draw_target(screen, state.target.pos, state.target.radius_px, flash_elapsed=state.target.hit_flash_elapsed)

            draw_glowing_ball(
                screen,
                render_pos,
                state.ball_radius,
                base_color=config.BALL_BASE_COLOR,
                blink_color=state.visual.active_blink_color,
                glow_elapsed=state.visual.glow_elapsed,
            )

            if mouse_mode:
                mx, my = pygame.mouse.get_pos()
                draw_reticle(screen, int(mx), int(my))
            else:
                draw_reticle(screen, int(controller_cursor.x), int(controller_cursor.y))

            if ui_visible:
                hud_surf = pygame.Surface((hud_rect.w, hud_rect.h), flags=pygame.SRCALPHA)
                hud_surf.fill(theme.panel_bg)
                screen.blit(hud_surf, (hud_rect.x, hud_rect.y))
                pygame.draw.rect(screen, theme.border, hud_rect, width=1)

                for wdg in widgets:
                    wdg.draw(screen)

                # Smaller debug block (the controls already encode most state).
                stats_x = hud_rect.x + int(round(10 * _ui_scale()))
                stats_y = hud_rect.bottom + int(round(8 * _ui_scale()))
                stats_lines = [
                    f"Active controller: {ctrl.active_label()}",
                    f"Measured: E {engine_meter.value:6.1f} Hz   V {visual_meter.value:6.1f} FPS",
                    f"Input axis: {last_input_axis}",
                    f"Input button: {last_input_button}",
                ]
                line_step = max(12, int(round(18 * _ui_scale())))
                for line in stats_lines:
                    txt = font.render(line, True, theme.muted)
                    screen.blit(txt, (stats_x, stats_y))
                    stats_y += line_step

            if mini_panel is not None:
                mini_panel.layout(win_w, win_h)
                mini_panel.draw(screen)

            update_mgr.draw_corner_ui(screen, font)
            help_mgr.draw_corner_ui(screen, font)

            if ui_visible:
                for wdg in widgets:
                    if hasattr(wdg, "draw_overlay"):
                        wdg.draw_overlay(screen)  # type: ignore[attr-defined]

            # Startup notice (on the canvas, fades out).
            _elapsed = now - startup_notice_start
            if _elapsed < startup_notice_s:
                _t = clamp(_elapsed / startup_notice_s, 0.0, 1.0)
                _a = int(round(255.0 * (1.0 - _t)))
                if _a > 0:
                    _txt = startup_notice_font.render(startup_notice_text, True, theme.text_bright)
                    _txt.set_alpha(_a)

                    _m = int(config.CANVAS_MARGIN)
                    _cw = max(1, win_w - 2 * _m)
                    _ch = max(1, win_h - 2 * _m)
                    _cx = _m + (_cw // 2)
                    _cy = _m + int(_ch * 0.14)

                    screen.blit(_txt, (_cx - (_txt.get_width() // 2), _cy - (_txt.get_height() // 2)))

            update_mgr.draw_dialog_overlay(screen)
            help_mgr.draw_dialog_overlay(screen)

            pygame.display.flip()
            visual_meter.tick()

        next_engine_in = max(0.0, engine_dt - accumulator)
        if visual_fps <= 0:
            next_render_in = 0.0
        else:
            visual_dt = 1.0 / float(max(1, visual_fps))
            next_render_in = max(0.0, (last_render + visual_dt) - time.perf_counter())

        sleep_for = None
        if next_engine_in > 0.0 and next_render_in > 0.0:
            sleep_for = min(next_engine_in, next_render_in)
        elif next_engine_in > 0.0:
            sleep_for = next_engine_in
        elif next_render_in > 0.0:
            sleep_for = next_render_in

        if sleep_for is not None and sleep_for > 0.002:
            time.sleep(sleep_for * 0.75)

        clock.tick(1000)

    pygame.quit()


if __name__ == "__main__":
    main()
