#!/usr/bin/env python3
"""Buienradar card — shows rain radar map and 2-hour rain forecast."""
import io
import json
import math
import os
import ssl
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from lib import Canvas, font, log, prevent_screensaver, show_image, sleep_screen
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps

POSTCODE  = os.environ.get('BUIENALARM_POSTCODE', '')
_LAT      = os.environ.get('BUIENALARM_LAT', '')
_LON      = os.environ.get('BUIENALARM_LON', '')
REFRESH   = int(os.environ.get('REFRESH_INTERVAL', '600'))
TMP       = '/tmp/kdash_buienradar.png'
ICONS_DIR = os.path.join(os.path.dirname(__file__), '..', 'icons')

GEOCODE_URL = ('https://nominatim.openstreetmap.org/search'
               '?postalcode={postcode}&country=NL&format=json&limit=1')


def resolve_coords() -> tuple:
    """Return (lat, lon) — from env vars if set, otherwise geocode the postcode."""
    if _LAT and _LON:
        return float(_LAT), float(_LON)
    if not POSTCODE:
        raise RuntimeError('Set BUIENALARM_POSTCODE (and optionally LAT/LON) in sync.conf')
    log(f'buienradar: geocoding {POSTCODE}...')
    url = GEOCODE_URL.format(postcode=POSTCODE.replace(' ', '+'))
    ctx = ssl._create_unverified_context()
    req = urllib.request.Request(url, headers={'User-Agent': 'kdash/1.0'})
    with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
        results = json.loads(r.read().decode())
    if not results:
        raise RuntimeError(f'Postcode {POSTCODE} not found via Nominatim')
    return float(results[0]['lat']), float(results[0]['lon'])

# NL radar image geographic bounds (from buienradar.nl gadget source)
RADAR_LON_START = 0.0
RADAR_LON_END   = 10.0
RADAR_LAT_START = 54.8   # north (top of image)
RADAR_LAT_END   = 49.5   # south (bottom of image)

METADATA_URL = (
    'https://image-lite.buienradar.nl/3.0/metadata/'
    'RadarMapRain5mNL?size=Full&history=1&forecast=0'
)
RAIN_URL = 'https://gpsgadget.buienradar.nl/data/raintext?lat={lat:.2f}&lon={lon:.2f}'


def _fetch(url: str, timeout: int = 20) -> bytes:
    ctx = ssl._create_unverified_context()
    req = urllib.request.Request(url, headers={'User-Agent': 'kdash/1.0'})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.read()


def fetch_rain() -> list:
    text = _fetch(RAIN_URL.format(lat=LAT, lon=LON)).decode()
    result = []
    for line in text.strip().splitlines():
        if '|' not in line:
            continue
        val_str, time_str = line.split('|')
        result.append({'value': int(val_str.strip()), 'time': time_str.strip()})
    return result


def fetch_radar() -> Image.Image:
    meta = json.loads(_fetch(METADATA_URL))
    img_url = meta.get('still') or meta['times'][-1]['url']
    raw = _fetch(img_url, timeout=30)
    return Image.open(io.BytesIO(raw)).convert('RGBA')


BASEMAP_CACHE = '/tmp/kdash_basemap.png'
OSM_TILE = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'


