#!/usr/bin/env python3
"""claude_quota — Claude subscription quota utilization card.

Uses the unofficial OAuth usage endpoint (reverse-engineered from ClaudeGod):
  GET https://api.anthropic.com/api/oauth/usage
with the same Bearer token Claude Code writes to ~/.claude/.credentials.json.

Required env vars (payload/local/env.sh or project env):
  CLAUDE_OAUTH_TOKEN   — accessToken from ~/.claude/.credentials.json
  CLAUDE_REFRESH_TOKEN — refreshToken from ~/.claude/.credentials.json (optional)
"""
from __future__ import annotations

import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from lib import Canvas, font, log
from lib.card import Card
from datetime import datetime, timezone
from PIL import Image, ImageFont

USAGE_URL    = 'https://api.anthropic.com/api/oauth/usage'
REFRESH_URL  = 'https://platform.claude.com/v1/oauth/token'
OAUTH_CLIENT = '9d1c250a-e61b-44d9-88ed-5944d1962f5e'
TOKEN_CACHE  = '/tmp/kdash_claude_quota_auth.json'

_SSL_CTX = ssl._create_unverified_context()


# ── Auth helpers ──────────────────────────────────────────────────────────────

def _load_token() -> tuple[str, str]:
    """Return (access_token, refresh_token). Reads session cache first, then env."""
    if os.path.exists(TOKEN_CACHE):
        try:
            d = json.loads(open(TOKEN_CACHE).read())
            at = d.get('access_token', '')
            rt = d.get('refresh_token', os.environ.get('CLAUDE_REFRESH_TOKEN', ''))
            if at:
                return at, rt
        except Exception:
            pass
    return (
        os.environ.get('CLAUDE_OAUTH_TOKEN', ''),
        os.environ.get('CLAUDE_REFRESH_TOKEN', ''),
    )


def _save_token(access_token: str, refresh_token: str, expires_in: int = 3600) -> None:
    try:
        with open(TOKEN_CACHE, 'w') as f:
            json.dump({
                'access_token':  access_token,
                'refresh_token': refresh_token,
                'expires_at':    time.time() + expires_in,
            }, f)
    except Exception:
        pass


def _refresh_access_token(refresh_token: str) -> str:
    """Exchange refresh token for a new access token; updates cache. Returns new token."""
    body = urllib.parse.urlencode({
        'grant_type':    'refresh_token',
        'refresh_token': refresh_token,
        'client_id':     OAUTH_CLIENT,
    }).encode()
    req = urllib.request.Request(REFRESH_URL, data=body)
    req.add_header('Content-Type', 'application/x-www-form-urlencoded')
    req.add_header('User-Agent', 'kdash/1.0')
    with urllib.request.urlopen(req, timeout=15, context=_SSL_CTX) as resp:
        result = json.loads(resp.read())
    new_at = result.get('access_token', '')
    new_rt = result.get('refresh_token', refresh_token)
    _save_token(new_at, new_rt, int(result.get('expires_in', 3600)))
    return new_at


def _get_usage(access_token: str) -> dict:
    req = urllib.request.Request(USAGE_URL)
    req.add_header('Authorization',   f'Bearer {access_token}')
    req.add_header('anthropic-beta',  'oauth-2025-04-20')
    req.add_header('Accept',          'application/json')
    req.add_header('User-Agent',      'kdash/1.0')
    with urllib.request.urlopen(req, timeout=15, context=_SSL_CTX) as resp:
        return json.loads(resp.read())


# ── Render helpers ────────────────────────────────────────────────────────────

_ASSET_DIR  = os.path.join(os.path.dirname(__file__), '..')
_LOGO_PATH  = os.path.join(_ASSET_DIR, 'icons', 'claude.png')
_cfont_cache: dict = {}


def _cfont(size: int, *, serif: bool = False, bold: bool = False,
           italic: bool = False) -> ImageFont.FreeTypeFont:
    """Anthropic brand font from payload/fonts; falls back to DejaVu."""
    key = (size, serif, bold, italic)
    if key in _cfont_cache:
        return _cfont_cache[key]
    if serif:
        name = 'ClaudeSerif-Bold.ttf' if bold else 'ClaudeSerif.ttf'
    else:
        name = 'ClaudeSans-Italic.ttf' if italic else 'ClaudeSans.ttf'
    try:
        f = ImageFont.truetype(os.path.join(_ASSET_DIR, 'fonts', name), size)
    except Exception:
        f = font(size, bold=bold)
    _cfont_cache[key] = f
    return f


def _norm(v: object) -> float:
    """Normalise API utilization to a 0-100 float (API may return 0-1 or 0-100)."""
    if v is None:
        return 0.0
    f = float(v)
    return f * 100.0 if f <= 1.0 else f


def _time_until(iso: str) -> str:
    """'Xd Yh' or 'Xh Ym' until the given ISO-8601 timestamp."""
    try:
        dt    = datetime.fromisoformat(iso.replace('Z', '+00:00'))
        secs  = int((dt - datetime.now(timezone.utc)).total_seconds())
        if secs <= 0:
            return 'now'
        d, r  = divmod(secs, 86400)
        h, r  = divmod(r, 3600)
        m     = r // 60
        return f'{d}d {h}h' if d > 0 else f'{h}h {m}m' if h > 0 else f'{m}m'
    except Exception:
        return '?'


