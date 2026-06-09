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

1. Edit `env`:
   ```sh
   REFRESH_INTERVAL=120
   SHELL_HOST=192.168.x.x   # your PC's IP
   SHELL_PORT=4568
   # KINDLE_MOUNT=/run/media/youruser/Kindle1
   ```
2. Connect Kindle via USB
3. Run:
   ```sh
   ./sync.sh
   ```

## Cards

Launch from KUAL → **kdash**:

| Entry | Refresh | Description |
|---|---|---|
| App: Clock | 2 min | Large centered clock with date and week number |
| App: Weather | 1 hr | Current weather via wttr.in (city from `WEATHER_CITY`) |
| App: Buienradar | 10 min | Dutch rain radar map + 2-hour forecast chart |
| App: Claude Usage | 10 min | Claude Code session/commit/cost stats for today |
| Stop | — | Kill all running cards, clear screen |
| Show IP | — | Display Kindle's IP address |
| Test Python | — | Show Python and PIL version on screen |
| Reverse Shell | — | Open a shell session back to your PC |

### Card behaviour

Each card runs a loop: **fetch → render → sleep → repeat**. During the sleep it stays alive and responsive. Power button press or a screen tap exits cleanly. The refresh interval can be overridden globally with `REFRESH_INTERVAL` in `env`.

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
   {"name": "App: My Card", "priority": 48, "action": "/bin/sh ./stop.sh; /bin/sh ./tools/launch.sh cards/mycard.py"}
   ```

3. Add the card name to the kill list in `payload/tools/stop.sh`:
   ```sh
   for name in clock weather buienradar claude mycard; do
   ```

4. Run `./sync.sh`

## Remote shell (instead of SSH)

SSH setup on Kindle is unreliable. The reverse shell is simpler as the Kindle connects out to your PC.

**Setup:** set `SHELL_HOST` and `SHELL_PORT` in `env`, then sync.

**Usage:**

1. On your PC, listen for the connection:
   ```sh
   stty raw -echo; nc -lvp 4568; stty sane
   ```
2. On Kindle: KUAL → kdash → Reverse Shell
3. The Kindle connects back you get a full interactive shell

The script retries twice (5s apart) if the connection fails. Make sure your PC is listening before tapping the menu entry. `stty sane` restores your terminal after you disconnect.