def _fetch_basemap(lat: float, lon: float, half_lon: float, half_lat: float,
                   crop_px: int, zoom: int = 8) -> Image.Image:
    """Stitch OSM tiles covering the bbox, return a grayscale image of crop_px×crop_px."""
    TILE = 256
    n = 2 ** zoom

    def lon_to_tx(ln): return (ln + 180) / 360 * n
    def lat_to_ty(la):
        lr = math.radians(la)
        return (1 - math.log(math.tan(lr) + 1 / math.cos(lr)) / math.pi) / 2 * n
    def tx_to_lon(tx): return tx / n * 360 - 180
    def ty_to_lat(ty): return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * ty / n))))

    lon_min, lon_max = lon - half_lon, lon + half_lon
    lat_min, lat_max = lat - half_lat, lat + half_lat

    tx_min = int(lon_to_tx(lon_min))
    tx_max = int(lon_to_tx(lon_max))
    ty_min = int(lat_to_ty(lat_max))   # lat_max → smaller tile y (north)
    ty_max = int(lat_to_ty(lat_min))

    cols = tx_max - tx_min + 1
    rows = ty_max - ty_min + 1
    stitched = Image.new('L', (TILE * cols, TILE * rows), 220)

    for ty in range(ty_min, ty_max + 1):
        for tx in range(tx_min, tx_max + 1):
            url = OSM_TILE.format(z=zoom, x=tx, y=ty)
            try:
                tile = Image.open(io.BytesIO(_fetch(url, timeout=10))).convert('L')
                stitched.paste(tile, ((tx - tx_min) * TILE, (ty - ty_min) * TILE))
            except Exception:
                pass

    # Map the crop bbox onto stitched pixel coords (linear approx — error < 3px for NL)
    sw, sh = stitched.size
    stitch_lon_min = tx_to_lon(tx_min)
    stitch_lon_max = tx_to_lon(tx_max + 1)
    stitch_lat_max = ty_to_lat(ty_min)
    stitch_lat_min = ty_to_lat(ty_max + 1)

    x0 = int((lon_min - stitch_lon_min) / (stitch_lon_max - stitch_lon_min) * sw)
    x1 = int((lon_max - stitch_lon_min) / (stitch_lon_max - stitch_lon_min) * sw)
    y0 = int((stitch_lat_max - lat_max) / (stitch_lat_max - stitch_lat_min) * sh)
    y1 = int((stitch_lat_max - lat_min) / (stitch_lat_max - stitch_lat_min) * sh)

    return stitched.crop((x0, y0, x1, y1)).resize((crop_px, crop_px), Image.LANCZOS)


def get_basemap(lat: float, lon: float, half_lon: float, half_lat: float,
                crop_px: int) -> Image.Image:
    """Return cached basemap or fetch fresh from OSM."""
    if os.path.exists(BASEMAP_CACHE):
        try:
            return Image.open(BASEMAP_CACHE).convert('L')
        except Exception:
            pass
    img = _fetch_basemap(lat, lon, half_lon, half_lat, crop_px)
    try:
        img.save(BASEMAP_CACHE)
    except Exception:
        pass
    return img


def radar_crop(radar: Image.Image, lat: float, lon: float,
               crop_px: int = 280, display_size: int = 480) -> Image.Image:
    """Crop radar around lat/lon, composite over OSM basemap, mark location."""
    w, h = radar.size
    px = int((lon - RADAR_LON_START) / (RADAR_LON_END - RADAR_LON_START) * w)
    py = int((RADAR_LAT_START - lat) / (RADAR_LAT_START - RADAR_LAT_END) * h)

    half = crop_px // 2
    x0 = max(0, px - half)
    y0 = max(0, py - half)
    x1 = min(w, x0 + crop_px)
    y1 = min(h, y0 + crop_px)
    cropped = radar.crop((x0, y0, x1, y1))   # RGBA: rain=colored+opaque, clear=transparent

    # Use the alpha channel directly as the rain signal.
    # Higher alpha → more rain. Inverted alpha → darker pixel for more rain.
    radar_alpha = cropped.split()[3]           # 0 = no rain, 255 = heavy rain
    rain_dark   = ImageOps.invert(radar_alpha) # 255 = no rain (white), 0 = heavy rain (black)

    # OSM basemap, slightly brightened so rain (dark) always reads on top
    half_lon = (crop_px / w) * (RADAR_LON_END - RADAR_LON_START) / 2
    half_lat = (crop_px / h) * (RADAR_LAT_START - RADAR_LAT_END) / 2
    try:
        basemap = get_basemap(lat, lon, half_lon, half_lat, crop_px)
        basemap = ImageEnhance.Contrast(basemap).enhance(2.0)
        basemap = ImageEnhance.Brightness(basemap).enhance(1.3)
        # composite(img1, img2, mask): returns img1 where mask=255, img2 where mask=0
        # So: where rain (alpha=255) → rain_dark; where clear (alpha=0) → basemap
        merged = Image.composite(rain_dark, basemap, radar_alpha)
    except Exception as e:
        log(f'buienradar: basemap failed ({e}), radar only')
        white  = Image.new('L', rain_dark.size, 255)
        merged = Image.composite(rain_dark, white, radar_alpha)

    # Draw crosshair
    dot_x, dot_y = px - x0, py - y0
    draw = ImageDraw.Draw(merged)
    arm, r = 18, 10
    draw.line([dot_x - arm, dot_y, dot_x + arm, dot_y], fill=0, width=3)
    draw.line([dot_x, dot_y - arm, dot_x, dot_y + arm], fill=0, width=3)
    draw.ellipse([dot_x - r, dot_y - r, dot_x + r, dot_y + r], outline=0, width=3)

    return merged.resize((display_size, display_size), Image.LANCZOS)


