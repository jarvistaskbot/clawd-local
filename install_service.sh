#!/bin/bash
# Installs the launchd service
mkdir -p ~/clawd-local/logs
cp com.clawd.local.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.clawd.local.plist
echo "Service installed and started"
