#!/usr/bin/env python3
from __future__ import annotations
import math
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from lib import Canvas, font, log
from lib.card import Card
from datetime import datetime
from PIL import Image

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None  # type: ignore[assignment,misc]

# ── Layout (pre-rotation coordinates = landscape display coordinates) ─────────
#
# Landscape Kindle: 1448 wide × 1072 tall
#   LEFT section  (x=0..723):   large local clock
#   RIGHT section (x=724..1447): 2×2 grid of small remote clocks
#
#        0      724     1086     1448
#        |       |        |       |
#   0    |       |  [1]   |  [2]  |
#        | LOCAL |        |       |
#  536   |       +--------+-------+
#        | CLOCK |  [3]   |  [4]  |
#  1072  |       |        |       |
#
SPLIT_X = 724          # left | right section divider
INNER_X = 1086         # clock [1,3] | [2,4] divider
SPLIT_Y = 536          # clock [1,2] | [3,4] divider

LOCAL_X  = 362         # center x of local clock
LOCAL_Y  = 471         # center y of local clock (slightly above screen center for label room)
LOCAL_R  = 250         # radius of local clock face

SMALL_CXS = [905, 1267]  # x-centers of small clock columns
SMALL_CYS = [210, 746]   # y-centers of small clock rows (vertically centered in cell+labels)
SMALL_R   = 130          # radius of small clock faces


def _city_from_tz(tz: str) -> str:
    """Extract a readable city name from an IANA timezone string, or return ''."""
    city = tz.split('/')[-1].replace('_', ' ').strip()
    # Reject placeholder values Kindle firmware writes into /etc/TZ
    if city.lower() in ('', 'tz', 'utc', 'gmt', 'localtime'):
        return ''
    return city


def _local_city() -> str:
    if env := os.environ.get('WORLD_CLOCK_LOCAL_CITY', ''):
        return env
    # TZ env var — Kindle sometimes sets this to the IANA name
    if city := _city_from_tz(os.environ.get('TZ', '')):
        return city
    # /etc/timezone — standard Linux
    try:
        if city := _city_from_tz(open('/etc/timezone').read().strip()):
            return city
    except Exception:
        pass
    # /etc/localtime symlink (e.g. → /usr/share/zoneinfo/Europe/Amsterdam)
    try:
        lt = os.readlink('/etc/localtime')
        if 'zoneinfo' in lt:
            if city := _city_from_tz(lt.split('zoneinfo/')[-1]):
                return city
    except Exception:
        pass
    # Python's own time module as last resort
    try:
        import time as _time
        name = _time.tzname[0]
        if name and name.lower() not in ('tz', 'utc', 'gmt', ''):
            return name
    except Exception:
        pass
    return 'Local'


def _resolve_tz(tz_name: str) -> tuple[datetime, str]:
    if ZoneInfo is not None and tz_name:
        try:
            tz = ZoneInfo(tz_name)
            dt = datetime.now(tz)
            return dt, dt.strftime('%Z')
        except Exception:
            pass
    dt = datetime.utcnow()
    return dt, 'UTC'


