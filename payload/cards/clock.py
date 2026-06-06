#!/usr/bin/env python3
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from lib import Canvas, font, show_image, prevent_screensaver, sleep_screen, sleep_watcher, log
from datetime import datetime

REFRESH = int(os.environ.get('REFRESH_INTERVAL', '120'))
TMP = '/tmp/kdash_clock.png'


def render():
    now = datetime.now()
    log(f"clock: rendering {now.strftime('%H:%M')}")

    c = Canvas()

    # Day of week — small header
    c.text_centered(100, now.strftime('%A').upper(), font(80))

    c.hline(260, 80, 1368, color=150, width=2)

    # Time — dominant
    c.text_centered(290, now.strftime('%H:%M'), font(310, bold=True))

    c.hline(665, 80, 1368, color=150, width=2)

    # Date
    c.text_centered(705, now.strftime('%d %B %Y'), font(80))

    c.hline(845, 80, 1368, color=210, width=1)

    # Week number
    c.text_centered(880, 'Week ' + now.strftime('%V'), font(55))

    c.save(TMP)
    show_image(TMP)


_stop = sleep_watcher()
while not _stop.is_set():
    prevent_screensaver()
    try:
        render()
    except Exception as e:
        log(f"clock error: {e}")
    if not _stop.is_set():
        sleep_screen(REFRESH)
prevent_screensaver(False)