def _ring(c: Canvas, cx: int, cy: int, r: int, thickness: int,
          pct: float, label: str, sublabel: str) -> None:
    """Utilization ring: gray track, black progress arc from 12 o'clock,
    big percentage in the middle, label + reset time below it."""
    bbox = [cx - r, cy - r, cx + r, cy + r]
    c._draw.arc(bbox, 0, 360, fill=210, width=thickness)
    pct = min(max(pct, 0.0), 100.0)
    if pct > 0:
        c._draw.arc(bbox, -90, -90 + 360 * pct / 100, fill=0, width=thickness)

    pct_str  = f'{pct:.0f}%'
    pct_fnt  = _cfont(130, serif=True, bold=True)
    pw, ph   = c.measure(pct_str, pct_fnt)
    c.text(cx - pw // 2, cy - ph - 30, pct_str, pct_fnt)

    lbl_fnt  = _cfont(44)
    lw, _    = c.measure(label, lbl_fnt)
    c.text(cx - lw // 2, cy + 16, label, lbl_fnt)

    if sublabel:
        sub_fnt = _cfont(34)
        sw, _   = c.measure(sublabel, sub_fnt)
        c.text(cx - sw // 2, cy + 76, sublabel, sub_fnt, color=110)


# ── Card ──────────────────────────────────────────────────────────────────────

class ClaudeQuotaCard(Card):
    name            = 'claude_quota'
    default_refresh = 300  # 5 min

    def fetch(self) -> dict:
        at, rt = _load_token()
        if not at:
            raise RuntimeError('CLAUDE_OAUTH_TOKEN not set')
        log('claude_quota: fetching')
        try:
            data = _get_usage(at)
        except urllib.error.HTTPError as e:
            if e.code == 401 and rt:
                log('claude_quota: 401 — refreshing token')
                at   = _refresh_access_token(rt)
                data = _get_usage(at)
            else:
                raise
        fh_pct = _norm(data.get('five_hour', {}).get('utilization'))
        sd_pct = _norm(data.get('seven_day', {}).get('utilization'))
        log(f'claude_quota: 5h={fh_pct:.0f}% 7d={sd_pct:.0f}%')
        return data

    def render(self, data: dict) -> Canvas:
        c = Canvas()

        fh   = data.get('five_hour')        or {}
        sd   = data.get('seven_day')        or {}
        sd_s = data.get('seven_day_sonnet') or {}
        sd_o = data.get('seven_day_opus')   or {}
        eu   = data.get('extra_usage')      or {}

        # ── Header: logo + title ──────────────────────────────────────────────
        title_fnt = _cfont(88, serif=True)
        tw, _     = c.measure('Claude Usage', title_fnt)
        logo_size = 96
        total_w   = logo_size + 36 + tw
        x0        = (c.w - total_w) // 2
        try:
            c.paste_icon(_LOGO_PATH, x0 + logo_size // 2, 110, logo_size)
        except Exception:
            pass
        c.text(x0 + logo_size + 36, 52, 'Claude Usage', title_fnt)

        c.divider(208)

        # ── Rings: 5-hour (left) · 7-day (right) ─────────────────────────────
        fh_pct = _norm(fh.get('utilization'))
        sd_pct = _norm(sd.get('utilization'))

        fh_sub = f'resets in {_time_until(fh["resets_at"])}' if fh.get('resets_at') else ''
        sd_sub = f'resets in {_time_until(sd["resets_at"])}' if sd.get('resets_at') else ''

        ring_y, ring_r, ring_t = 580, 260, 42
        _ring(c, 400,  ring_y, ring_r, ring_t, fh_pct, '5-Hour', fh_sub)
        _ring(c, 1048, ring_y, ring_r, ring_t, sd_pct, '7-Day',  sd_sub)

        # ── Bottom info line ──────────────────────────────────────────────────
        parts = []
        if sd_s.get('utilization') is not None:
            parts.append(f'Sonnet 7d {_norm(sd_s.get("utilization")):.0f}%')
        if sd_o.get('utilization') is not None:
            parts.append(f'Opus 7d {_norm(sd_o.get("utilization")):.0f}%')
        if eu.get('is_enabled'):
            used     = (eu.get('used_credits') or 0) / 100
            currency = eu.get('currency') or 'USD'
            sym      = '€' if currency == 'EUR' else ('£' if currency == 'GBP' else '$')
            extra    = f'extra {sym}{used:.2f}'
            if eu.get('monthly_limit'):
                extra += f' / {sym}{eu["monthly_limit"] / 100:.0f}'
            parts.append(extra)
        parts.append(f'last refreshed {datetime.now().strftime("%H:%M")}')

        info_fnt = _cfont(36, italic=True)
        iw, _    = c.measure('  ·  '.join(parts), info_fnt)
        c.text((c.w - iw) // 2, 980, '  ·  '.join(parts), info_fnt, color=120)

        c.img = c.img.transpose(Image.ROTATE_90)
        return c


if __name__ == '__main__':
    ClaudeQuotaCard().run()
