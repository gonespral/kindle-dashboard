#!/usr/bin/env python3
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from lib import Canvas, font, show_image, prevent_screensaver, sleep_screen, sleep_watcher, fetch_json, log
from datetime import datetime, timezone
from PIL import Image

ADMIN_KEY = os.environ.get('ANTHROPIC_ADMIN_API_KEY', '')
API_KEY   = os.environ.get('ANTHROPIC_API_KEY', '')
REFRESH   = int(os.environ.get('REFRESH_INTERVAL', '600'))
TMP       = '/tmp/kdash_claude.png'

USAGE_URL  = 'https://api.anthropic.com/v1/organizations/usage_report/claude_code'
TOKENS_URL = 'https://api.anthropic.com/v1/messages/count_tokens'


def fetch_usage(date_str):
    if not ADMIN_KEY:
        raise RuntimeError('ANTHROPIC_ADMIN_API_KEY not set')
    url = f'{USAGE_URL}?starting_at={date_str}&limit=1000'
    data = fetch_json(url, headers={
        'X-Api-Key': ADMIN_KEY,
        'anthropic-version': '2023-06-01',
    })
    return data.get('data', [])


def fetch_rate_limits():
    """Returns dict with five_hour/seven_day pct (0-100) or empty dict if unavailable."""
    if not API_KEY:
        return {}
    try:
        _, hdrs = fetch_json_with_headers(
            TOKENS_URL,
            headers={
                'X-Api-Key': API_KEY,
                'anthropic-version': '2023-06-01',
            },
            body={
                'model': 'claude-haiku-4-5-20251001',
                'messages': [{'role': 'user', 'content': 'hi'}],
            },
        )
        result = {}
        five = hdrs.get('anthropic-ratelimit-unified-5h-utilization')
        seven = hdrs.get('anthropic-ratelimit-unified-7d-utilization')
        if five is not None:
            result['five_hour'] = float(five) * 100
        if seven is not None:
            result['seven_day'] = float(seven) * 100
        return result
    except Exception as e:
        log(f'rate limits: {e}')
        return {}


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


def _bar(c, x, y, w, h, pct, label):
    """Draw a labeled progress bar. pct is 0-100."""
    c.rect(x, y, w, h, fill=None, outline=0, width=2)
    fill_w = max(0, int(w * min(pct, 100) / 100)) - 4
    if fill_w > 0:
        c.rect(x + 2, y + 2, fill_w, h - 4, fill=0, outline=None)
    pct_str = f'{pct:.0f}%'
    c.text(x + w + 20, y + (h - 40) // 2, pct_str, font(40))
    c.text(x, y + h + 10, label, font(36))


def render(d, date_str, rl):
    c = Canvas()
    W = c.w

    # Header
    c.text_centered(60,  'Claude Code', font(70, bold=True))
    c.text_centered(155, date_str,      font(45))
    c.divider(220)

    if rl:
        # Compact sessions row when rate limits are shown
        c.text_centered(260, str(d['sessions']), font(200, bold=True))
        c.text_centered(490, 'sessions',         font(50))
        c.divider(560)

        # Rate limits
        bar_y = 590
        bar_h = 55
        bar_w = 520
        margin = 100
        if 'five_hour' in rl:
            _bar(c, margin, bar_y, bar_w, bar_h, rl['five_hour'], '5-hour session')
        if 'seven_day' in rl:
            col2_x = W // 2 + margin // 2
            _bar(c, col2_x, bar_y, bar_w, bar_h, rl['seven_day'], '7-day weekly')
        c.divider(700)
        y_metrics = 730
    else:
        # Big sessions number
        c.text_centered(250, str(d['sessions']), font(260, bold=True))
        c.text_centered(545, 'sessions',         font(55))
        c.divider(635)
        y_metrics = 670

    # Metrics row
    col1, col2, col3 = 130, 540, 950
    y1 = y_metrics
    y2 = y_metrics + 120

    c.text(col1, y1, str(d['commits']),       font(90, bold=True))
    c.text(col1, y2, 'commits',               font(40))

    c.text(col2, y1, str(d['prs']),           font(90, bold=True))
    c.text(col2, y2, 'pull requests',         font(40))

    c.text(col3, y1, f"${d['cost_usd']:.2f}", font(90, bold=True))
    c.text(col3, y2, 'cost today',            font(40))

    c.column_divider(W // 3,       margin=y_metrics - 25)
    c.column_divider((W // 3) * 2, margin=y_metrics - 25)

    c.divider(y_metrics + 240)

    # Lines of code
    loc_str = f"+{d['loc_added']:,}  −{d['loc_removed']:,}  lines"
    c.text_centered(y_metrics + 270, loc_str, font(50))

    c.img = c.img.transpose(Image.ROTATE_90)
    c.save(TMP)
    show_image(TMP)


_stop = sleep_watcher()
while not _stop.is_set():
    prevent_screensaver()
    try:
        date_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        log(f'claude: fetching {date_str}')
        records  = fetch_usage(date_str)
        data     = aggregate(records)
        log(f"claude: {data['sessions']} sessions ${data['cost_usd']:.2f}")
        rl = fetch_rate_limits()
        if rl:
            log(f"rate limits: 5h={rl.get('five_hour', '?'):.0f}% 7d={rl.get('seven_day', '?'):.0f}%")
        render(data, date_str, rl)
    except Exception as e:
        log(f'claude error: {e}')
    if not _stop.is_set():
        sleep_screen(REFRESH)
prevent_screensaver(False)
