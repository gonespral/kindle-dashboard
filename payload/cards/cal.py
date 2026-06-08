#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from lib import Canvas, font, log, fetch_url
from lib.card import Card
from PIL import Image

WEATHER_CITY  = os.environ.get('WEATHER_CITY', 'Delft')

# Collect all configured iCal URLs.
# Supports ICAL_URL (single) or ICAL_URL_1 … ICAL_URL_N (multi).
def _collect_urls() -> list[str]:
    urls = []
    if os.environ.get('ICAL_URL'):
        urls.append(os.environ['ICAL_URL'])
    for i in range(1, 10):
        u = os.environ.get(f'ICAL_URL_{i}')
        if u:
            urls.append(u)
    return urls

GCAL_ICAL_URLS = _collect_urls()

ICONS_DIR = os.path.join(os.path.dirname(__file__), '..', 'icons')

LEFT_W    = 500
DIVIDER_X = 518
RIGHT_X   = 536
PAD       = 20


# ── iCal fetch + parse ────────────────────────────────────────────────────────

def _fetch_ical(url: str) -> str:
    return fetch_url(url, timeout=10, retries=1)


def _parse_ical(text: str) -> list[dict]:
    """Return list of VEVENT property dicts. Each value is (str, params_dict)."""
    # Unfold RFC 5545 folded lines (CRLF + space/tab = continuation)
    text = re.sub(r'\r?\n[ \t]', '', text)

    events: list[dict] = []
    props:  dict       = {}
    in_ev  = False

    for line in text.splitlines():
        line = line.rstrip('\r')
        if line == 'BEGIN:VEVENT':
            in_ev = True
            props = {}
        elif line == 'END:VEVENT':
            in_ev = False
            events.append(props)
        elif in_ev and ':' in line:
            key_part, _, value = line.partition(':')
            name = key_part.split(';')[0].upper()
            params: dict[str, str] = {}
            for seg in key_part.split(';')[1:]:
                if '=' in seg:
                    pk, pv = seg.split('=', 1)
                    params[pk.upper()] = pv
            props[name] = (value, params)

    return events


def _unescape(s: str) -> str:
    return (s.replace('\\n', ' ').replace('\\N', ' ')
             .replace('\\,', ',').replace('\\;', ';')
             .replace('\\\\', '\\'))


