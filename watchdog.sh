#!/bin/bash
# Watchdog for clawd-local bot
# Restarts bot if dead or stuck in typing loop (no getUpdates in last 3 min)

LOG="$HOME/clawd-local/logs/watchdog.log"
STDERR_LOG="$HOME/clawd-local/logs/stderr.log"
MAX_IDLE_SECONDS=180  # 3 min without getUpdates = stuck

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG"
}

restart_bot() {
    log "ACTION: Killing all claude + bot processes"
    pkill -9 -f "claude" 2>/dev/null
    pkill -9 -f "[Pp]ython.*main\.py" 2>/dev/null
    sleep 3
    launchctl unload "$HOME/Library/LaunchAgents/com.clawd.local.plist" 2>/dev/null
    sleep 2
    launchctl load "$HOME/Library/LaunchAgents/com.clawd.local.plist"
    log "ACTION: Bot restarted"
}

# Check 1: Is the bot process running? (matches Python, python3, or Python3 running main.py)
if ! pgrep -f "[Pp]ython.*main\.py" > /dev/null 2>&1; then
    log "DEAD: bot process not running — restarting"
    restart_bot
    exit 0
fi

# Check 2: When was the last getUpdates in the log?
if [ ! -f "$STDERR_LOG" ]; then
    log "WARN: stderr.log not found — skipping idle check"
    exit 0
fi

LAST_UPDATE=$(grep "getUpdates" "$STDERR_LOG" | tail -1 | awk '{print $1, $2}')
if [ -z "$LAST_UPDATE" ]; then
    log "WARN: No getUpdates found in log — skipping"
    exit 0
fi

LAST_TS=$(date -j -f "%Y-%m-%d %H:%M:%S,%3N" "${LAST_UPDATE}" "+%s" 2>/dev/null || \
          date -j -f "%Y-%m-%d %H:%M:%S" "${LAST_UPDATE%,*}" "+%s" 2>/dev/null)
NOW=$(date "+%s")
IDLE=$((NOW - LAST_TS))

if [ "$IDLE" -gt "$MAX_IDLE_SECONDS" ]; then
    log "STUCK: Last getUpdates was ${IDLE}s ago (>${MAX_IDLE_SECONDS}s threshold) — restarting"
    restart_bot
else
    log "OK: Last getUpdates ${IDLE}s ago"
fi
