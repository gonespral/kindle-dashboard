#!/bin/sh
eips -c

# Kill by per-card PID files
for name in clock worldclocks weather buienradar claude cal sleep_test; do
    pidfile="/tmp/kdash_${name}.pid"
    if [ -f "$pidfile" ]; then
        kill "$(cat "$pidfile")" 2>/dev/null
        rm -f "$pidfile"
    fi
done

# Legacy shared PID file (written by launch.sh before card's own PID file)
if [ -f /tmp/kdash_card.pid ]; then
    kill "$(cat /tmp/kdash_card.pid)" 2>/dev/null
    rm -f /tmp/kdash_card.pid
fi

# Belt-and-suspenders: catch any stray card processes
pkill -f 'extensions/kdash' 2>/dev/null
pkill -f '/cards/'           2>/dev/null

eips 0 0 "stopped."
