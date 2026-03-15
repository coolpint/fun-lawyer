from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


@dataclass(frozen=True)
class AppConfig:
    db_path: Path
    storage_dir: Path
    public_media_base_url: str | None
    youtube_channel_handle: str
    youtube_api_key: str | None
    openai_api_key: str | None
    openai_article_model: str
    openai_qa_model: str
    openai_transcribe_model: str
    local_transcribe_model: str
    local_transcribe_compute_type: str
    teams_webhook_url: str | None
    yt_dlp_bin: str
    yt_dlp_cookies_path: str | None
    ffmpeg_bin: str
    ffprobe_bin: str

    @classmethod
    def from_env(cls, cwd: Path | None = None) -> "AppConfig":
        base_dir = cwd or Path.cwd()
        load_dotenv(base_dir / ".env")

        db_path = Path(os.getenv("APP_DB_PATH", ".data/fun_lawyer.db"))
        storage_dir = Path(os.getenv("APP_STORAGE_DIR", ".data/storage"))
        resolved_db = (base_dir / db_path).resolve() if not db_path.is_absolute() else db_path
        resolved_storage = (base_dir / storage_dir).resolve() if not storage_dir.is_absolute() else storage_dir

        return cls(
            db_path=resolved_db,
            storage_dir=resolved_storage,
            public_media_base_url=os.getenv("APP_PUBLIC_MEDIA_BASE_URL") or None,
            youtube_channel_handle=os.getenv("YOUTUBE_CHANNEL_HANDLE", "@lawfun_official"),
            youtube_api_key=os.getenv("YOUTUBE_API_KEY") or None,
            openai_api_key=os.getenv("OPENAI_API_KEY") or None,
            openai_article_model=os.getenv("OPENAI_ARTICLE_MODEL", "gpt-5"),
            openai_qa_model=os.getenv("OPENAI_QA_MODEL", "gpt-5-mini"),
            openai_transcribe_model=os.getenv("OPENAI_TRANSCRIBE_MODEL", "gpt-4o-transcribe"),
            local_transcribe_model=os.getenv("LOCAL_TRANSCRIBE_MODEL", "small"),
            local_transcribe_compute_type=os.getenv("LOCAL_TRANSCRIBE_COMPUTE_TYPE", "int8"),
            teams_webhook_url=os.getenv("TEAMS_WEBHOOK_URL") or None,
            yt_dlp_bin=os.getenv("YT_DLP_BIN", "yt-dlp"),
            yt_dlp_cookies_path=os.getenv("YT_DLP_COOKIES_PATH") or None,
            ffmpeg_bin=os.getenv("FFMPEG_BIN", "ffmpeg"),
            ffprobe_bin=os.getenv("FFPROBE_BIN", "ffprobe"),
        )

    def ensure_directories(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def require(self, name: str) -> str:
        mapping: Dict[str, str | None] = {
            "youtube_api_key": self.youtube_api_key,
            "openai_api_key": self.openai_api_key,
            "teams_webhook_url": self.teams_webhook_url,
        }
        value = mapping.get(name)
        if not value:
            raise RuntimeError(f"Missing required config value: {name}")
        return value
