#!/usr/bin/env python3
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from lib import Canvas, font, log
from lib.card import Card
from datetime import datetime
from PIL import Image


class ClockCard(Card):
    name = 'clock'
    default_refresh = 60
    sync_to_minute = True

    def fetch(self) -> dict:
        return {'now': datetime.now()}

    def render(self, data: dict) -> Canvas:
        now = data['now']
        log(f"clock: rendering {now.strftime('%H:%M')}")

        c = Canvas()

        c.text_centered(100, now.strftime('%A').upper(), font(80))
        c.hline(260, 80, 1368, color=150, width=2)
        c.text_centered(290, now.strftime('%H:%M'), font(310, bold=True))
        c.hline(665, 80, 1368, color=150, width=2)
        c.text_centered(705, now.strftime('%d %B %Y'), font(80))
        c.hline(845, 80, 1368, color=210, width=1)
        c.text_centered(880, 'Week ' + now.strftime('%V'), font(55))

        c.img = c.img.transpose(Image.ROTATE_90)
        return c


if __name__ == '__main__':
    ClockCard().run()
