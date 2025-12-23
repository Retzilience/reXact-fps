# updater.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Sequence, Tuple

import json
import os
import platform
import re
import threading
import time
import urllib.parse
import urllib.request
import webbrowser

import pygame


@dataclass(frozen=True)
class UpdateEntry:
    version: str
    os_tag: str
    flags: tuple[str, ...]
    download_url: str


@dataclass(frozen=True)
class UpdateStatus:
    os_tag: str
    current_version: str
    latest: Optional[UpdateEntry]
    update_available: bool
    current_deprecated: bool


@dataclass(frozen=True)
class UpdateUITheme:
    text: tuple[int, int, int]
    text_bright: tuple[int, int, int]
    muted: tuple[int, int, int]
    border: tuple[int, int, int]
    panel_bg: tuple[int, int, int, int]


def detect_os_tag() -> str:
    sp = platform.system().lower()
    if "linux" in sp:
        return "linux"
    if "windows" in sp:
        return "windows"
    if "darwin" in sp or "mac" in sp:
        return "mac"
    return sp or "unknown"


def _version_key(v: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+", v)
    if not nums:
        return (0,)
    return tuple(int(x) for x in nums)


def _parse_flags(s: str) -> tuple[str, ...]:
    if not s.strip():
        return ()
    parts = [p.strip() for p in re.split(r"[,\s]+", s.strip()) if p.strip()]
    return tuple(parts)


def _parse_descriptor(text: str) -> list[UpdateEntry]:
    out: list[UpdateEntry] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "#" in line:
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 4:
            continue
        version = parts[0]
        os_tag = parts[1].lower()
        flags = _parse_flags(parts[2])
        url = parts[3]
        if not version or not os_tag or not url:
            continue
        out.append(UpdateEntry(version=version, os_tag=os_tag, flags=flags, download_url=url))
    return out


def _rewrite_github_raw_url(url: str) -> Optional[str]:
    """
    Best-effort rewrite from:
      https://github.com/<owner>/<repo>/raw/<ref>/path
      https://github.com/<owner>/<repo>/raw/refs/heads/<ref>/path
    to:
      https://raw.githubusercontent.com/<owner>/<repo>/<ref>/path
    """
    try:
        u = urllib.parse.urlparse(url)
        host = (u.netloc or "").lower()
        if host != "github.com":
            return None

        parts = [p for p in u.path.split("/") if p]
        # owner / repo / raw / ...
        if len(parts) < 5:
            return None
        owner, repo = parts[0], parts[1]
        if parts[2] != "raw":
            return None

        rest = parts[3:]
        if len(rest) >= 3 and rest[0] == "refs" and rest[1] == "heads":
            ref = rest[2]
            file_parts = rest[3:]
        else:
            ref = rest[0]
            file_parts = rest[1:]

        if not ref or not file_parts:
            return None

        raw_path = "/".join([owner, repo, ref] + file_parts)
        return urllib.parse.urlunparse(("https", "raw.githubusercontent.com", "/" + raw_path, "", "", ""))
    except Exception:
        return None


def _state_dir(app_id: str) -> Path:
    sysname = platform.system().lower()
    home = Path.home()

    if "linux" in sysname:
        base = Path(os.environ.get("XDG_STATE_HOME", str(home / ".local" / "state")))
        return base / app_id

    if "windows" in sysname:
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or str(home)
        return Path(base) / app_id

    if "darwin" in sysname or "mac" in sysname:
        return home / "Library" / "Application Support" / app_id

    return home / f".{app_id}"


def _load_json(path: Path) -> dict:
    try:
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_json(path: Path, obj: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(obj, indent=2, sort_keys=True), encoding="utf-8")
    except Exception:
        pass


def _downloads_dir() -> Path:
    home = Path.home()
    cand = home / "Downloads"
    if cand.exists() and cand.is_dir():
        return cand
    return home


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suf = path.suffix
    parent = path.parent
    for i in range(1, 1000):
        p = parent / f"{stem}-{i}{suf}"
        if not p.exists():
            return p
    return parent / f"{stem}-{int(time.time())}{suf}"


class _Worker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None

    def running(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def start(self, fn: Callable[[], None]) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            t = threading.Thread(target=fn, daemon=True)
            self._thread = t
            t.start()


class UpdateManager:
    def __init__(
        self,
        *,
        app_id: str,
        current_version: str,
        descriptor_url: str,
        project_url: str,
        releases_url: str,
        os_tag: Optional[str] = None,
        http_timeout_s: float = 6.0,
        check_delay_s: float = 2.0,
        theme: Optional[UpdateUITheme] = None,
    ) -> None:
        self.app_id = app_id
        self.current_version = str(current_version)
        self.descriptor_url = str(descriptor_url)
        self.project_url = str(project_url)
        self.releases_url = str(releases_url)
        self.os_tag = (os_tag or detect_os_tag()).lower()
        self.http_timeout_s = float(http_timeout_s)
        self.check_delay_s = float(check_delay_s)

        self.theme = theme or UpdateUITheme(
            text=(210, 210, 210),
            text_bright=(235, 235, 235),
            muted=(170, 180, 195),
            border=(90, 100, 120),
            panel_bg=(0, 0, 0, 150),
        )

        self._state_path = _state_dir(self.app_id) / "updater.json"
        st = _load_json(self._state_path)
        self._snooze_until_version = str(st.get("snooze_until_version", "")).strip()

        self._check_worker = _Worker()
        self._download_worker = _Worker()

        self._result_lock = threading.Lock()
        self._pending_status: Optional[UpdateStatus] = None
        self._pending_notice: Optional[Tuple[str, bool]] = None
        self._pending_interactive: bool = False
        self._pending_force: bool = False

        self._download_lock = threading.Lock()
        self._download_path: Optional[str] = None
        self._download_error: Optional[str] = None
        self._download_done: bool = False

        self._dialog: Optional[_UpdateDialog] = None

        self._btn_updates = pygame.Rect(0, 0, 0, 0)
        self._corner_pad = 12

        self._toast_text: Optional[str] = None
        self._toast_error: bool = False
        self._toast_until: float = 0.0
        self._toast_sticky: bool = False

        # Fire-and-forget background check with delay (silent on failure).
        self.check_async(delay_s=self.check_delay_s, interactive=False, force=False)

    def dialog_active(self) -> bool:
        return self._dialog is not None and self._dialog.visible

    def should_quit(self) -> bool:
        return self._dialog is not None and self._dialog.request_quit

    def _now(self) -> float:
        return time.monotonic()

    def _show_toast(self, text: str, *, is_error: bool = False, seconds: float = 2.5, sticky: bool = False) -> None:
        self._toast_text = str(text)
        self._toast_error = bool(is_error)
        self._toast_sticky = bool(sticky)
        self._toast_until = 0.0 if sticky else (self._now() + float(max(0.25, seconds)))

    def _clear_toast_if_expired(self) -> None:
        if self._toast_text is None:
            return
        if self._toast_sticky:
            return
        if self._now() >= self._toast_until:
            self._toast_text = None
            self._toast_error = False
            self._toast_until = 0.0
            self._toast_sticky = False

    def check_async(self, delay_s: float = 0.0, *, interactive: bool = False, force: bool = False) -> None:
        if self._check_worker.running():
            if interactive:
                self._show_toast("Update check already running.", is_error=False, seconds=2.0, sticky=False)
            return

        if interactive:
            self._show_toast("Checking for updates…", is_error=False, sticky=True)

        def work() -> None:
            try:
                if delay_s > 0.0:
                    time.sleep(float(delay_s))
                text = self._http_get_text(self.descriptor_url, timeout=self.http_timeout_s)
                if text is None:
                    if interactive:
                        with self._result_lock:
                            self._pending_notice = ("Update check failed.", True)
                            self._pending_interactive = True
                            self._pending_force = False
                    return

                entries = _parse_descriptor(text)
                status = self._compute_status(entries)
                with self._result_lock:
                    self._pending_status = status
                    self._pending_interactive = bool(interactive)
                    self._pending_force = bool(force)
            except Exception:
                if interactive:
                    with self._result_lock:
                        self._pending_notice = ("Update check failed.", True)
                        self._pending_interactive = True
                        self._pending_force = False
                return

        self._check_worker.start(work)

    def _http_get_text(self, url: str, timeout: float) -> Optional[str]:
        def _try(u: str) -> Optional[str]:
            try:
                req = urllib.request.Request(
                    u,
                    headers={
                        "User-Agent": f"{self.app_id}/{self.current_version} (update-check)",
                        "Accept": "text/plain,*/*;q=0.9",
                    },
                )
                with urllib.request.urlopen(req, timeout=float(timeout)) as resp:
                    data = resp.read()
                return data.decode("utf-8", errors="replace")
            except Exception:
                return None

        text = _try(url)
        if text is not None:
            return text

        alt = _rewrite_github_raw_url(url)
        if alt and alt != url:
            return _try(alt)

        return None

    def _compute_status(self, entries: Sequence[UpdateEntry]) -> UpdateStatus:
        os_entries = [e for e in entries if e.os_tag.lower() == self.os_tag]
        latest = max(os_entries, key=lambda e: _version_key(e.version), default=None)

        cur_key = _version_key(self.current_version)
        latest_key = _version_key(latest.version) if latest is not None else cur_key
        update_available = latest is not None and latest_key > cur_key

        current_deprecated = False
        for e in os_entries:
            if _version_key(e.version) == cur_key and e.version.strip() == self.current_version.strip():
                if any(f.lower() == "deprecated" for f in e.flags):
                    current_deprecated = True
                break

        return UpdateStatus(
            os_tag=self.os_tag,
            current_version=self.current_version,
            latest=latest,
            update_available=bool(update_available),
            current_deprecated=bool(current_deprecated),
        )

    def _should_show(self, status: UpdateStatus) -> bool:
        if status.current_deprecated:
            return True
        if not status.update_available or status.latest is None:
            return False
        if self._snooze_until_version and self._snooze_until_version.strip() == status.latest.version.strip():
            return False
        return True

    def _open_dialog(self, font: pygame.font.Font, status: UpdateStatus) -> None:
        if status.latest is None:
            return
        self._dialog = _UpdateDialog(
            font=font,
            theme=self.theme,
            status=status,
            releases_url=self.releases_url,
            project_url=self.project_url,
            on_snooze=self._set_snooze_until,
            on_download=self._start_download_for_latest,
        )

    def _set_snooze_until(self, version: str) -> None:
        self._snooze_until_version = str(version).strip()
        _save_json(self._state_path, {"snooze_until_version": self._snooze_until_version})

    def _start_download_for_latest(self, url: str) -> None:
        if self._download_worker.running():
            return

        with self._download_lock:
            self._download_path = None
            self._download_error = None
            self._download_done = False

        def work() -> None:
            try:
                dest_dir = _downloads_dir()
                name = Path(urllib.parse.urlparse(url).path).name
                if not name:
                    name = f"{self.app_id}-{self.os_tag}-{self.current_version}.bin"
                out_path = _unique_path(dest_dir / name)

                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": f"{self.app_id}/{self.current_version} (update-download)"},
                )
                with urllib.request.urlopen(req, timeout=float(self.http_timeout_s)) as resp:
                    with out_path.open("wb") as f:
                        while True:
                            chunk = resp.read(256 * 1024)
                            if not chunk:
                                break
                            f.write(chunk)

                with self._download_lock:
                    self._download_path = str(out_path)
                    self._download_done = True
            except Exception as e:
                with self._download_lock:
                    self._download_error = str(e)
                    self._download_done = True

        self._download_worker.start(work)

    def pump(self, font: pygame.font.Font) -> None:
        with self._result_lock:
            status = self._pending_status
            notice = self._pending_notice
            interactive = self._pending_interactive
            force = self._pending_force
            self._pending_status = None
            self._pending_notice = None
            self._pending_interactive = False
            self._pending_force = False

        if notice is not None:
            msg, is_err = notice
            self._show_toast(msg, is_error=is_err, seconds=2.5, sticky=False)
            return

        if status is not None:
            # Manual checks override snooze: they must show an update dialog if an update exists.
            must_show = bool(force or interactive)

            if self._dialog is None:
                if status.current_deprecated:
                    self._open_dialog(font, status)
                elif status.update_available and status.latest is not None:
                    if must_show or self._should_show(status):
                        self._open_dialog(font, status)
                    elif interactive:
                        self._show_toast("Update available (snoozed).", is_error=False, seconds=2.5, sticky=False)
                else:
                    if interactive:
                        if status.latest is None:
                            self._show_toast(
                                f"No update entry for OS: {status.os_tag}.",
                                is_error=True,
                                seconds=3.0,
                                sticky=False,
                            )
                        else:
                            self._show_toast("No updates available.", is_error=False, seconds=2.5, sticky=False)

            if interactive and self._dialog is None:
                # Clear the sticky “Checking…” if we decided not to open a dialog.
                self._toast_sticky = False
                self._toast_until = self._now() + 2.5

        if self._dialog is not None:
            with self._download_lock:
                self._dialog.set_download_state(
                    done=self._download_done,
                    path=self._download_path,
                    error=self._download_error,
                )

    def layout(self, font: pygame.font.Font, win_w: int, win_h: int) -> None:
        updates_txt = "Updates"
        uw, uh = font.size(updates_txt)

        pad_x = 10
        pad_y = 6

        self._btn_updates = pygame.Rect(
            win_w - self._corner_pad - (uw + pad_x * 2),
            win_h - self._corner_pad - (uh + pad_y * 2),
            uw + pad_x * 2,
            uh + pad_y * 2,
        )

        if self._dialog is not None:
            self._dialog.layout(win_w, win_h)

    def handle_event(self, event: pygame.event.Event, font: pygame.font.Font) -> bool:
        if self._dialog is not None and self._dialog.visible:
            return self._dialog.handle_event(event)

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            if self._btn_updates.collidepoint(mx, my):
                self.check_async(delay_s=0.0, interactive=True, force=True)
                return True

        return False

    def _draw_corner_button(self, surface: pygame.Surface, font: pygame.font.Font, rect: pygame.Rect, label: str) -> None:
        mx, my = pygame.mouse.get_pos()
        pressed = pygame.mouse.get_pressed(3)[0]
        hover = rect.collidepoint(mx, my)
        down = hover and pressed

        base_a = int(self.theme.panel_bg[3])
        fill_a = base_a
        if hover:
            fill_a = min(255, base_a + 35)
        if down:
            fill_a = min(255, base_a + 70)

        panel = pygame.Surface((rect.w, rect.h), flags=pygame.SRCALPHA)
        panel.fill((0, 0, 0, fill_a))
        surface.blit(panel, (rect.x, rect.y))

        border_col = self.theme.border
        if hover:
            border_col = tuple(min(255, int(c) + 25) for c in self.theme.border)

        pygame.draw.rect(surface, border_col, rect, width=1)

        col = self.theme.muted if not hover else self.theme.text_bright
        t = font.render(label, True, col)
        surface.blit(t, (rect.x + (rect.w - t.get_width()) // 2, rect.y + (rect.h - t.get_height()) // 2))

    def _draw_toast(self, surface: pygame.Surface, font: pygame.font.Font) -> None:
        self._clear_toast_if_expired()
        if self._toast_text is None:
            return

        msg = self._toast_text
        tw, th = font.size(msg)

        pad_x = 10
        pad_y = 7

        # Anchor above the Updates button.
        w = tw + pad_x * 2
        h = th + pad_y * 2
        x = self._btn_updates.right - w
        y = self._btn_updates.y - 8 - h

        rect = pygame.Rect(x, y, w, h)

        a = 200 if not self._toast_error else 220
        panel = pygame.Surface((rect.w, rect.h), flags=pygame.SRCALPHA)
        panel.fill((0, 0, 0, a))
        surface.blit(panel, (rect.x, rect.y))

        border_col = self.theme.border
        if self._toast_error:
            border_col = (min(255, border_col[0] + 35), border_col[1], border_col[2])

        pygame.draw.rect(surface, border_col, rect, width=1)

        col = self.theme.text_bright if self._toast_error else self.theme.muted
        t = font.render(msg, True, col)
        surface.blit(t, (rect.x + pad_x, rect.y + pad_y))

    def draw_corner_ui(self, surface: pygame.Surface, font: pygame.font.Font) -> None:
        self._draw_corner_button(surface, font, self._btn_updates, "Updates")
        self._draw_toast(surface, font)

    def draw_dialog_overlay(self, surface: pygame.Surface) -> None:
        if self._dialog is None:
            return
        self._dialog.draw(surface)


class _UpdateDialog:
    def __init__(
        self,
        *,
        font: pygame.font.Font,
        theme: UpdateUITheme,
        status: UpdateStatus,
        releases_url: str,
        project_url: str,
        on_snooze: Callable[[str], None],
        on_download: Callable[[str], None],
    ) -> None:
        self.font = font
        self.theme = theme
        self.status = status
        self.releases_url = releases_url
        self.project_url = project_url
        self.on_snooze = on_snooze
        self.on_download = on_download

        self.visible: bool = True
        self.request_quit: bool = False

        self._rect = pygame.Rect(0, 0, 560, 260)
        self._chk_rect = pygame.Rect(0, 0, 18, 18)

        self._btn_download = pygame.Rect(0, 0, 0, 0)
        self._btn_releases = pygame.Rect(0, 0, 0, 0)
        self._btn_skip = pygame.Rect(0, 0, 0, 0)

        self._snooze_checked: bool = False

        self._download_done: bool = False
        self._download_path: Optional[str] = None
        self._download_error: Optional[str] = None
        self._download_requested: bool = False
        self._exit_when_download_done: bool = False

        self.layout(1280, 720)

    def set_download_state(self, *, done: bool, path: Optional[str], error: Optional[str]) -> None:
        self._download_done = bool(done)
        self._download_path = path
        self._download_error = error

        if self.status.current_deprecated and self._exit_when_download_done and self._download_done:
            self.request_quit = True
            self.visible = False

    def layout(self, win_w: int, win_h: int) -> None:
        self._rect = pygame.Rect(0, 0, 560, 260)
        self._rect.center = (win_w // 2, win_h // 2)

        pad = 18
        btn_h = 34
        btn_w = 160
        gap = 10

        bx = self._rect.x + pad
        by = self._rect.bottom - pad - btn_h

        self._btn_download = pygame.Rect(bx, by, btn_w, btn_h)
        self._btn_releases = pygame.Rect(bx + btn_w + gap, by, btn_w, btn_h)
        self._btn_skip = pygame.Rect(bx + (btn_w + gap) * 2, by, btn_w, btn_h)

        self._chk_rect = pygame.Rect(self._rect.x + pad, self._rect.y + 140, 18, 18)

    def _draw_button(self, surface: pygame.Surface, rect: pygame.Rect, label: str, enabled: bool = True) -> None:
        mx, my = pygame.mouse.get_pos()
        pressed = pygame.mouse.get_pressed(3)[0]
        hover = rect.collidepoint(mx, my)
        down = hover and pressed and enabled

        a = 175 if enabled else 120
        if hover and enabled:
            a = min(255, a + 25)
        if down:
            a = min(255, a + 50)

        panel = pygame.Surface((rect.w, rect.h), flags=pygame.SRCALPHA)
        panel.fill((0, 0, 0, a))
        surface.blit(panel, (rect.x, rect.y))

        border_col = self.theme.border
        if hover and enabled:
            border_col = tuple(min(255, int(c) + 25) for c in self.theme.border)
        pygame.draw.rect(surface, border_col, rect, width=1)

        col = self.theme.text_bright if enabled else self.theme.muted
        if hover and enabled:
            col = self.theme.text_bright

        t = self.font.render(label, True, col)
        surface.blit(t, (rect.x + (rect.w - t.get_width()) // 2, rect.y + (rect.h - t.get_height()) // 2))

    def _open_releases(self) -> None:
        try:
            webbrowser.open(self.releases_url)
        except Exception:
            pass

    def _request_download(self) -> None:
        if self.status.latest is None:
            return
        self._download_requested = True
        self.on_download(self.status.latest.download_url)

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not self.visible:
            return False

        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            if self.status.current_deprecated:
                self.request_quit = True
            self.visible = False
            return True

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos

            if not self._rect.collidepoint(mx, my):
                return True  # modal: consume everything outside

            snooze_allowed = not self.status.current_deprecated
            if snooze_allowed and self._chk_rect.inflate(6, 6).collidepoint(mx, my):
                self._snooze_checked = not self._snooze_checked
                return True

            download_enabled = not self._download_requested
            if self._btn_download.collidepoint(mx, my) and download_enabled:
                self._request_download()
                if self.status.current_deprecated:
                    self._exit_when_download_done = True
                return True

            if self._btn_releases.collidepoint(mx, my):
                self._open_releases()
                if self.status.current_deprecated:
                    self.request_quit = True
                self.visible = False
                return True

            if self._btn_skip.collidepoint(mx, my):
                if self.status.current_deprecated:
                    self.request_quit = True
                    self.visible = False
                    return True

                if self._snooze_checked and self.status.latest is not None:
                    self.on_snooze(self.status.latest.version)
                self.visible = False
                return True

            return True

        return True

    def draw(self, surface: pygame.Surface) -> None:
        if not self.visible or self.status.latest is None:
            return

        dim = pygame.Surface(surface.get_size(), flags=pygame.SRCALPHA)
        dim.fill((0, 0, 0, 140))
        surface.blit(dim, (0, 0))

        panel = pygame.Surface((self._rect.w, self._rect.h), flags=pygame.SRCALPHA)
        panel.fill(self.theme.panel_bg)
        surface.blit(panel, (self._rect.x, self._rect.y))
        pygame.draw.rect(surface, self.theme.border, self._rect, width=1)

        pad = 18
        x = self._rect.x + pad
        y = self._rect.y + pad

        title = "Update required" if self.status.current_deprecated else "Update available"
        t = self.font.render(title, True, self.theme.text_bright)
        surface.blit(t, (x, y))
        y += 28

        lines: list[str] = [
            f"Current: {self.status.current_version}   Latest: {self.status.latest.version}   OS: {self.status.os_tag}",
        ]

        flags = ", ".join(self.status.latest.flags) if self.status.latest.flags else ""
        if flags:
            lines.append(f"Latest flags: {flags}")

        if self.status.current_deprecated:
            lines.append("This version is deprecated. You must update to continue using reXact-fps.")
        else:
            lines.append("An update is available. You can download it or open the releases page.")

        if self._download_requested:
            if not self._download_done:
                lines.append("Downloading update…")
            else:
                if self._download_error:
                    lines.append(f"Download failed: {self._download_error}")
                elif self._download_path:
                    lines.append(f"Downloaded to: {self._download_path}")

        for ln in lines:
            tt = self.font.render(ln, True, self.theme.muted)
            surface.blit(tt, (x, y))
            y += 20

        if not self.status.current_deprecated:
            pygame.draw.rect(surface, self.theme.border, self._chk_rect, width=1)
            if self._snooze_checked:
                inner = self._chk_rect.inflate(-6, -6)
                pygame.draw.rect(surface, self.theme.text_bright, inner, border_radius=2)

            lbl = "Don't warn me until next version"
            tt = self.font.render(lbl, True, self.theme.text_bright)
            surface.blit(tt, (self._chk_rect.right + 10, self._chk_rect.y + (self._chk_rect.h - tt.get_height()) // 2))

        download_label = "Download update"
        download_enabled = not self._download_requested
        if self._download_requested and not self._download_done:
            download_label = "Downloading…"
        elif self._download_requested and self._download_done and self._download_error is None:
            download_label = "Downloaded"
        elif self._download_requested and self._download_done and self._download_error is not None:
            download_label = "Retry download"
            download_enabled = True
            self._download_requested = False
            self._download_done = False
            self._download_error = None

        self._draw_button(surface, self._btn_download, download_label, enabled=download_enabled)
        self._draw_button(surface, self._btn_releases, "Go to releases", enabled=True)
        self._draw_button(surface, self._btn_skip, "Don't update", enabled=True)
