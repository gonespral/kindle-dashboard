#!/bin/sh
set -e

# Load config
if [ -f "$(dirname "$0")/sync.conf" ]; then
  . "$(dirname "$0")/sync.conf"
fi

REFRESH_INTERVAL="${REFRESH_INTERVAL:-3600}"
WEATHER_CITY="${WEATHER_CITY:-Delft}"
BUIENALARM_POSTCODE="${BUIENALARM_POSTCODE:-}"
SCRIPTS_DIR="$(cd "$(dirname "$0")/payload" && pwd)"

# Find Kindle mount
find_kindle() {
  for p in "$KINDLE_MOUNT" /run/media/*/Kindle* /media/*/Kindle* /Volumes/Kindle; do
    [ -n "$p" ] && [ -w "$p" ] && echo "$p" && return
  done
}

KINDLE="$(find_kindle)"
if [ -z "$KINDLE" ]; then
  echo "Kindle not found. Connect via USB and unlock it."
  exit 1
fi

DEST="$KINDLE/extensions/kdash"
echo "Syncing to $DEST ..."

rm -rf "$DEST"
cp -r "$SCRIPTS_DIR/." "$DEST"

mkdir -p "$DEST/local"
cat > "$DEST/local/env.sh" <<EOF
export REFRESH_INTERVAL=$REFRESH_INTERVAL
export WEATHER_CITY=$WEATHER_CITY
export SHELL_HOST=${SHELL_HOST:-}
export SHELL_PORT=${SHELL_PORT:-4568}
export ANTHROPIC_ADMIN_API_KEY=${ANTHROPIC_ADMIN_API_KEY:-}
export BUIENALARM_POSTCODE=$BUIENALARM_POSTCODE
EOF

find "$DEST" -name "*.sh" -exec chmod 755 {} \;

echo "Done! $DEST"
