#!/bin/bash
cd "$HOME/clawd-local"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:$PATH"
export PYTHONPATH="$HOME/Library/Python/3.9/lib/python/site-packages:$PYTHONPATH"

# Kill any existing instances before starting
pkill -f "python3 main.py" 2>/dev/null
sleep 2

# Wait for network to be ready (up to 60s)
echo "[$(date)] Waiting for network..."
for i in $(seq 1 30); do
    if curl -s --connect-timeout 3 https://api.telegram.org > /dev/null 2>&1; then
        echo "[$(date)] Network ready after ${i} attempts"
        break
    fi
    sleep 2
done

echo "[$(date)] Starting bot..."
exec /usr/bin/python3 main.py
