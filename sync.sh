#!/bin/sh
set -e

# Load env vars
if [ -f "$(dirname "$0")/env" ]; then
  . "$(dirname "$0")/env"
fi

WEATHER_CITY="${WEATHER_CITY:-Delft}"
BUIENALARM_POSTCODE="${BUIENALARM_POSTCODE:-}"
SCRIPTS_DIR="$(cd "$(dirname "$0")/payload" && pwd)"

# Find Kindle mount
if [ -n "$KINDLE_MOUNT" ]; then
  if [ ! -w "$KINDLE_MOUNT" ]; then
    echo "error: KINDLE_MOUNT=$KINDLE_MOUNT is not writable (Kindle not mounted there?)"
    exit 1
  fi
  KINDLE="$KINDLE_MOUNT"
else
  KINDLE=""
  for p in /run/media/*/Kindle* /media/*/Kindle* /Volumes/Kindle; do
    [ -w "$p" ] && KINDLE="$p" && break
  done
  if [ -z "$KINDLE" ]; then
    echo "error: Kindle not found. Connect via USB and unlock it, or set KINDLE_MOUNT in env"
    exit 1
  fi
fi

DEST="$KINDLE/extensions/kdash"
echo "Syncing to $DEST ..."

rm -rf "$DEST"
cp -r "$SCRIPTS_DIR/." "$DEST"

mkdir -p "$DEST/local"
cat > "$DEST/local/env.sh" <<EOF
${REFRESH_INTERVAL:+export REFRESH_INTERVAL="$REFRESH_INTERVAL"}
export WEATHER_CITY="$WEATHER_CITY"
export SHELL_HOST="${SHELL_HOST:-}"
export SHELL_PORT="${SHELL_PORT:-4568}"
export ANTHROPIC_ADMIN_API_KEY="${ANTHROPIC_ADMIN_API_KEY:-}"
export CLAUDE_OAUTH_TOKEN="${CLAUDE_OAUTH_TOKEN:-}"
export CLAUDE_REFRESH_TOKEN="${CLAUDE_REFRESH_TOKEN:-}"
export BUIENALARM_POSTCODE="$BUIENALARM_POSTCODE"
export BUIENALARM_LAT="${BUIENALARM_LAT:-}"
export BUIENALARM_LON="${BUIENALARM_LON:-}"
export KDASH_DEBUG="${KDASH_DEBUG:-true}"
export ICAL_URL="${ICAL_URL:-}"
export ICAL_URL_1="${ICAL_URL_1:-}"
export ICAL_URL_2="${ICAL_URL_2:-}"
export ICAL_URL_3="${ICAL_URL_3:-}"
export ICAL_URL_4="${ICAL_URL_4:-}"
export WORLD_CLOCK_LOCAL_CITY="${WORLD_CLOCK_LOCAL_CITY:-}"
export WORLD_CLOCK_TZ1="${WORLD_CLOCK_TZ1:-}"
export WORLD_CLOCK_TZ2="${WORLD_CLOCK_TZ2:-}"
export WORLD_CLOCK_TZ3="${WORLD_CLOCK_TZ3:-}"
export WORLD_CLOCK_TZ4="${WORLD_CLOCK_TZ4:-}"
export WORLD_CLOCK_CITY1="${WORLD_CLOCK_CITY1:-}"
export WORLD_CLOCK_CITY2="${WORLD_CLOCK_CITY2:-}"
export WORLD_CLOCK_CITY3="${WORLD_CLOCK_CITY3:-}"
export WORLD_CLOCK_CITY4="${WORLD_CLOCK_CITY4:-}"
EOF

find "$DEST" -name "*.sh" -exec chmod 755 {} \;

echo "Done! $DEST"
