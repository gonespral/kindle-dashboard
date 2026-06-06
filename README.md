# kdash

Kindle e-ink dashboard. Scripts run directly on the Kindle no server needed.

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

1. Edit `sync.conf`:
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

| Entry | Description |
|---|---|
| App: Clock | Large centered clock (Python + PIL) |
| App: Weather | Current weather via wttr.in |
| Stop | Kill all running cards, clear screen |
| Show IP | Display Kindle's IP address |
| Test Python | Show Python and PIL version on screen |
| Reverse Shell | Open a shell session back to your PC |

## Adding a card

1. Create `scripts/cards/mycard.py` (use `clock.py` as a template)
2. Add entry to `scripts/menu.json`:
   ```json
   {"name": "App: My Card", "priority": 48, "action": "/bin/sh ./launch.sh cards/mycard.py"}
   ```
3. Run `./sync.sh`

## Remote shell (instead of SSH)

SSH setup on Kindle is unreliable. The reverse shell is simpler — the Kindle connects out to your PC.

**Setup:** set `SHELL_HOST` and `SHELL_PORT` in `sync.conf`, then sync.

**Usage:**

1. On your PC, listen for the connection:
   ```sh
   stty raw -echo; nc -lvp 4568; stty sane
   ```
2. On Kindle: KUAL → kdash → Reverse Shell
3. The Kindle connects back — you get a full interactive shell

The script retries twice (5s apart) if the connection fails. Make sure your PC is listening before tapping the menu entry. `stty sane` restores your terminal after you disconnect.
