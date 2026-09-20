#!/bin/bash
cd "$HOME/clawd-local"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
export PYTHONPATH="$HOME/Library/Python/3.9/lib/python/site-packages:$PYTHONPATH"

PIDFILE="$HOME/clawd-local/bot.pid"

# Check if already running via PID file
if [ -f "$PIDFILE" ]; then
    OLD_PID=$(cat "$PIDFILE" 2>/dev/null)
    if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        echo "[$(date)] Bot already running as PID $OLD_PID, killing it first..."
        kill -9 "$OLD_PID" 2>/dev/null
        sleep 3
    fi
    rm -f "$PIDFILE"
fi

# Kill any stray bot instances. Anchored to end-of-cmdline so it only matches
# "<python> main.py" itself — an unanchored "main.py" also matches claude CLI
# processes whose prompt text mentions main.py, killing in-flight tasks.
pkill -9 -f "[Pp]ython[0-9.]* main\.py$" 2>/dev/null
sleep 4

# Wait for network (up to 90s)
echo "[$(date)] Waiting for network..."
for i in $(seq 1 45); do
    if curl -s --connect-timeout 3 https://api.telegram.org > /dev/null 2>&1; then
        echo "[$(date)] Network ready after attempt $i"
        break
    fi
    sleep 2
done

echo "[$(date)] Starting bot..."
/usr/bin/python3 main.py &
BOT_PID=$!
echo $BOT_PID > "$PIDFILE"
echo "[$(date)] Bot started with PID $BOT_PID"

# Wait for bot process — launchd sees our exit code
wait $BOT_PID
EXIT_CODE=$?
rm -f "$PIDFILE"
echo "[$(date)] Bot exited with code $EXIT_CODE"
exit $EXIT_CODE
