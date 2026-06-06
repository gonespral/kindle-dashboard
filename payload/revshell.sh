#!/bin/sh
DIR="$(cd "$(dirname "$0")" && pwd)"
. "$DIR/local/env.sh" 2>/dev/null

PC_IP="${SHELL_HOST:-${SERVER_URL#http://}}"
PC_IP="${PC_IP%%:*}"
PC_PORT="${SHELL_PORT:-4568}"
RETRIES=10
RETRY_DELAY=5

eips -c
eips 0 0 "On your PC run:"
eips 0 1 "  stty raw -echo"
eips 0 2 "  nc -lvp $PC_PORT"
eips 0 3 "  stty sane  (after disconnect)"
eips 0 5 "Connecting to $PC_IP:$PC_PORT ..."
eips 0 6 "Will retry ${RETRIES}x every ${RETRY_DELAY}s"

python3 - "$PC_IP" "$PC_PORT" "$RETRIES" "$RETRY_DELAY" <<'EOF'
import os, pty, select, socket, sys, struct, termios, fcntl, time

host, port, retries, delay = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])

for attempt in range(1, retries + 1):
    print(f"[revshell] attempt {attempt}/{retries} -> {host}:{port}")
    try:
        s = socket.socket()
        s.settimeout(5)
        s.connect((host, port))
        s.settimeout(None)
        break
    except OSError as e:
        print(f"[revshell] failed: {e}")
        if attempt < retries:
            print(f"[revshell] retrying in {delay}s...")
            time.sleep(delay)
        else:
            print(f"[revshell] gave up after {retries} attempts")
            sys.exit(1)

s.sendall(b"\r\n\033[1;32m[kdash]\033[0m Kindle shell ready\r\n\r\n")

os.environ['TERM'] = 'xterm-256color'
os.environ['PS1'] = '\033[1;36mkindle\033[0m:\033[1;34m\\w\033[0m# '

pid, fd = pty.fork()

if pid == 0:
    os.execv('/bin/sh', ['sh', '--login'])
else:
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack('HHHH', 24, 80, 0, 0))
    try:
        while True:
            r, _, _ = select.select([s, fd], [], [])
            if s in r:
                data = s.recv(1024)
                if not data:
                    break
                os.write(fd, data)
            if fd in r:
                try:
                    data = os.read(fd, 1024)
                    if not data:
                        break
                    s.sendall(data)
                except OSError:
                    break
    finally:
        print("[revshell] session ended")
        os.waitpid(pid, 0)
        s.close()
EOF

eips 0 5 "revshell done — check /tmp/kdash.log"
