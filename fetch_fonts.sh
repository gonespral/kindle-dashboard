#!/bin/sh
# Download the Anthropic brand webfonts used by the Claude Quota card and
# convert them to static TTFs in payload/fonts/.
#
# Usage: ./fetch_fonts.sh
#
# Requires: curl, python3 with fonttools + brotli
#   pixi install (or: pip install fonttools brotli)
set -e

FONT_DIR="$(cd "$(dirname "$0")/payload/fonts" && pwd)"
BASE=https://cdn.prod.website-files.com/67ce28cfec624e2b733f8a52

python3 -c "import fontTools, brotli" 2>/dev/null || {
  echo "error: python3 with fonttools + brotli required (pip install fonttools brotli)"
  exit 1
}

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "Downloading Anthropic webfonts..."
curl -fsSL -o "$TMP/serif.woff2"  "$BASE/69971a1551eb6cda0d656e8a_AnthropicSerif-Roman-Web.woff2"
curl -fsSL -o "$TMP/sans.woff2"   "$BASE/69971a00a3295036497e1a28_AnthropicSans-Roman-Web.woff2"
curl -fsSL -o "$TMP/sansit.woff2" "$BASE/69971a016067bf14b9b8f48d_AnthropicSans-Italic-Web.woff2"

# The webfonts are variable fonts (weight + optical size axes). The Kindle's
# Python 3.9 PIL can't select variable-font instances, so pin static instances.
python3 - "$TMP" "$FONT_DIR" <<'EOF'
import sys
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

tmp, out = sys.argv[1], sys.argv[2]
jobs = [
    ('serif.woff2',  {'wght': 500, 'opsz': 48}, 'ClaudeSerif.ttf'),
    ('serif.woff2',  {'wght': 650, 'opsz': 48}, 'ClaudeSerif-Bold.ttf'),
    ('sans.woff2',   {'wght': 400, 'opsz': 16}, 'ClaudeSans.ttf'),
    ('sansit.woff2', {'wght': 400, 'opsz': 16}, 'ClaudeSans-Italic.ttf'),
]
for src, axes, name in jobs:
    f = TTFont(f'{tmp}/{src}')
    instancer.instantiateVariableFont(f, axes, inplace=True)
    f.flavor = None
    f.save(f'{out}/{name}')
    print(f'  wrote payload/fonts/{name}')
EOF

echo "Done. Run ./sync.sh to copy them to the Kindle."
