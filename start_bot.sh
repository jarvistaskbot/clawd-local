#!/bin/bash
cd "$HOME/clawd-local"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:$PATH"
export PYTHONPATH="$HOME/Library/Python/3.9/lib/python/site-packages:$PYTHONPATH"

# Kill any existing instances before starting
pkill -f "python3 main.py" 2>/dev/null
sleep 1

# Wait for network to be ready (up to 30s)
for i in $(seq 1 15); do
    if curl -s --connect-timeout 2 https://api.telegram.org > /dev/null 2>&1; then
        break
    fi
    sleep 2
done

/usr/bin/python3 main.py
