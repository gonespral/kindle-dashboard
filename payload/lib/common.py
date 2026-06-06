"""
kdash lib - eips display bindings, Canvas, and network helpers.

On non-Kindle hosts (no eips binary) display calls print a notice instead
of silently doing nothing, so you know what would have been called.
"""
from __future__ import annotations

import json
import os
import shutil
import ssl
import subprocess
import sys
import threading
import time
import urllib.request
from typing import Optional, Tuple

from PIL import Image, ImageDraw, ImageFont, ImageOps

# ── Screen dimensions ─────────────────────────────────────────────────────────

W, H = 1448, 1072

# ── eips helpers ─────────────────────────────────────────────────────────────

def _eips(*args: str) -> None:
    if shutil.which("eips") is None:
        print(f"[eips] {' '.join(args)}")
        return
    result = subprocess.run(["eips", *args])
    if result.returncode != 0:
        print(f"[eips] error (rc={result.returncode}): eips {' '.join(args)}")


def clear() -> None:
    _eips("-c")


def refresh() -> None:
    _eips("")


def show_text(col: int, row: int, string: str, *, highlight: bool = False) -> None:
    args = [str(col), str(row)]
    if highlight:
        args.append("-h")
    args.append(string)
    _eips(*args)


def show_image(
    path: str,
    *,
    full_refresh: bool = True,
    waveform: str = "gc16",
    x: int | None = None,
    y: int | None = None,
    invert: bool = False,
) -> None:
    args = ["-g", str(path), "-w", waveform]
    if full_refresh:
        args.append("-f")
    if x is not None:
        args += ["-x", str(x)]
    if y is not None:
        args += ["-y", str(y)]
    if invert:
        args.append("-v")
    _eips(*args)


def rectangle(
    gray: int, width: int, height: int,
    *, x: int | None = None, y: int | None = None, waveform: str = "gc16",
) -> None:
    spec = f"l={gray:#04x},w={width},h={height}"
    args = ["-d", spec, "-w", waveform]
    if x is not None:
        args += ["-x", str(x)]
    if y is not None:
        args += ["-y", str(y)]
    _eips(*args)


def scroll(first_row: int, last_row: int) -> None:
    _eips("-z", str(first_row), str(last_row))


def log(msg: str, row: int = 0) -> None:
    """Print to stdout and display on eips row (for on-device debugging)."""
    print(msg)
    _eips("0", str(row), msg[:60])  # eips truncates long lines anyway


def prevent_screensaver(enable: bool = True) -> None:
    if shutil.which("lipc-set-prop") is None:
        print(f"[lipc] preventScreenSaver={int(enable)}")
        return
    result = subprocess.run(
        ["lipc-set-prop", "com.lab126.powerd", "preventScreenSaver", str(int(enable))]
    )
    if result.returncode != 0:
        print(f"[lipc] error (rc={result.returncode}): preventScreenSaver={int(enable)}")


def sleep_screen(seconds: int) -> None:
    """Suspend the Kindle for `seconds` via RTC wakeup + mem sleep."""
    prevent_screensaver(False)
    rtc = "/sys/class/rtc/rtc0/wakealarm"
    power = "/sys/power/state"
    if os.path.exists(rtc) and os.path.exists(power):
        wake_at = int(time.time()) + seconds
        try:
            with open(rtc, "w") as f:
                f.write("0\n")       # clear existing alarm
            with open(rtc, "w") as f:
                f.write(f"{wake_at}\n")
            with open(power, "w") as f:
                f.write("mem\n")     # suspend-to-RAM; resumes here after wake
        except OSError as e:
            print(f"[sleep] suspend failed: {e}; falling back to sleep")
            time.sleep(seconds)
    else:
        print(f"[sleep] {seconds}s (no /sys/power/state on this host)")
        time.sleep(seconds)


def sleep_watcher() -> threading.Event:
    """Return an Event that gets set when the Kindle fires the goingToSleep LIPC event.

    Start this once at the top of a card loop. On non-Kindle hosts the event is
    never set (the watcher thread exits immediately without setting it).
    """
    stop = threading.Event()

    def _watch() -> None:
        if shutil.which('lipc-wait-event') is None:
            print('[lipc] sleep_watcher: lipc-wait-event not available')
            return
        subprocess.run(
            ['lipc-wait-event', 'com.lab126.powerd', 'goingToSleep'],
            capture_output=True,
        )
        stop.set()

    threading.Thread(target=_watch, daemon=True).start()
    return stop


