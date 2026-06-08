#!/bin/sh
# Verbose launcher for kdash cards.
#
# KEY FIX: uses setsid to detach the Python process from KUAL's process group,
# which would otherwise kill it with SIGHUP when KUAL's shell exits.
#
# Logs every step on screen (eips rows) and to /tmp/kdash_launch.log

LOG=/tmp/kdash_launch.log
ROW=0

say() {
  ROW=$((ROW + 1))
  printf '%s\n' "$1" >> "$LOG"
  eips 0 "$ROW" "$1" 2>/dev/null || true
}

eips -c 2>/dev/null || true
printf '\n=== launch %s ===\n' "$(date)" >> "$LOG"
printf 'args: %s\n' "$*"    >> "$LOG"

say "kdash launch"
say "cwd: $(pwd)"
say "arg: $*"

# ── 1. Find kdash dir ──────────────────────────────────────────────────────────
SCRIPT_DIR="$(dirname "$0")"
KDASH_DIR="$(cd "$SCRIPT_DIR/.." 2>/dev/null && pwd)"
say "dir: $KDASH_DIR"

if [ ! -f "$KDASH_DIR/menu.json" ]; then
  say "no menu.json — scanning..."
  for d in /mnt/us/extensions/kdash /mnt/us/kual/kdash; do
    [ -f "$d/menu.json" ] && KDASH_DIR="$d" && break
  done
fi

if [ ! -f "$KDASH_DIR/menu.json" ]; then
  say "FATAL: dir not found"
  exit 1
fi

cd "$KDASH_DIR"
say "cd ok: $(pwd)"

# ── 2. Load env ────────────────────────────────────────────────────────────────
if [ -f ./local/env.sh ]; then
  . ./local/env.sh
  say "env: loaded"
else
  say "WARN: no local/env.sh"
fi

# ── 3. Find python3 ────────────────────────────────────────────────────────────
export PATH="/usr/bin:/usr/local/bin:/opt/bin:/opt/local/bin:$PATH"
PY=""
for p in /usr/bin/python3 /usr/local/bin/python3 /opt/bin/python3 python3; do
  if [ -x "$p" ]; then
    PY="$p"; break
  fi
  if command -v "$p" >/dev/null 2>&1; then
    PY="$(command -v "$p")"; break
  fi
done

if [ -z "$PY" ]; then
  say "FATAL: no python3 in PATH"
  say "$PATH"
  exit 1
fi

say "py: $PY"
say "ver: $("$PY" --version 2>&1)"

# ── 4. Import check (synchronous — errors visible on screen) ───────────────────
say "checking imports..."
CARD="$1"
CHECK="$("$PY" - "$CARD" 2>&1 <<'EOF'
import sys, os
card = sys.argv[1]
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(card))))
errs = []
try:
    from PIL import Image
except Exception as e:
    errs.append("PIL: " + str(e))
try:
    import lib.common
except Exception as e:
    errs.append("lib: " + str(e))
if errs:
    print("\n".join(errs)); sys.exit(1)
print("PIL+lib OK")
EOF
)"
RC=$?
say "$CHECK"
if [ "$RC" -ne 0 ]; then
  say "FATAL: import check failed"
  exit 1
fi

# ── 5. Launch — detached from KUAL's process group ────────────────────────────
eips -c 2>/dev/null || true
say "detaching..."

# Try setsid first (BusyBox has it); fall back to subshell orphan trick
if command -v setsid >/dev/null 2>&1; then
  setsid "$PY" "$@" >> "$LOG" 2>&1 < /dev/null &
  echo "$!" > /tmp/kdash_card.pid
  say "setsid pid: $!"
else
  # ( cmd & ) orphans the child when the subshell exits; $! written from within
  ( "$PY" "$@" >> "$LOG" 2>&1 < /dev/null &
    echo $! > /tmp/kdash_card.pid )
  say "subshell launch ok"
fi

say "done — tail $LOG for runtime errors"
