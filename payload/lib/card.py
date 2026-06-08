#!/usr/bin/env python3
from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from abc import ABC, abstractmethod

from PIL import Image, ImageDraw

import glob

from lib.common import (
    Canvas, font, show_image,
    sleep_screen, sleep_watcher, tap_watcher,
    prevent_screensaver, log, clear,
    usb_storage_watcher,
)

LOW_BATTERY_THRESHOLD = 25
MULTI_PRESS_COUNT  = 3    # total power-button presses needed to kill all cards
MULTI_PRESS_WINDOW = 5.0  # seconds to wait for each additional press


def _count_power_presses(stop: threading.Event) -> int:
    """After an initial goingToSleep event, count rapid follow-up presses.

    Each press puts the Kindle to sleep; we watch for the next goingToSleep
    within MULTI_PRESS_WINDOW seconds.  Returns total presses including the
    first (1 = single press/refresh, MULTI_PRESS_COUNT = kill-all).
    """
    total = 1
    while total < MULTI_PRESS_COUNT and not stop.is_set():
        _next = sleep_watcher()
        sleep_screen(MULTI_PRESS_WINDOW, _next, stop)
        if _next.is_set():
            total += 1
        else:
            break
    return total


def _kill_all_cards() -> None:
    my_pid = os.getpid()
    for pidfile in glob.glob('/tmp/kdash_*.pid'):
        try:
            pid = int(open(pidfile).read().strip())
            if pid != my_pid:
                os.kill(pid, signal.SIGTERM)
        except Exception:
            pass
        try:
            os.unlink(pidfile)
        except Exception:
            pass
    subprocess.run(['pkill', '-f', '/cards/'], capture_output=True)


def read_battery() -> int | None:
    try:
        r = subprocess.run(
            ['lipc-get-prop', 'com.lab126.powerd', 'battLevel'],
            capture_output=True, text=True, timeout=2,
        )
        return int(r.stdout.strip())
    except Exception:
        return None


def _draw_battery_overlay(img: Image.Image, level: int) -> None:
    draw = ImageDraw.Draw(img)
    iw, ih = img.size
    margin = 20
    bw, bh = 90, 44
    nub_w, nub_h = 10, 18
    x = iw - margin - bw - nub_w
    y = ih - margin - bh

    draw.rectangle([x, y, x + bw, y + bh], fill=255, outline=0, width=3)
    draw.rectangle(
        [x + bw, y + (bh - nub_h) // 2, x + bw + nub_w, y + (bh - nub_h) // 2 + nub_h],
        fill=0,
    )
    fill_w = max(4, int(level / 100 * (bw - 8)))
    draw.rectangle([x + 4, y + 4, x + 4 + fill_w, y + bh - 4], fill=60)

    fnt = font(24)
    txt = f'{level}%'
    tw = draw.textbbox((0, 0), txt, font=fnt)[2]
    draw.text((x + (bw - tw) // 2, y + (bh - 28) // 2), txt, font=fnt, fill=255)


class Card(ABC):
    name: str = ''
    default_refresh: int = 600
    use_prevent_screensaver: bool = False  # kept for compat
    sync_to_minute: bool = False           # True → sleep until next minute boundary

    def __init__(self):
        self.refresh = int(os.environ.get('REFRESH_INTERVAL', str(self.default_refresh)))
        self._stop = threading.Event()

    @abstractmethod
    def fetch(self) -> dict: ...

    @abstractmethod
    def render(self, data: dict) -> Canvas:
        """Build and return a Canvas (rotate inside here). Do NOT call show_image()."""
        ...

    def data_changed(self, old: dict | None, new: dict) -> bool:
        return old != new

    def sleep_duration(self) -> int:
        if self.sync_to_minute:
            return max(1, 60 - time.localtime().tm_sec)
        return self.refresh

    def _pid_path(self) -> str:
        return f'/tmp/kdash_{self.name}.pid'

    def _write_pid(self) -> None:
        with open(self._pid_path(), 'w') as f:
            f.write(str(os.getpid()))

    def _remove_pid(self) -> None:
        try:
            os.unlink(self._pid_path())
        except OSError:
            pass

    def _setup_signals(self) -> None:
        def _handle(signum, frame):
            self._stop.set()
        signal.signal(signal.SIGTERM, _handle)
        signal.signal(signal.SIGINT, _handle)

    def _display(self, canvas: Canvas) -> None:
        level = read_battery()
        if level is not None and level <= LOW_BATTERY_THRESHOLD:
            _draw_battery_overlay(canvas.img, level)
        path = canvas.save(f'/tmp/kdash_{self.name}.png')
        show_image(path)

    def run(self) -> None:
        self._write_pid()
        self._setup_signals()

        prevent_screensaver(True)

        # tap_watcher deferred until after first render to drain KUAL launch-tap.
        _tap = threading.Event()
        _first_render_done = False
        _last_data: dict | None = None
        _usb = usb_storage_watcher()

        log(f'{self.name}: started (refresh={self.refresh}s)')
        try:
            while not self._stop.is_set():
                # Renew after each sleep — Kindle resets preventScreenSaver on wake.
                prevent_screensaver(True)

                # ── Early-exit checks ──────────────────────────────────────
                if _usb.is_set():
                    log(f'{self.name}: USB drive mode — stopping')
                    _kill_all_cards()
                    return

                if _tap.is_set():
                    clear()
                    log(f'{self.name}: tap — stopping all cards')
                    _kill_all_cards()
                    return

                # ── Fetch ─────────────────────────────────────────────────
                try:
                    _last_data = self.fetch()
                except Exception as e:
                    log(f'{self.name}: fetch error: {e}')

                # ── Render (uses cached data on fetch failure) ─────────────
                if _last_data is not None:
                    try:
                        canvas = self.render(_last_data)
                        self._display(canvas)
                    except Exception as e:
                        log(f'{self.name}: render error: {e}')

                if not _first_render_done:
                    _tap = tap_watcher()
                    _first_render_done = True

                if _tap.is_set() or self._stop.is_set():
                    if _tap.is_set():
                        clear()
                        log(f'{self.name}: tap — stopping all cards')
                        _kill_all_cards()
                    else:
                        log(f'{self.name}: stopped (SIGTERM)')
                    return

                # ── Sleep ──────────────────────────────────────────────────
                sleep_secs = self.sleep_duration()
                _sleep = sleep_watcher()
                log(f'{self.name}: sleeping {sleep_secs}s')
                sleep_screen(sleep_secs, _sleep, _tap, self._stop)

                if _sleep.is_set():
                    # Power button pressed. Count additional presses to decide
                    # whether to refresh early or kill all cards.
                    presses = _count_power_presses(self._stop)
                    log(f'{self.name}: {presses}/{MULTI_PRESS_COUNT} press(es)')
                    if presses >= MULTI_PRESS_COUNT:
                        clear()
                        log(f'{self.name}: {MULTI_PRESS_COUNT}x press — stopping all cards')
                        _kill_all_cards()
                        return
                    # Fewer presses: fall through → refresh immediately

        finally:
            prevent_screensaver(False)
            self._remove_pid()
