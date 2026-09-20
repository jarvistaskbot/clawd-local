#!/bin/bash
cd "$HOME/clawd-local"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
export PYTHONPATH="$HOME/Library/Python/3.9/lib/python/site-packages:$PYTHONPATH"

PIDFILE="$HOME/clawd-local/bot.pid"
LOCKFILE="$HOME/clawd-local/bot.lock"

# Acquire exclusive lock — prevents two instances from starting simultaneously
exec 9>"$LOCKFILE"
if ! flock -n 9; then
    echo "[$(date)] Another instance is starting, exiting"
    exit 1
fi

# Kill any existing bot processes
echo "[$(date)] Killing existing bot processes..."
if [ -f "$PIDFILE" ]; then
    OLD_PID=$(cat "$PIDFILE" 2>/dev/null)
    if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        kill -9 "$OLD_PID" 2>/dev/null
        echo "[$(date)] Killed old PID $OLD_PID"
    fi
    rm -f "$PIDFILE"
fi
pkill -9 -f "main\.py" 2>/dev/null
sleep 4

# Wait for network (up to 90s)
echo "[$(date)] Waiting for network..."
for i in $(seq 1 45); do
    if curl -s --connect-timeout 3 https://api.telegram.org > /dev/null 2>&1; then
        echo "[$(date)] Network ready"
        break
    fi
    sleep 2
done

# Write our PID and start
echo "[$(date)] Starting bot..."
/usr/bin/python3 main.py &
BOT_PID=$!
echo $BOT_PID > "$PIDFILE"
echo "[$(date)] Bot started with PID $BOT_PID"

# Wait for bot to exit (keeps launchd happy)
wait $BOT_PID
EXIT_CODE=$?
rm -f "$PIDFILE"
echo "[$(date)] Bot exited with code $EXIT_CODE"
exit $EXIT_CODE