def _parse_dt(value: str, params: dict) -> tuple[datetime, bool]:
    """Return (datetime, is_all_day). Timed datetimes are converted to local tz."""
    if params.get('VALUE') == 'DATE' or (len(value) == 8 and 'T' not in value):
        return datetime.strptime(value, '%Y%m%d'), True

    if value.endswith('Z'):
        dt = datetime.strptime(value, '%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc)
        return dt.astimezone(), False

    tzid = params.get('TZID')
    if tzid:
        try:
            from zoneinfo import ZoneInfo
            dt = datetime.strptime(value, '%Y%m%dT%H%M%S').replace(tzinfo=ZoneInfo(tzid))
            return dt.astimezone(), False
        except Exception:
            pass

    return datetime.strptime(value, '%Y%m%dT%H%M%S'), False


_DAYS = {'MO': 0, 'TU': 1, 'WE': 2, 'TH': 3, 'FR': 4, 'SA': 5, 'SU': 6}


def _expand_rrule(ev: dict, window_start: date, window_end: date) -> list[dict]:
    """Expand a recurring RRULE event into individual instances within the window."""
    try:
        start_dt, allday = _parse_dt(*ev['DTSTART'])
    except Exception:
        return []

    start_date = start_dt.date()
    rule   = dict(p.split('=', 1) for p in ev['RRULE'][0].split(';') if '=' in p)
    freq   = rule.get('FREQ', '')
    step   = max(1, int(rule.get('INTERVAL', 1)))
    byday  = [_DAYS[d[:2]] for d in rule.get('BYDAY', '').split(',') if d[:2] in _DAYS]

    until: date | None = None
    if 'UNTIL' in rule:
        try:
            until = datetime.strptime(rule['UNTIL'].rstrip('Z')[:8], '%Y%m%d').date()
        except Exception:
            pass

    exdates: set[date] = set()
    if 'EXDATE' in ev:
        for val in ev['EXDATE'][0].split(','):
            try:
                exdates.add(datetime.strptime(val.rstrip('Z')[:8], '%Y%m%d').date())
            except Exception:
                pass

    orig_value, orig_params = ev['DTSTART']
    time_suffix = orig_value[8:] if not allday else ''  # e.g. 'T090000' or 'T090000Z'

    results = []
    for i in range((window_end - window_start).days + 1):
        d = window_start + timedelta(days=i)
        if d < start_date:
            continue
        if until and d > until:
            continue
        if d in exdates:
            continue

        if freq == 'WEEKLY':
            if byday:
                if d.weekday() not in byday:
                    continue
                start_mon = start_date - timedelta(days=start_date.weekday())
                d_mon     = d - timedelta(days=d.weekday())
                occurs    = ((d_mon - start_mon).days // 7) % step == 0
            else:
                occurs = (d - start_date).days % (step * 7) == 0
        elif freq == 'DAILY':
            occurs = (d - start_date).days % step == 0
        else:
            continue  # MONTHLY/YEARLY: rare, skip

        if occurs:
            inst = dict(ev)
            inst['DTSTART'] = (
                (d.strftime('%Y%m%d'), {'VALUE': 'DATE'}) if allday
                else (d.strftime('%Y%m%d') + time_suffix, orig_params)
            )
            results.append(inst)

    return results


def _group_events(raw: list[dict], today: date) -> dict[str, list[dict]]:
    window_end = today + timedelta(days=2)  # inclusive: today, +1, +2
    groups: dict[str, list[dict]] = {}

    for ev in raw:
        if 'DTSTART' not in ev:
            continue

        instances = _expand_rrule(ev, today, window_end) if 'RRULE' in ev else [ev]

        for inst in instances:
            try:
                dt, allday = _parse_dt(*inst['DTSTART'])
            except Exception:
                continue

            ev_date = dt.date()
            if not (today <= ev_date <= window_end):
                continue

            day_key = ev_date.strftime('%Y-%m-%d')
            summary_raw = inst.get('SUMMARY', ('', {}))[0]
            groups.setdefault(day_key, []).append({
                'summary': _unescape(summary_raw) or '(no title)',
                '_time':   '' if allday else dt.strftime('%H:%M'),
                '_allday': allday,
                '_sort':   (0 if allday else 1, '' if allday else dt.strftime('%H:%M')),
            })

    for day in groups:
        groups[day].sort(key=lambda e: e['_sort'])

    return groups


# ── Weather (mini) ────────────────────────────────────────────────────────────

def _fetch_weather() -> dict:
    try:
        url = f'http://wttr.in/{urllib.parse.quote(WEATHER_CITY)}?format=j1'
        ctx = ssl._create_unverified_context()
        req = urllib.request.Request(url, headers={'User-Agent': 'kdash/1.0'})
        with urllib.request.urlopen(req, timeout=5, context=ctx) as resp:
            d = json.loads(resp.read())
        cur = d['current_condition'][0]
        return {
            'temp': cur['temp_C'] + '°',
            'desc': cur['weatherDesc'][0]['value'],
            'code': int(cur['weatherCode']),
        }
    except Exception as e:
        log(f'gcal: weather error: {e}')
        return {'temp': '--°', 'desc': '', 'code': 0}


def _weather_icon(code: int) -> str:
    if code == 113: return 'sunny'
    if code == 116: return 'partly_cloudy_day'
    if code in (119, 122): return 'cloudy'
    if code in (200, 386, 389, 392, 395): return 'thunderstorm'
    if code in (179, 323, 326, 329, 332, 335, 338, 368, 371): return 'weather_snowy'
    if code in (263, 266): return 'grain'
    if code in (305, 308, 356): return 'water_drop'
    return 'rainy'


# ── Helpers ───────────────────────────────────────────────────────────────────

def _truncate(c: Canvas, text: str, fnt, max_w: int) -> str:
    tw, _ = c.measure(text, fnt)
    if tw <= max_w:
        return text
    while text:
        text = text[:-1]
        tw, _ = c.measure(text + '…', fnt)
        if tw <= max_w:
            break
    return text + '…'


# ── Card ──────────────────────────────────────────────────────────────────────

class GCalCard(Card):
    name = 'cal'
    default_refresh = 60  # network refresh interval (seconds)
    sync_to_minute = True

    def __init__(self):
        super().__init__()
        self._last_net_fetch: float = 0.0
        self._raw_events:     list  = []
        self._cached_weather: dict  = {'temp': '--°', 'desc': '', 'code': 0}
        self._fetch_error:    str   = ''

    def fetch(self) -> dict:
        now = datetime.now()

        if time.time() - self._last_net_fetch >= self.refresh:
            log('cal: fetching network data...')
            self._cached_weather = _fetch_weather()
            self._fetch_error    = ''

            if not GCAL_ICAL_URLS:
                self._fetch_error = 'No ICAL_URL set in env'
                log(f'cal: {self._fetch_error}')
            else:
                errors: list[str] = []
                all_events: list[dict] = []
                for i, url in enumerate(GCAL_ICAL_URLS, 1):
                    log(f'cal: fetching calendar {i}/{len(GCAL_ICAL_URLS)}...')
                    try:
                        evs = _parse_ical(_fetch_ical(url))
                        log(f'cal: calendar {i}: {len(evs)} events parsed')
                        all_events.extend(evs)
                    except Exception as e:
                        errors.append(f'Cal {i}: {e}')
                        log(f'cal: fetch error: {errors[-1]}')
                self._fetch_error = '; '.join(errors)
                # Only replace cached events when all fetches succeeded —
                # on partial/full failure keep the last good data.
                if not errors:
                    self._raw_events = all_events
                elif not self._raw_events:
                    self._raw_events = all_events  # nothing cached yet, use what we have
            self._last_net_fetch = time.time()

        # Re-group every minute (cheap; handles midnight date rollover)
        groups = _group_events(self._raw_events, now.date())
        total  = sum(len(v) for v in groups.values())
        log(f'cal: {total} events in next 3 days')

        return {
            'weather': self._cached_weather,
            'groups':  groups,
            'error':   self._fetch_error,
            'now':     now.isoformat(),
        }

    def render(self, data: dict) -> Canvas:
        c   = Canvas()
        now = datetime.now()
        self._draw_left(c, now, data['weather'])
        c.column_divider(DIVIDER_X, margin=40)
        self._draw_right(c, now, data['groups'], data.get('error', ''))
        c.img = c.img.transpose(Image.ROTATE_90)
        return c

    # ── Left panel: clock + mini weather ─────────────────────────────────────

    def _draw_left(self, c: Canvas, now: datetime, weather: dict) -> None:
        # Time
        time_str = now.strftime('%H:%M')
        fnt_time = font(150, bold=True)
        tw, _ = c.measure(time_str, fnt_time)
        c.text((LEFT_W - tw) // 2, 30, time_str, fnt_time)

        # Day name + date
        fnt_day  = font(52, bold=True)
        fnt_date = font(46)
        day_str  = now.strftime('%A').upper()
        date_str = now.strftime('%-d %B').upper()
        dw, _ = c.measure(day_str, fnt_day)
        c.text((LEFT_W - dw) // 2, 215, day_str, fnt_day)
        dtw, _ = c.measure(date_str, fnt_date)
        c.text((LEFT_W - dtw) // 2, 280, date_str, fnt_date)

        # Divider above weather
        c.hline(810, 30, LEFT_W - 30, color=160, width=2)

        # Weather icon + temp
        icon_name = _weather_icon(weather['code'])
        icon_path = os.path.join(ICONS_DIR, f'{icon_name}.png')
        icon_sz   = 88
        fnt_temp  = font(95, bold=True)
        temp_str  = weather['temp']
        tw, _     = c.measure(temp_str, fnt_temp)
        block_w   = icon_sz + 14 + tw
        bx        = (LEFT_W - block_w) // 2
        icon_cy   = 878

        if os.path.exists(icon_path):
            c.paste_icon(icon_path, cx=bx + icon_sz // 2, cy=icon_cy, size=icon_sz)
        c.text(bx + icon_sz + 14, icon_cy - 47, temp_str, fnt_temp)

        # Description + city
        fnt_desc = font(40)
        desc = _truncate(c, weather['desc'], fnt_desc, LEFT_W - 40)
        dw, _ = c.measure(desc, fnt_desc)
        c.text((LEFT_W - dw) // 2, 948, desc, fnt_desc, color=90)

        fnt_city = font(36)
        cw, _ = c.measure(WEATHER_CITY, fnt_city)
        c.text((LEFT_W - cw) // 2, 1002, WEATHER_CITY, fnt_city, color=150)

    # ── Right panel: 3-day calendar ───────────────────────────────────────────

    def _draw_right(self, c: Canvas, now: datetime, groups: dict, error: str = '') -> None:
        if error:
            fnt_err = font(38)
            err_str = _truncate(c, f'Error: {error}', fnt_err, 1440 - RIGHT_X - PAD * 2)
            c.text(RIGHT_X + PAD, 20, err_str, fnt_err, color=80)

        section_h = 1072 // 3
        for i in range(3):
            day_dt  = now + timedelta(days=i)
            day_key = day_dt.strftime('%Y-%m-%d')
            self._draw_day(c, day_key, day_dt, now, groups.get(day_key, []),
                           y=i * section_h, section_h=section_h)

    def _draw_day(self, c: Canvas, day_key: str, day_dt: datetime, now: datetime,
                  events: list[dict], y: int, section_h: int) -> None:
        today    = now.strftime('%Y-%m-%d')
        tomorrow = (now + timedelta(days=1)).strftime('%Y-%m-%d')

        if day_key == today:
            label = 'TODAY'
        elif day_key == tomorrow:
            label = 'TOMORROW'
        else:
            label = day_dt.strftime('%A').upper()

        fnt_hdr      = font(44, bold=True)
        fnt_hdr_date = font(36)

        c.text(RIGHT_X + PAD, y + 8, label, fnt_hdr)
        c.text_right(1440, y + 12, day_dt.strftime('%-d %b').upper(), fnt_hdr_date, color=120)
        c.hline(y + 60, RIGHT_X + PAD, 1440, color=70, width=2)

        fnt_time   = font(37, bold=True)
        fnt_title  = font(40)
        fnt_allday = font(36)
        fnt_empty  = font(37)

        ev_y  = y + 74
        max_y = y + section_h - 18

        if not events:
            c.text(RIGHT_X + PAD + 10, ev_y, 'No events', fnt_empty, color=170)
        else:
            for ev in events:
                if ev_y + 44 > max_y:
                    break
                title  = ev['summary']
                allday = ev['_allday']

                if allday:
                    c.text(RIGHT_X + PAD + 10, ev_y + 2, '·', fnt_allday, color=130)
                    max_w = 1440 - RIGHT_X - PAD * 2 - 26
                    c.text(RIGHT_X + PAD + 28, ev_y + 2,
                           _truncate(c, title, fnt_allday, max_w), fnt_allday, color=80)
                    ev_y += 48
                else:
                    t_str = ev['_time']
                    tw, _ = c.measure(t_str, fnt_time)
                    c.text(RIGHT_X + PAD + 10, ev_y, t_str, fnt_time)
                    x_title = RIGHT_X + PAD + 10 + tw + 14
                    max_w   = 1440 - x_title - PAD
                    c.text(x_title, ev_y, _truncate(c, title, fnt_title, max_w), fnt_title)
                    ev_y += 52

        if y + section_h < 1060:
            c.hline(y + section_h - 2, RIGHT_X + PAD, 1440, color=190, width=1)


if __name__ == '__main__':
    GCalCard().run()