def _text_cx(c: Canvas, cx: int, y: int, text: str, fnt, color: int = 0) -> None:
    """Draw text horizontally centered on cx."""
    bb = c._draw.textbbox((0, 0), text, font=fnt)
    w = bb[2] - bb[0]
    c._draw.text((cx - w // 2, y), text, font=fnt, fill=color)


def _draw_clock_face(c: Canvas, cx: int, cy: int, r: int, dt: datetime) -> None:
    draw = c._draw
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=255, outline=0, width=5)
    for i in range(60):
        angle = math.radians(i * 6 - 90)
        is_hour = (i % 5 == 0)
        outer = r - 6
        inner = r - (30 if is_hour else 12)
        lw = 6 if is_hour else 2
        x1 = cx + outer * math.cos(angle)
        y1 = cy + outer * math.sin(angle)
        x2 = cx + inner * math.cos(angle)
        y2 = cy + inner * math.sin(angle)
        draw.line([(x1, y1), (x2, y2)], fill=0, width=lw)
    h_angle = math.radians((dt.hour % 12 + dt.minute / 60) * 30 - 90)
    draw.line(
        [(cx, cy), (cx + r * 0.54 * math.cos(h_angle), cy + r * 0.54 * math.sin(h_angle))],
        fill=0, width=11,
    )
    m_angle = math.radians((dt.minute + dt.second / 60) * 6 - 90)
    draw.line(
        [(cx, cy), (cx + r * 0.82 * math.cos(m_angle), cy + r * 0.82 * math.sin(m_angle))],
        fill=0, width=7,
    )
    dot = 14
    draw.ellipse([cx - dot, cy - dot, cx + dot, cy + dot], fill=0)


class WorldClocksCard(Card):
    name = 'worldclocks'
    default_refresh = 60
    sync_to_minute = True

    def _get_clock(self, n: int) -> tuple[datetime | None, str, str]:
        tz_key = os.environ.get(f'WORLD_CLOCK_TZ{n}', '')
        # backward-compat: WORLD_CLOCK_TZ / WORLD_CLOCK_CITY map to slot 1
        if not tz_key and n == 1:
            tz_key = os.environ.get('WORLD_CLOCK_TZ', '')
        city_key = os.environ.get(f'WORLD_CLOCK_CITY{n}', '')
        if not city_key and n == 1:
            city_key = os.environ.get('WORLD_CLOCK_CITY', '')
        if not tz_key:
            return None, city_key, ''
        dt, abbr = _resolve_tz(tz_key)
        city = city_key or _city_from_tz(tz_key) or tz_key
        return dt, city, abbr

    def fetch(self) -> dict:
        return {
            'local': datetime.now(),
            'local_city': _local_city(),
            'clocks': [self._get_clock(n) for n in range(1, 5)],
        }

    def render(self, data: dict) -> Canvas:
        local_dt: datetime = data['local']
        local_city: str = data['local_city']
        clocks = data['clocks']

        log(f"worldclocks: {local_dt.strftime('%H:%M')}  local={local_city}")

        c = Canvas()
        draw = c._draw

        # ── Local clock (left section) ────────────────────────────────────────
        _draw_clock_face(c, LOCAL_X, LOCAL_Y, LOCAL_R, local_dt)
        _text_cx(c, LOCAL_X, LOCAL_Y + LOCAL_R + 16, local_dt.strftime('%H:%M'), font(70))
        _text_cx(c, LOCAL_X, LOCAL_Y + LOCAL_R + 92, local_city, font(38), color=80)

        # ── 4 small clocks (right section, 2×2) ──────────────────────────────
        # Order: [1]=top-left, [2]=top-right, [3]=bottom-left, [4]=bottom-right
        positions = [
            (SMALL_CXS[0], SMALL_CYS[0]),
            (SMALL_CXS[1], SMALL_CYS[0]),
            (SMALL_CXS[0], SMALL_CYS[1]),
            (SMALL_CXS[1], SMALL_CYS[1]),
        ]
        for i, (cx, cy) in enumerate(positions):
            dt, city, abbr = clocks[i]
            if dt is None:
                draw.ellipse([cx - SMALL_R, cy - SMALL_R, cx + SMALL_R, cy + SMALL_R],
                             fill=255, outline=180, width=2)
                _text_cx(c, cx, cy - 24, '—', font(48), color=180)
                if city:
                    _text_cx(c, cx, cy + SMALL_R + 16, city, font(30), color=160)
                continue
            _draw_clock_face(c, cx, cy, SMALL_R, dt)
            _text_cx(c, cx, cy + SMALL_R + 14, dt.strftime('%H:%M'), font(42))
            label = f'{city}  {abbr}' if abbr and abbr != city else city
            _text_cx(c, cx, cy + SMALL_R + 60, label, font(28), color=80)

        c.img = c.img.transpose(Image.ROTATE_90)
        return c


if __name__ == '__main__':
    WorldClocksCard().run()
