#!/bin/sh
# Record a command into logs/commands.log with a timestamp.
# Usage: ./scripts/log-command.sh "command you ran"
set -eu

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
LOG="$ROOT/logs/commands.log"

if [ "$#" -eq 0 ]; then
  echo "Usage: $0 \"command you ran\"" >&2
  exit 1
fi

mkdir -p "$ROOT/logs"
printf '%s | %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >> "$LOG"
echo "Logged to $LOG"
