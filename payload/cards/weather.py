#!/usr/bin/env python3
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from lib import Canvas, font, show_image, sleep_screen, sleep_watcher, tap_watcher, fetch_json, log
from datetime import datetime
from PIL import Image

CITY = os.environ.get('WEATHER_CITY', 'Delft')
REFRESH = int(os.environ.get('REFRESH_INTERVAL', '3600'))
TMP = '/tmp/kdash_weather.png'
ICONS_DIR = os.path.join(os.path.dirname(__file__), '..', 'icons')


# ── Day/night/twilight ────────────────────────────────────────────────────────

def _parse_time(s: str) -> int:
    """'07:23 AM' → minutes since midnight."""
    t, meridiem = s.strip().split()
    h, m = map(int, t.split(':'))
    if meridiem == 'PM' and h != 12:
        h += 12
    if meridiem == 'AM' and h == 12:
        h = 0
    return h * 60 + m


def sky_period(astronomy: dict) -> str:
    now = datetime.now().hour * 60 + datetime.now().minute
    rise = _parse_time(astronomy['sunrise'])
    sset = _parse_time(astronomy['sunset'])
    tw = 30  # civil twilight window in minutes
    if abs(now - rise) < tw or abs(now - sset) < tw:
        return 'twilight'
    return 'day' if rise < now < sset else 'night'


# ── Icon selection ────────────────────────────────────────────────────────────

def icon_for(code: int, period: str) -> str:
    night = period == 'night'

    # Twilight: only override clear sky
    if period == 'twilight' and code == 113:
        return 'wb_twilight'

    # Clear sky
    if code == 113:
        return 'nights_stay' if night else 'sunny'

    # Partly cloudy
    if code == 116:
        return 'partly_cloudy_night' if night else 'partly_cloudy_day'

    # Cloudy / overcast — same day or night
    if code in (119, 122):
        return 'cloudy'

    # Mist
    if code == 143:
        return 'mist'

    # Fog / freezing fog
    if code in (248, 260):
        return 'foggy'

    # Thunderstorm (any code with thunder)
    if code in (200, 386, 389, 392, 395):
        return 'thunderstorm'

    # Blizzard
    if code == 230:
        return 'severe_cold'

    # Blowing snow
    if code == 227:
        return 'snowing'

    # Patchy / light–heavy snow, snow showers
    if code in (179, 323, 326, 329, 332, 335, 338, 368, 371):
        return 'weather_snowy'

    # Ice pellets, sleet, freezing rain, freezing drizzle
    if code in (182, 185, 281, 284, 311, 314, 317, 320, 350, 362, 365, 374, 377):
        return 'hail'

    # Torrential rain
    if code == 359:
        return 'umbrella'

    # Heavy rain showers
    if code in (305, 308, 356):
        return 'water_drop'

    # Light drizzle
    if code in (263, 266):
        return 'grain'

    # Everything else → general rain
    return 'rainy'


# ── Fetch ─────────────────────────────────────────────────────────────────────

def fetch():
    log(f"weather: fetching {CITY}...")
    url = f'http://wttr.in/{CITY}?format=j1'
    data = fetch_json(url)
    cur = data['current_condition'][0]
    astro = data['weather'][0]['astronomy'][0]
    return {
        'temp':     cur['temp_C'] + '°C',
        'feels':    cur['FeelsLikeC'] + '°C',
        'desc':     cur['weatherDesc'][0]['value'],
        'humidity': cur['humidity'] + '%',
        'wind':     cur['windspeedKmph'] + ' km/h',
        'code':     int(cur['weatherCode']),
        'period':   sky_period(astro),
    }


# ── Render ────────────────────────────────────────────────────────────────────

ICON_SM = 60   # size of stat icons
ICON_GAP = 10  # gap between icon and value text


def _icn(name: str) -> str:
    return os.path.join(ICONS_DIR, f'{name}.png')


def _stat_left(c, x: int, y: int, icon_name: str, value: str) -> None:
    """Draw [icon] value left-aligned at (x, y)."""
    fnt = font(55)
    p = _icn(icon_name)
    if os.path.exists(p):
        c.paste_icon(p, cx=x + ICON_SM // 2, cy=y + ICON_SM // 2, size=ICON_SM)
        c.text(x + ICON_SM + ICON_GAP, y, value, fnt)
    else:
        c.text(x, y, value, fnt)


def _stat_right(c, x: int, y: int, icon_name: str, value: str) -> None:
    """Draw [icon] value right-justified to x."""
    fnt = font(55)
    vw, _ = c.measure(value, fnt)
    p = _icn(icon_name)
    if os.path.exists(p):
        icon_cx = x - vw - ICON_GAP - ICON_SM // 2
        c.paste_icon(p, cx=icon_cx, cy=y + ICON_SM // 2, size=ICON_SM)
    c.text_right(x, y, value, fnt)


def render(w):
    icon_name = icon_for(w['code'], w['period'])
    log(f"weather: {w['period']} {icon_name} {w['temp']} {w['desc']}")

    c = Canvas()

    # Condition icon
    if os.path.exists(_icn(icon_name)):
        c.paste_icon(_icn(icon_name), cx=724, cy=130, size=200)

    # City with location pin
    loc_path = _icn('location_on')
    city_fnt = font(80, bold=True)
    if os.path.exists(loc_path):
        pin_sz = 60
        cw, _ = c.measure(CITY, city_fnt)
        block_w = pin_sz + 8 + cw
        bx = (c.w - block_w) // 2
        c.paste_icon(loc_path, cx=bx + pin_sz // 2, cy=268, size=pin_sz)
        c.text(bx + pin_sz + 8, 240, CITY, city_fnt)
    else:
        c.text_centered(240, CITY, city_fnt)

    c.text_centered(355, w['temp'],  font(220, bold=True))
    c.text_centered(620, w['desc'],  font(65))

    c.divider(710)

    _stat_left(c,  200, 750, 'device_thermostat',  w['feels'])
    _stat_left(c,  200, 855, 'humidity_percentage', w['humidity'])
    _stat_right(c, 1248, 750, 'air',               w['wind'])

    c.img = c.img.transpose(Image.ROTATE_90)
    c.save(TMP)
    show_image(TMP)


# ── Loop ──────────────────────────────────────────────────────────────────────

_sleep = sleep_watcher()
_tap   = tap_watcher()
while not _sleep.is_set() and not _tap.is_set():
    try:
        render(fetch())
    except Exception as e:
        log(f"weather error: {e}")
    sleep_screen(REFRESH, _sleep, _tap)
