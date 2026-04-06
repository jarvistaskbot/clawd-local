#!/bin/bash
launchctl unload ~/Library/LaunchAgents/com.clawd.local.plist
rm ~/Library/LaunchAgents/com.clawd.local.plist
echo "Service removed"
