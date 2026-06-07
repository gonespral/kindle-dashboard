#!/bin/sh
eips -c

# Kill by PID saved by last launch
if [ -f /tmp/kdash_card.pid ]; then
    kill "$(cat /tmp/kdash_card.pid)" 2>/dev/null
    rm -f /tmp/kdash_card.pid
fi

# Kill any remaining python3 processes running a kdash script
pkill -f 'extensions/kdash' 2>/dev/null
pkill -f '/cards/'           2>/dev/null

eips 0 0 "stopped."