# ── Network ───────────────────────────────────────────────────────────────────

def fetch_json(url: str, timeout: int = 15, verify_ssl: bool = False,
               headers: dict | None = None, body: dict | None = None) -> dict:
    """Fetch a URL and return parsed JSON. Uses stdlib only.
    verify_ssl=False by default — Kindle's CA bundle is too old for most sites.
    Pass body dict to make a POST request with JSON body.
    """
    h = {"User-Agent": "kdash/1.0"}
    if headers:
        h.update(headers)
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, headers=h, data=data)
    ctx = ssl.create_default_context() if verify_ssl else ssl._create_unverified_context()
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        return json.loads(resp.read().decode())


def fetch_json_with_headers(url: str, timeout: int = 15, verify_ssl: bool = False,
                            headers: dict | None = None,
                            body: dict | None = None) -> tuple:
    """Like fetch_json but also returns response headers as a dict."""
    h = {"User-Agent": "kdash/1.0"}
    if headers:
        h.update(headers)
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, headers=h, data=data)
    ctx = ssl.create_default_context() if verify_ssl else ssl._create_unverified_context()
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        resp_headers = {k.lower(): v for k, v in resp.info().items()}
        return json.loads(resp.read().decode()), resp_headers


# ── Fonts ─────────────────────────────────────────────────────────────────────

_FONT_DIRS = [
    os.path.join(os.path.dirname(__file__), '..', 'fonts'),  # bundled — works on host + Kindle
    '/usr/java/lib/fonts',
    '/usr/share/fonts/truetype/dejavu',
    '/usr/share/fonts/dejavu-sans-fonts',
    '/usr/share/fonts/dejavu',
    '/mnt/us/fonts',
]
_font_cache: dict[tuple, ImageFont.FreeTypeFont] = {}


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    key = (size, bold)
    if key in _font_cache:
        return _font_cache[key]

    names = ['DejaVuSans-Bold.ttf', 'DejaVuSans.ttf'] if bold \
        else ['DejaVuSans.ttf', 'DejaVuSans-Bold.ttf']

    # 1. Check known Kindle + common Linux/Mac dirs
    for d in _FONT_DIRS:
        for name in names:
            p = os.path.join(d, name)
            if os.path.exists(p):
                f = ImageFont.truetype(p, size)
                _font_cache[key] = f
                return f

    # 2. Ask fontconfig (works on any desktop Linux/Mac with fc-match)
    try:
        query = 'DejaVuSans:weight=bold' if bold else 'DejaVuSans'
        result = subprocess.run(
            ['fc-match', '-f', '%{file}', query],
            capture_output=True, text=True, timeout=3,
        )
        path = result.stdout.strip()
        if path and os.path.exists(path):
            print(f"[font] using {path} (via fc-match)")
            f = ImageFont.truetype(path, size)
            _font_cache[key] = f
            return f
    except Exception:
        pass

    # 3. Pick any .ttf we can find in the known dirs (Kindle fallback)
    for d in _FONT_DIRS:
        if not os.path.isdir(d):
            continue
        for name in os.listdir(d):
            if name.lower().endswith('.ttf'):
                p = os.path.join(d, name)
                print(f"[font] falling back to {p}")
                f = ImageFont.truetype(p, size)
                _font_cache[key] = f
                return f

    raise RuntimeError(
        "No TrueType font found. Add a .ttf path to _FONT_DIRS in lib/common.py"
    )


# ── Canvas ────────────────────────────────────────────────────────────────────

Color = int  # 0 = black, 255 = white


