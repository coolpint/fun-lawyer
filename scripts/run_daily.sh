#!/bin/zsh
set -eu

ROOT_DIR="/Users/air/codes/fun-lawyer"
LOG_DIR="$ROOT_DIR/.data/logs"

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export YT_DLP_BIN="${YT_DLP_BIN:-/opt/homebrew/bin/yt-dlp}"
export FFMPEG_BIN="${FFMPEG_BIN:-/opt/homebrew/bin/ffmpeg}"
export FFPROBE_BIN="${FFPROBE_BIN:-/opt/homebrew/bin/ffprobe}"

mkdir -p "$LOG_DIR"
exec >> "$LOG_DIR/daily.log" 2>&1

echo "[$(date '+%Y-%m-%d %H:%M:%S')] fun-lawyer daily run started"
cd "$ROOT_DIR"
. "$ROOT_DIR/.venv/bin/activate"
python -m fun_lawyer.cli run-once --max-results 20
echo "[$(date '+%Y-%m-%d %H:%M:%S')] fun-lawyer daily run finished"
