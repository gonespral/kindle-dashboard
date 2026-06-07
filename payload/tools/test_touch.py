#!/usr/bin/env python3
"""Touch event tester — enumerates ALL input devices and shows raw events.

Usage:
    python3 tools/test_touch.py          # auto-detect + monitor all candidates
    python3 tools/test_touch.py event1   # monitor specific device (by name)

Tap the screen; each event line appears on the Kindle display.
60s timeout exits.
"""

import glob
import os
import select
import struct
import subprocess
import sys
import time

# ── Input event constants ──────────────────────────────────────────────────────
EV_FMT  = 'llHHi'
EV_SIZE = struct.calcsize(EV_FMT)  # 16 bytes on 32-bit ARM

EV_SYN, EV_KEY, EV_ABS = 0, 1, 3
BTN_TOUCH          = 0x14a
ABS_X, ABS_Y       = 0x00, 0x01
ABS_MT_POSITION_X  = 0x35
ABS_MT_POSITION_Y  = 0x36
ABS_MT_TRACKING_ID = 0x39

CODE_NAMES = {
    BTN_TOUCH:          'BTN_TOUCH',
    ABS_X:              'ABS_X',
    ABS_Y:              'ABS_Y',
    ABS_MT_POSITION_X:  'MT_X',
    ABS_MT_POSITION_Y:  'MT_Y',
    ABS_MT_TRACKING_ID: 'MT_ID',
}
TYPE_NAMES = {EV_SYN: 'SYN', EV_KEY: 'KEY', EV_ABS: 'ABS'}

# Devices that are definitely NOT the touchscreen
_SKIP = frozenset(['gpio-keys', 'power', 'keypad', 'hall', 'lid', 'als'])


def eips(col, row, text):
    subprocess.run(['eips', str(col), str(row), str(text)[:60]],
                   capture_output=True)


def parse_input_devices():
    """Return list of dicts: {name, event, path}."""
    try:
        raw = open('/proc/bus/input/devices').read()
    except OSError:
        return []
    devices = []
    for block in raw.strip().split('\n\n'):
        name = ''
        handlers = []
        for line in block.splitlines():
            if line.startswith('N: Name='):
                name = line.split('=', 1)[1].strip('"')
            elif line.startswith('H: Handlers='):
                handlers = line.split('=', 1)[1].split()
        event = next((h for h in handlers if h.startswith('event')), None)
        if event:
            devices.append({'name': name, 'event': event, 'path': '/dev/input/' + event})
    return devices


def classify(devices):
    candidates, skipped = [], []
    for d in devices:
        name_lc = d['name'].lower()
        if any(s in name_lc for s in _SKIP):
            skipped.append(d)
        else:
            candidates.append(d)
    return candidates, skipped


def main():
    override = sys.argv[1] if len(sys.argv) > 1 else None

    subprocess.run(['eips', '-c'], capture_output=True)
    row = 0

    eips(0, row, 'touch tester'); row += 1

    devices = parse_input_devices()

    if not devices:
        paths = sorted(glob.glob('/dev/input/event*'))
        eips(0, row, 'proc unavail — events: ' + ' '.join(os.path.basename(p) for p in paths))
        row += 1
        candidates = [{'name': os.path.basename(p), 'event': os.path.basename(p), 'path': p}
                      for p in paths]
        skipped = []
    else:
        candidates, skipped = classify(devices)
        eips(0, row, f'found {len(devices)} devices:'); row += 1
        for d in devices:
            marker = 'skip' if d in skipped else 'CAND'
            eips(0, row, f'  [{marker}] {d["event"]:8s} {d["name"][:38]}'); row += 1

    eips(0, row, '---'); row += 1

    if override:
        p = override if override.startswith('/') else '/dev/input/' + override
        to_open = [{'name': override, 'event': os.path.basename(p), 'path': p}]
        eips(0, row, f'override: {p}'); row += 1
    elif candidates:
        to_open = candidates
        eips(0, row, f'monitoring {len(candidates)} candidate(s):'); row += 1
        for d in candidates:
            eips(0, row, f'  {d["event"]}: {d["name"][:46]}'); row += 1
    else:
        to_open = devices
        eips(0, row, 'no candidates — monitoring all'); row += 1

    if not to_open:
        eips(0, row, 'ERROR: no devices'); return

    eips(0, row, 'tap screen (60s timeout)'); row += 1

    # ── Open all candidate fds ────────────────────────────────────────────────
    open_fds = {}  # fd → (file_obj, dev_dict)
    for d in to_open:
        try:
            f = open(d['path'], 'rb')
            open_fds[f.fileno()] = (f, d)
        except OSError as e:
            eips(0, row, f'  open {d["event"]} failed: {e}'); row += 1

    if not open_fds:
        eips(0, row, 'ERROR: could not open any device'); return

    # ── Event loop ────────────────────────────────────────────────────────────
    tap_count = 0
    last_x = {}  # fd → last x
    last_y = {}  # fd → last y
    deadline = time.time() + 60

    try:
        while time.time() < deadline:
            ready, _, _ = select.select(list(open_fds.keys()), [], [], 1.0)
            for fd in ready:
                f, dev = open_fds[fd]
                data = f.read(EV_SIZE)
                if len(data) < EV_SIZE:
                    continue
                _, _, ev_type, ev_code, ev_value = struct.unpack(EV_FMT, data)

                if ev_type == EV_SYN:
                    continue

                tag = dev['event']
                type_name = TYPE_NAMES.get(ev_type, str(ev_type))
                code_name = CODE_NAMES.get(ev_code, f'0x{ev_code:03x}')

                if ev_type == EV_KEY and ev_code == BTN_TOUCH:
                    action = 'DOWN' if ev_value else 'UP'
                    x, y = last_x.get(fd, 0), last_y.get(fd, 0)
                    tap_count += 1
                    eips(0, row, f'{tag} tap#{tap_count} {action} ({x},{y})')
                    row = min(row + 1, 30)

                elif ev_type == EV_ABS:
                    if ev_code in (ABS_MT_POSITION_X, ABS_X):
                        last_x[fd] = ev_value
                    elif ev_code in (ABS_MT_POSITION_Y, ABS_Y):
                        last_y[fd] = ev_value
                    elif ev_code != ABS_MT_TRACKING_ID:
                        eips(0, row, f'{tag} {type_name} {code_name}={ev_value}')
                        row = min(row + 1, 30)

                else:
                    eips(0, row, f'{tag} {type_name} {code_name}={ev_value}')
                    row = min(row + 1, 30)

    finally:
        for f, _ in open_fds.values():
            f.close()

    eips(0, row, f'done. {tap_count} taps detected.')


if __name__ == '__main__':
    main()