class Canvas:
    def __init__(self, w: int = W, h: int = H, bg: Color = 255):
        self.w = w
        self.h = h
        self.img = Image.new('L', (w, h), bg)
        self._draw = ImageDraw.Draw(self.img)

    # Text

    def text(self, x: int, y: int, string: str, fnt: ImageFont.FreeTypeFont,
             color: Color = 0) -> Tuple[int, int]:
        self._draw.text((x, y), string, font=fnt, fill=color)
        bb = self._draw.textbbox((x, y), string, font=fnt)
        return bb[2] - bb[0], bb[3] - bb[1]

    def text_centered(self, y: int, string: str, fnt: ImageFont.FreeTypeFont,
                      color: Color = 0, x_offset: int = 0) -> Tuple[int, int]:
        bb = self._draw.textbbox((0, 0), string, font=fnt)
        x = (self.w - (bb[2] - bb[0])) // 2 + x_offset
        return self.text(x, y, string, fnt, color)

    def text_right(self, x: int, y: int, string: str, fnt: ImageFont.FreeTypeFont,
                   color: Color = 0) -> Tuple[int, int]:
        bb = self._draw.textbbox((0, 0), string, font=fnt)
        return self.text(x - (bb[2] - bb[0]), y, string, fnt, color)

    def measure(self, string: str, fnt: ImageFont.FreeTypeFont) -> Tuple[int, int]:
        bb = self._draw.textbbox((0, 0), string, font=fnt)
        return bb[2] - bb[0], bb[3] - bb[1]

    # Shapes

    def line(self, x1: int, y1: int, x2: int, y2: int,
             color: Color = 0, width: int = 2) -> None:
        self._draw.line([(x1, y1), (x2, y2)], fill=color, width=width)

    def hline(self, y: int, x1: int = 0, x2: Optional[int] = None,
              color: Color = 0, width: int = 2) -> None:
        self._draw.line([(x1, y), (x2 if x2 is not None else self.w, y)],
                        fill=color, width=width)

    def rect(self, x: int, y: int, w: int, h: int,
             fill: Optional[Color] = None, outline: Optional[Color] = 0,
             width: int = 2) -> None:
        self._draw.rectangle([x, y, x + w, y + h], fill=fill, outline=outline, width=width)

    def ellipse(self, x: int, y: int, w: int, h: int,
                fill: Optional[Color] = None, outline: Optional[Color] = 0,
                width: int = 2) -> None:
        self._draw.ellipse([x, y, x + w, y + h], fill=fill, outline=outline, width=width)

    # Layout

    def divider(self, y: int, margin: int = 60, color: Color = 180, width: int = 2) -> None:
        self.hline(y, margin, self.w - margin, color=color, width=width)

    def column_divider(self, x: int, margin: int = 60, color: Color = 180, width: int = 2) -> None:
        self._draw.line([(x, margin), (x, self.h - margin)], fill=color, width=width)

    # Icons

    def paste_icon(self, path: str, cx: int, cy: int, size: int) -> None:
        """Paste a grayscale icon PNG centered at (cx, cy), scaled to size×size.
        White areas of the icon are treated as transparent.
        """
        icon = Image.open(path).convert('L').resize((size, size), Image.LANCZOS)
        mask = ImageOps.invert(icon)  # dark icon pixels → fully opaque in mask
        x = cx - size // 2
        y = cy - size // 2
        self.img.paste(icon, (x, y), mask=mask)

    # Charts

    def bar_chart(self, x: int, y: int, w: int, h: int,
                  values: list[float], labels: list[str] | None = None,
                  fnt: ImageFont.FreeTypeFont | None = None) -> None:
        if not values:
            return
        max_val = max(values) or 1
        n = len(values)
        gap = max(2, w // (n * 6))
        bar_w = (w - gap * (n + 1)) // n
        fnt = fnt or font(22)
        for i, v in enumerate(values):
            bh = int((v / max_val) * h)
            bx = x + gap + i * (bar_w + gap)
            by = y + h - bh
            self._draw.rectangle([bx, by, bx + bar_w, y + h], fill=0)
            if labels and i < len(labels):
                lw, _ = self.measure(labels[i], fnt)
                self._draw.text((bx + (bar_w - lw) // 2, y + h + 6),
                                labels[i], font=fnt, fill=0)

    # Output

    def save(self, path: str = '/tmp/kdash.png') -> str:
        self.img.save(path)
        if shutil.which("eips") is None:
            opener = 'open' if sys.platform == 'darwin' else 'xdg-open'
            if shutil.which(opener):
                subprocess.Popen([opener, path])
        return path
