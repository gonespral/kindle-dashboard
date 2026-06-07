#!/usr/bin/env python3
"""Download Material Symbols weather SVGs and convert to grayscale PNGs.

Run once (or when icons need updating):
    python3 payload/lib/fetch_icons.py
"""

import os
import subprocess
import urllib.request

ICONS_DIR = os.path.join(os.path.dirname(__file__), '..', 'icons')
CDN = "https://fonts.gstatic.com/s/i/short-term/release/materialsymbolsoutlined/{name}/default/48px.svg"

ICONS = [
    # Day / clear
    'sunny',
    'wb_sunny',
    'wb_twilight',

    # Night / clear
    'nights_stay',

    # Partly cloudy
    'partly_cloudy_day',
    'partly_cloudy_night',

    # Overcast / cloud
    'cloudy',

    # Fog / mist
    'foggy',
    'mist',

    # Drizzle
    'grain',

    # Rain
    'rainy',
    'water_drop',
    'umbrella',

    # Snow
    'weather_snowy',
    'snowing',
    'severe_cold',

    # Ice / sleet / freezing
    'ac_unit',
    'hail',

    # Thunder
    'thunderstorm',

    # Extreme
    'tornado',
    'cyclone',
    'flood',
    'air',

    # Weather stats
    'device_thermostat',  # feels-like temperature
    'humidity_percentage',  # humidity
    'location_on',        # city name
]

SIZE = 256


def main():
    os.makedirs(ICONS_DIR, exist_ok=True)
    ok, fail = 0, 0
    for name in ICONS:
        svg_path = f'/tmp/kdash_icon_{name}.svg'
        png_path = os.path.join(ICONS_DIR, f'{name}.png')

        url = CDN.format(name=name)
        print(f"Downloading {name}...", end=' ', flush=True)
        try:
            with urllib.request.urlopen(url, timeout=10) as r:
                svg_data = r.read()
            with open(svg_path, 'wb') as f:
                f.write(svg_data)
        except Exception as e:
            print(f"FAILED ({e})")
            fail += 1
            continue

        result = subprocess.run([
            'convert',
            '-background', 'white',
            '-flatten',
            '-density', '300',
            '-resize', f'{SIZE}x{SIZE}',
            '-colorspace', 'Gray',
            svg_path, png_path,
        ], capture_output=True, text=True)

        if result.returncode != 0:
            print(f"FAILED to convert: {result.stderr.strip()}")
            fail += 1
        else:
            print(f"ok")
            ok += 1

    print(f"\nDone: {ok} icons saved to {os.path.relpath(ICONS_DIR)}, {fail} failed.")


if __name__ == '__main__':
    main()
