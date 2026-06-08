# kdash — AI Agent Guide

A self-hosted Kindle e-ink dashboard. Cards run as Python scripts directly on the Kindle using PIL for rendering and `eips` for display. No server required.

## Architecture

**Kindle payload** (`/payload`): KUAL menu extension for jailbroken Kindle
- Cards are Python scripts in `payload/cards/`, each subclassing `Card` from `payload/lib/card.py`
- Shared library in `payload/lib/` — eips wrappers, Canvas, network helpers, Card base class
- Menu defined in `payload/menu.json`
- Launched via `payload/tools/launch.sh` (handles Python discovery, env loading, process detachment)

## Key Files

| File | Purpose |
|------|---------|
| `payload/lib/card.py` | `Card` base class — fetch/render loop, sleep, signal handling, battery overlay |
| `payload/lib/common.py` | eips helpers, `Canvas`, `sleep_watcher`, `tap_watcher`, `sleep_screen`, `fetch_json`, `font` |
| `payload/lib/__init__.py` | Re-exports everything from `lib.common` and `lib.card` |
| `payload/cards/clock.py` | Clock card (2 min refresh) |
| `payload/cards/weather.py` | Weather card via wttr.in (1 hr refresh) |
| `payload/cards/buienradar.py` | Dutch rain radar + forecast (10 min refresh) |
| `payload/cards/claude_usage.py` | Claude Code usage stats (10 min refresh) |
| `payload/menu.json` | KUAL menu — maps entries to launch commands |
| `payload/tools/launch.sh` | Smart launcher: finds Python, loads env, detaches from KUAL via setsid |
| `payload/tools/stop.sh` | Kills all running cards by PID file, then pkill fallback |

## Card Lifecycle

Each card subclasses `Card` and implements two methods:

```python
class MyCard(Card):
    name = 'mycard'
    default_refresh = 300  # seconds; overridden by REFRESH_INTERVAL env var

    def fetch(self) -> dict:
        return {...}  # fetch data from APIs, system, etc.

    def render(self, data: dict) -> Canvas:
        c = Canvas()
        # draw on c using c.text(), c.rect(), etc.
        c.img = c.img.transpose(Image.ROTATE_90)  # landscape rotation
        return c  # do NOT call show_image() — base class handles it

if __name__ == '__main__':
    MyCard().run()
```

`Card.run()` loop:
1. Writes PID to `/tmp/kdash_{name}.pid`; installs SIGTERM/SIGINT handlers
2. Starts `sleep_watcher()` (fires on power button / going to sleep) and `tap_watcher()` (fires on first screen tap)
3. Loops: `fetch()` → if data changed: `render()` → apply battery overlay if ≤25% → `show_image()`
4. Sleeps `refresh` seconds (wakes early on power button, tap, or SIGTERM)
5. Logs exit reason to screen on stop; removes PID file

**Override `data_changed(old, new)`** when the fetch dict contains non-comparable values (e.g. PIL Images). Default is `old != new`.

**Set `use_prevent_screensaver = True`** on cards with long fetches (e.g. buienradar) to keep the Kindle awake during the network phase.

## Adding an On-Device Card

1. Create `payload/cards/mycard.py` (see Card Lifecycle above)
2. Add to `payload/menu.json`:
   ```json
   {"name": "App: My Card", "priority": 48, "action": "/bin/sh ./stop.sh; /bin/sh ./tools/launch.sh cards/mycard.py"}
   ```
3. Add `mycard` to the name list in `payload/tools/stop.sh`
4. Run `./sync.sh`

## Conventions

- **Canvas size**: 1448×1072 pixels, grayscale (8-bit), white background
- **Rotation**: all cards rotate the canvas 90° before returning (`c.img = c.img.transpose(Image.ROTATE_90)`) — the Kindle displays in landscape
- **render() returns Canvas**: do not call `show_image()` inside `render()`; the base class calls `_display()` which adds the battery overlay then saves and shows
- **Fonts**: DejaVu via `font(size, bold=False)` helper — searches bundled `payload/fonts/`, Kindle system paths, then `fc-match` fallback
- **Type annotations**: use `from __future__ import annotations` for compatibility with Kindle's Python 3.9
- **No third-party libs**: stdlib + PIL only

## Process Management

- Each running card writes `/tmp/kdash_{name}.pid`
- `stop.sh` kills by PID file for each known card name, then falls back to `pkill -f '/cards/'`
- SIGTERM is caught by the card's signal handler — exits cleanly after the current fetch completes
- Power button fires `com.lab126.powerd goingToSleep` lipc event → `sleep_watcher()` event set → loop exits with log message

## Environment Variables (`payload/local/env.sh`)

| Variable | Used by | Default |
|---|---|---|
| `REFRESH_INTERVAL` | all cards | per-card default |
| `WEATHER_CITY` | weather | `Delft` |
| `BUIENALARM_POSTCODE` | buienradar | — |
| `BUIENALARM_LAT` / `_LON` | buienradar | geocoded from postcode |
| `ANTHROPIC_ADMIN_API_KEY` | claude_usage | — |
| `SHELL_HOST` / `SHELL_PORT` | revshell | — |

## Testing

1. **Import smoke test**: `cd payload && python3 -c "from lib.card import Card; print('ok')"`
2. **Card dry-run on host**: `cd payload && python3 cards/clock.py` — renders PNG, opens with `xdg-open` (eips calls print instead of running)
3. **SIGTERM test**: `python3 cards/clock.py & sleep 2; kill $!` — PID file should be gone after exit
4. **On Kindle**: launch via KUAL, check `/tmp/kdash_launch.log` if card doesn't appear
