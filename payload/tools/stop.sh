#!/bin/sh
eips -c
pkill -f "cards/clock.py"   2>/dev/null
pkill -f "cards/weather.py" 2>/dev/null
eips 0 0 "stopped."
