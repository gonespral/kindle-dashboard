# kdash

Kindle e-ink dashboard. Scripts run directly on the Kindle.

## Requirements

- Jailbroken Kindle with KUAL + MRPI
- Python 3.9.8 + PIL 9.0.0 installed on the Kindle (via MRPI)

## Jailbreak

- Firmware < 5.18.1: https://kindlemodding.org/jailbreaking/WinterBreak/
- Firmware 5.18.1+: https://kindlemodding.org/jailbreaking/AdBreak/

## KUAL + MRPI

Download: https://www.mobileread.com/forums/showthread.php?t=225030

1. Copy `Update_KUALmrInstaller_*.bin` to Kindle root
2. On Kindle: search → `;log mrpi` → Enter (screen flashes)
3. Copy KUAL `.bin` to Kindle root, run `;log mrpi` again
4. KUAL appears as a book in your library

## Python + PIL

Download from: https://www.mobileread.com/forums/showthread.php?t=195474

1. Copy `Update_python_*.bin` to Kindle root, run `;log mrpi`
2. Copy `Update_PIL_*.bin` (or Pillow) to Kindle root, run `;log mrpi`
3. Reboot

Confirmed working: **Python 3.9.8**, **PIL 9.0.0**

## Sync to Kindle

1. Copy `env.example` to `env` and edit:
   ```sh
   SHELL_HOST=192.168.x.x   # your PC's IP
   SHELL_PORT=4568
   # REFRESH_INTERVAL=600   # optional global override; unset = per-card defaults
   # KINDLE_MOUNT=/run/media/youruser/Kindle1
   ```
2. Connect Kindle via USB
3. Run:
   ```sh
   ./sync.sh
   ```

## Cards

Launch from KUAL -> **kdash**:

| Entry | Refresh | Description |
|---|---|---|
| Clock | 1 min | Large centered clock with date and week number |
| World Clocks | 1 min | Local time plus four configurable time zones |
| Weather | 1 hr | Current weather via wttr.in (city from `WEATHER_CITY`) |
| Claude Usage | 10 min | Claude Code session/commit/cost stats for today |
| Buienradar | 10 min | Dutch rain radar map + 2-hour forecast chart |
| Claude Quota | 5 min | Claude subscription quota: 5-hour + 7-day utilization rings |
| Calendar | 1 min | Agenda from one or more iCal feeds (`ICAL_URL*`) |
| Stop | - | Kill all running cards, clear screen |
| Tools → Sleep Test | - | Test sleep/wake event handling |
| Tools → Show IP | - | Display Kindle's IP address |
| Tools → Test Python | - | Show Python and PIL version on screen |
| Tools → Test Touch | - | Show touch events on screen |
| Tools → Rev Shell | - | Open a shell session back to your PC |

### Card behaviour

Each card runs a loop: **fetch -> render -> sleep -> repeat**. During the sleep it stays alive and responsive; a power button press or a screen tap exits cleanly. Each card has its own default refresh interval (see table above); setting `REFRESH_INTERVAL` in `env` overrides it globally for all cards.

If battery drops to 25% or below, a small battery indicator is drawn in the corner of whichever card is displayed.

## Adding a card

1. Create `payload/cards/mycard.py` subclassing `Card`:

   ```python
   #!/usr/bin/env python3
   import os, sys
   sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

   from lib import Canvas, font, log
   from lib.card import Card
   from PIL import Image

   class MyCard(Card):
       name = 'mycard'
       default_refresh = 300  # seconds

       def fetch(self) -> dict:
           # fetch data from API, files, etc.
           return {'value': 42}

       def render(self, data: dict) -> Canvas:
           c = Canvas()
           c.text_centered(500, str(data['value']), font(200, bold=True))
           c.img = c.img.transpose(Image.ROTATE_90)
           return c  # base class saves, overlays battery icon, and calls show_image()

   if __name__ == '__main__':
       MyCard().run()
   ```

2. Add entry to `payload/menu.json`:
   ```json
   {"name": "My Card", "priority": 48, "action": "/bin/sh ./tools/stop.sh; /bin/sh ./tools/launch.sh ./cards/mycard.py"}
   ```

3. Add the card name to the kill list in `payload/tools/stop.sh`:
   ```sh
   for name in clock worldclocks weather buienradar claude claude_quota cal sleep_test mycard; do
   ```

4. Run `./sync.sh`

## Environment variables

All secrets and per-device config live in the `env` file at the repo root. `sync.sh` copies it to `payload/local/env.sh` on the Kindle, where it is sourced by `launch.sh` before starting any card.

| Variable | Card | How to get it |
|---|---|---|
| `ANTHROPIC_ADMIN_API_KEY` | Claude Usage | Anthropic Console → API Keys (needs `usage_report:read` scope) |
| `CLAUDE_OAUTH_TOKEN` | Claude Quota | `~/.claude/.credentials.json` → `claudeAiOauth.accessToken` |
| `CLAUDE_REFRESH_TOKEN` | Claude Quota | `~/.claude/.credentials.json` → `claudeAiOauth.refreshToken` |
| `WEATHER_CITY` | Weather | Any city name (default: `Delft`) |
| `BUIENALARM_POSTCODE` | Buienradar | Dutch postcode |
| `WORLD_CLOCK_TZ1..4` / `WORLD_CLOCK_CITY1..4` | World Clocks | IANA time zone names + optional display labels |
| `ICAL_URL`, `ICAL_URL_1..4` | Calendar | iCal feed URLs (e.g. Google Calendar secret address) |
| `REFRESH_INTERVAL` | all | Optional global refresh override in seconds; unset = per-card defaults |
| `KDASH_DEBUG` | all | Set to `false` to hide on-screen log lines (default `true`) |
| `SHELL_HOST` / `SHELL_PORT` | Reverse Shell | Your PC's IP and listening port |

### Setting up Claude Quota

The Claude Quota card uses the same OAuth token that Claude Code manages automatically. Copy the values from your local credentials file:

```sh
python3 -c "
import json
d = json.load(open('$HOME/.claude/.credentials.json'))
o = d['claudeAiOauth']
print('CLAUDE_OAUTH_TOKEN=' + o['accessToken'])
print('CLAUDE_REFRESH_TOKEN=' + o['refreshToken'])
"
```

Paste both lines into `env`. The access token only lasts a few hours, which is fine: when it expires the card auto-refreshes it using the refresh token and caches the new one in `/tmp/kdash_claude_quota_auth.json` until the next Kindle reboot.

## Fonts

The Claude Quota card renders with Anthropic's brand fonts (Anthropic Serif for the title and percentages, Anthropic Sans for labels). These are proprietary fonts, so they are not committed to this repo; instead each user fetches them from Anthropic's public CDN for their own device:

```sh
pixi install        # or: pip install fonttools brotli
./fetch_fonts.sh
./sync.sh
```

The script downloads the variable webfonts and pins them to static TTFs in `payload/fonts/` (the Kindle's PIL cannot select variable font instances). If the fonts are missing, the card falls back to the bundled DejaVu.

## Remote shell

SSH setup on Kindle is unreliable. The reverse shell is simpler: the Kindle connects out to your PC.

**Setup:** set `SHELL_HOST` and `SHELL_PORT` in `env`, then sync.

**Usage:**

1. On your PC, listen for the connection:
   ```sh
   stty raw -echo; nc -lvp 4568; stty sane
   ```
2. On Kindle: KUAL → kdash → Reverse Shell
3. The Kindle connects back and you get a full interactive shell

The script retries twice (5s apart) if the connection fails. Make sure your PC is listening before tapping the menu entry. `stty sane` restores your terminal after you disconnect.
