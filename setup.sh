#!/bin/bash
set -e

echo "Setting up clawd-local..."

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

if [ ! -f .env ]; then
    cp .env.example .env
    echo "Created .env from .env.example"
fi

echo ""
echo "Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Edit .env with your Telegram bot token and allowed user IDs"
echo "  2. Make sure Claude Code CLI is installed and authenticated"
echo "  3. Run: source venv/bin/activate && python main.py"
