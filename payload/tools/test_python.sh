#!/bin/sh
# Runs via KUAL to verify Python environment. Results shown on screen + log.
LOG=/tmp/kdash_launch.log

eips -c

# Show which python3 is being used
export PATH="/usr/bin:/usr/local/bin:/opt/bin:/opt/local/bin:$PATH"
PY=""
for p in /usr/bin/python3 /usr/local/bin/python3 /opt/bin/python3 python3; do
  [ -x "$p" ] && PY="$p" && break
  command -v "$p" >/dev/null 2>&1 && PY="$(command -v "$p")" && break
done

eips 0 0 "py: ${PY:-NOT FOUND}"
echo "test-python.sh: PY=$PY PATH=$PATH" >> "$LOG"

[ -z "$PY" ] && exit 1

"$PY" - <<'EOF'
import subprocess, sys, os

def show(row, msg):
    print(msg)
    subprocess.run(["eips", "0", str(row), msg[:60]], capture_output=True)

show(1, "python " + sys.version.split()[0])
show(2, "path: " + sys.executable)

try:
    from PIL import Image
    show(3, "PIL " + Image.__version__)
except Exception as e:
    show(3, "PIL MISSING: " + str(e)[:40])

try:
    import lib.common  # check lib package is importable
    show(4, "lib: OK")
except Exception as e:
    show(4, "lib ERR: " + str(e)[:40])

show(5, "cwd: " + os.getcwd())
EOF
