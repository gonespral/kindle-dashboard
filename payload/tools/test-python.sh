#!/bin/sh
eips -c
python3 - <<'EOF'
import subprocess, sys, os

lines = []
lines.append("python: " + sys.version.split()[0])

try:
    from PIL import Image
    lines.append("PIL: " + Image.__version__)
except ImportError:
    lines.append("PIL: not found")

for i, line in enumerate(lines):
    subprocess.run(["eips", "0", str(i + 1), line])
EOF
