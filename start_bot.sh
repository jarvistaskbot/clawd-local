#!/bin/bash
cd "$HOME/clawd-local"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:$PATH"
export PYTHONPATH="$HOME/Library/Python/3.9/lib/python/site-packages:$PYTHONPATH"

# Kill any existing instances before starting
pkill -f "python3 main.py" 2>/dev/null
sleep 1

/usr/bin/python3 main.py
