#!/usr/bin/env python3
"""Test card for power-button press detection."""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from datetime import datetime
from PIL import Image

from lib import Canvas, font, log
from lib.card import Card, read_battery, MULTI_PRESS_COUNT, MULTI_PRESS_WINDOW


class SleepTestCard(Card):
    name = 'sleep_test'
    default_refresh = 30

    def __init__(self):
        super().__init__()
        self._cycle = 0

    def fetch(self) -> dict:
        self._cycle += 1
        return {
            'time': datetime.now(),
            'battery': read_battery(),
            'cycle': self._cycle,
        }

    def render(self, data: dict) -> Canvas:
        c = Canvas()

        c.text_centered(60, 'Sleep Test', font(60, bold=True))
        c.text_centered(200, data['time'].strftime('%H:%M:%S'), font(160, bold=True))

        c.text_centered(390, f'Render cycle #{data["cycle"]}', font(55))

        batt = data['battery']
        c.text_centered(475, f'Battery: {batt}%' if batt is not None else 'Battery: ?', font(50))

        c.hline(570, 60, 1388, color=180, width=1)
        c.text_centered(615, f'Press power once  →  refresh early', font(40), color=100)
        c.text_centered(680, f'Press {MULTI_PRESS_COUNT}x within {MULTI_PRESS_WINDOW:.0f}s each  →  stop all cards', font(40), color=100)
        c.text_centered(745, f'Refresh every {self.refresh}s', font(40), color=150)

        c.img = c.img.transpose(Image.ROTATE_90)
        return c


if __name__ == '__main__':
    SleepTestCard().run()