def intensity_label(v: int) -> str:
    if v == 0:   return 'Dry'
    if v < 25:   return 'Drizzle'
    if v < 75:   return 'Light rain'
    if v < 150:  return 'Moderate rain'
    return 'Heavy rain'


def icon_for(v: int) -> str:
    if v == 0:   return 'wb_sunny'
    if v < 25:   return 'grain'
    if v < 75:   return 'rainy'
    if v < 150:  return 'water_drop'
    return 'umbrella'


def render(rain: list, radar: Image.Image) -> None:
    c = Canvas()

    # ── Header ──────────────────────────────────────────────────────────────
    c.text_centered(40, 'Buienradar', font(70, bold=True))
    c.text_centered(135, POSTCODE, font(45))
    c.divider(200)

    # ── Left column: radar map (x=60, y=220) ────────────────────────────────
    MAP_SIZE = 480
    MAP_X, MAP_Y = 60, 220
    c.rect(MAP_X - 2, MAP_Y - 2, MAP_SIZE + 4, MAP_SIZE + 4,
           fill=None, outline=150, width=2)
    c.img.paste(radar, (MAP_X, MAP_Y))

    # Map caption
    c.text(MAP_X, MAP_Y + MAP_SIZE + 8, '~200 km radius', font(30), color=160)

    # ── Column divider ───────────────────────────────────────────────────────
    DIVX = 635
    c.column_divider(DIVX, margin=200)

    # ── Right column: icon + status + info ──────────────────────────────────
    current = rain[0]['value']
    status  = intensity_label(current)
    RCENTER = (DIVX + 1448) // 2   # 1041

    icon_path = os.path.join(ICONS_DIR, f'{icon_for(current)}.png')
    if os.path.exists(icon_path):
        c.paste_icon(icon_path, cx=RCENTER, cy=310, size=160)

    c.text_centered(480, status, font(65, bold=True), x_offset=RCENTER - 724)

    if current > 0:
        end_time = next((d['time'] for d in rain if d['value'] == 0), None)
        info = f'dry at {end_time}' if end_time else 'rain for the next 2h'
    else:
        start_time = next((d['time'] for d in rain if d['value'] > 0), None)
        info = f'rain at {start_time}' if start_time else 'no rain for the next 2h'

    c.text_centered(565, info, font(42), x_offset=RCENTER - 724)

    # ── Bar chart ────────────────────────────────────────────────────────────
    CHART_X = DIVX + 35
    CHART_Y = 650
    CHART_W = 1448 - CHART_X - 35
    CHART_H = 310

    values = [d['value'] for d in rain]
    labels = [rain[i]['time'] if i % 6 == 0 else '' for i in range(len(rain))]
    c.bar_chart(CHART_X, CHART_Y, CHART_W, CHART_H, values, labels, fnt=font(28))

    # ── Footer ───────────────────────────────────────────────────────────────
    c.divider(1000)
    c.text(MAP_X, 1025, f'radar: {rain[0]["time"]}', font(35), color=150)
    c.text_right(1368, 1025, 'buienradar.nl', font(35), color=150)

    c.img = c.img.transpose(Image.ROTATE_90)
    c.save(TMP)
    show_image(TMP)


LAT, LON = resolve_coords()
log(f'buienradar: {POSTCODE} → {LAT:.4f},{LON:.4f}')

while True:
    prevent_screensaver()
    try:
        rain  = fetch_rain()
        radar = radar_crop(fetch_radar(), LAT, LON)
        log(f'buienradar: {intensity_label(rain[0]["value"])} ({rain[0]["value"]})')
        render(rain, radar)
    except Exception as e:
        log(f'buienradar error: {e}')
    sleep_screen(REFRESH)
