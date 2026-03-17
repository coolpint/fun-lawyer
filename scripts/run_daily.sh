#!/bin/zsh
set -eu

ROOT_DIR="/Users/air/codes/fun-lawyer"
LOG_DIR="$ROOT_DIR/.data/logs"

mkdir -p "$LOG_DIR"
exec >> "$LOG_DIR/daily.log" 2>&1

echo "[$(date '+%Y-%m-%d %H:%M:%S')] fun-lawyer daily run started"
cd "$ROOT_DIR"
. "$ROOT_DIR/.venv/bin/activate"
python -m fun_lawyer.cli run-once --max-results 20
echo "[$(date '+%Y-%m-%d %H:%M:%S')] fun-lawyer daily run finished"
