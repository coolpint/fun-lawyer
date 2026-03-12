from __future__ import annotations

import html
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List

from ..config import AppConfig


TIMECODE_RE = re.compile(
    r"(?P<start>\d\d:\d\d:\d\d(?:\.\d+)?)\s+-->\s+(?P<end>\d\d:\d\d:\d\d(?:\.\d+)?)"
)


def parse_timestamp(value: str) -> float:
    hours, minutes, seconds = value.split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def _run(command: List[str]) -> str:
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    return completed.stdout.strip()


class MediaTools:
    def __init__(self, config: AppConfig):
        self.config = config

    def download_video(self, youtube_url: str, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        template = output_dir / "%(id)s.%(ext)s"
        stdout = _run(
            [
                self.config.yt_dlp_bin,
                "--no-playlist",
                "--merge-output-format",
                "mp4",
                "--print",
                "after_move:filepath",
                "-o",
                str(template),
                youtube_url,
            ]
        )
        video_path = Path(stdout.splitlines()[-1].strip())
        return video_path

    def download_subtitles(self, youtube_url: str, output_dir: Path, video_id: str) -> Path | None:
        output_dir.mkdir(parents=True, exist_ok=True)
        template = output_dir / "%(id)s.%(ext)s"
        try:
            _run(
                [
                    self.config.yt_dlp_bin,
                    "--no-playlist",
                    "--skip-download",
                    "--write-sub",
                    "--write-auto-sub",
                    "--sub-langs",
                    "ko.*,ko,en.*,en",
                    "--convert-subs",
                    "vtt",
                    "-o",
                    str(template),
                    youtube_url,
                ]
            )
        except subprocess.CalledProcessError:
            return None

        candidates = sorted(output_dir.glob(f"{video_id}*.vtt"))
        return candidates[0] if candidates else None

    def extract_audio(self, video_path: Path, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_path.exists():
            return output_path
        _run(
            [
                self.config.ffmpeg_bin,
                "-y",
                "-i",
                str(video_path),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                str(output_path),
            ]
        )
        return output_path

    def probe_dimensions(self, video_path: Path) -> tuple[int, int]:
        stdout = _run(
            [
                self.config.ffprobe_bin,
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height",
                "-of",
                "csv=s=x:p=0",
                str(video_path),
            ]
        )
        width_str, height_str = stdout.strip().split("x", 1)
        return int(width_str), int(height_str)

    def is_short_form(self, video_path: Path, duration_sec: int) -> bool:
        if duration_sec > 180:
            return False
        width, height = self.probe_dimensions(video_path)
        return height > width

    def capture_frame(self, video_path: Path, timestamp_sec: int, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        _run(
            [
                self.config.ffmpeg_bin,
                "-y",
                "-ss",
                str(timestamp_sec),
                "-i",
                str(video_path),
                "-frames:v",
                "1",
                "-q:v",
                "2",
                str(output_path),
            ]
        )
        return output_path

    def parse_subtitles(self, subtitle_path: Path) -> Dict[str, Any]:
        segments: List[Dict[str, Any]] = []
        lines = subtitle_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        current_time: tuple[float, float] | None = None
        current_text: List[str] = []

        def flush() -> None:
            nonlocal current_time, current_text
            if not current_time or not current_text:
                current_time = None
                current_text = []
                return
            joined = " ".join(self._clean_caption_text(line) for line in current_text).strip()
            if joined:
                segments.append(
                    {
                        "start_sec": round(current_time[0], 3),
                        "end_sec": round(current_time[1], 3),
                        "text": joined,
                    }
                )
            current_time = None
            current_text = []

        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                flush()
                continue
            match = TIMECODE_RE.match(line)
            if match:
                flush()
                current_time = (
                    parse_timestamp(match.group("start")),
                    parse_timestamp(match.group("end")),
                )
                continue
            if line.isdigit() or line == "WEBVTT":
                continue
            current_text.append(line)

        flush()
        transcript_text = "\n".join(segment["text"] for segment in segments)
        return {"text": transcript_text, "segments": segments, "language": None}

    @staticmethod
    def _clean_caption_text(value: str) -> str:
        stripped = re.sub(r"<[^>]+>", "", value)
        stripped = stripped.replace("&nbsp;", " ")
        return html.unescape(stripped)
