#!/usr/bin/env python3
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from lib import Canvas, font, show_image, sleep_screen, sleep_watcher, tap_watcher, fetch_json, log
from datetime import datetime, timezone
from PIL import Image

ADMIN_KEY = os.environ.get('ANTHROPIC_ADMIN_API_KEY', '')
REFRESH   = int(os.environ.get('REFRESH_INTERVAL', '600'))
TMP       = '/tmp/kdash_claude.png'

USAGE_URL = 'https://api.anthropic.com/v1/organizations/usage_report/claude_code'


def fetch(date_str):
    if not ADMIN_KEY:
        raise RuntimeError('ANTHROPIC_ADMIN_API_KEY not set')
    url  = f'{USAGE_URL}?starting_at={date_str}&limit=1000'
    data = fetch_json(url, headers={
        'X-Api-Key': ADMIN_KEY,
        'anthropic-version': '2023-06-01',
    })
    return data.get('data', [])


def aggregate(records):
    sessions    = 0
    commits     = 0
    prs         = 0
    loc_added   = 0
    loc_removed = 0
    cost_cents  = 0
    for r in records:
        m = r.get('core_metrics', {})
        sessions    += m.get('num_sessions', 0)
        commits     += m.get('commits_by_claude_code', 0)
        prs         += m.get('pull_requests_by_claude_code', 0)
        loc_added   += m.get('lines_of_code', {}).get('added', 0)
        loc_removed += m.get('lines_of_code', {}).get('removed', 0)
        for mb in r.get('model_breakdown', []):
            cost_cents += mb.get('estimated_cost', {}).get('amount', 0)
    return {
        'sessions':    sessions,
        'commits':     commits,
        'prs':         prs,
        'loc_added':   loc_added,
        'loc_removed': loc_removed,
        'cost_usd':    cost_cents / 100,
    }


def render(d, date_str):
    c = Canvas()
    W = c.w

    c.text_centered(60,  'Claude Code', font(70, bold=True))
    c.text_centered(155, date_str,      font(45))
    c.divider(220)

    c.text_centered(250, str(d['sessions']), font(260, bold=True))
    c.text_centered(545, 'sessions',         font(55))

    c.divider(635)

    col1, col2, col3 = 130, 540, 950
    y1, y2 = 670, 790

    c.text(col1, y1, str(d['commits']),       font(90, bold=True))
    c.text(col1, y2, 'commits',               font(40))

    c.text(col2, y1, str(d['prs']),           font(90, bold=True))
    c.text(col2, y2, 'pull requests',         font(40))

    c.text(col3, y1, f"${d['cost_usd']:.2f}", font(90, bold=True))
    c.text(col3, y2, 'cost today',            font(40))

    c.column_divider(W // 3,       margin=645)
    c.column_divider((W // 3) * 2, margin=645)

    c.divider(900)

    loc_str = f"+{d['loc_added']:,}  −{d['loc_removed']:,}  lines"
    c.text_centered(930, loc_str, font(50))

    c.img = c.img.transpose(Image.ROTATE_90)
    c.save(TMP)
    show_image(TMP)


_sleep = sleep_watcher()
_tap   = tap_watcher()
while not _sleep.is_set() and not _tap.is_set():
    try:
        date_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        log(f'claude: fetching {date_str}')
        records = fetch(date_str)
        data    = aggregate(records)
        log(f"claude: {data['sessions']} sessions ${data['cost_usd']:.2f}")
        render(data, date_str)
    except Exception as e:
        log(f'claude error: {e}')
    sleep_screen(REFRESH, _sleep, _tap)
