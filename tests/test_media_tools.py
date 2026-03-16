import tempfile
import unittest
from pathlib import Path

from fun_lawyer.config import AppConfig
from fun_lawyer.integrations.media_tools import MediaTools


class MediaToolsCommandTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        base = Path(self.temp_dir.name)
        self.base_kwargs = dict(
            db_path=base / "app.db",
            storage_dir=base / "storage",
            public_media_base_url=None,
            youtube_channel_handle="@lawfun_official",
            youtube_api_key=None,
            openai_api_key=None,
            openai_article_model="gpt-5",
            openai_qa_model="gpt-5-mini",
            openai_transcribe_model="gpt-4o-transcribe",
            local_transcribe_model="small",
            local_transcribe_compute_type="int8",
            teams_webhook_url=None,
            yt_dlp_bin="yt-dlp",
            ffmpeg_bin="ffmpeg",
            ffprobe_bin="ffprobe",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_prefers_explicit_cookie_file(self) -> None:
        config = AppConfig(
            **self.base_kwargs,
            yt_dlp_cookies_path="/tmp/cookies.txt",
            yt_dlp_cookies_from_browser="chrome",
        )
        tools = MediaTools(config)
        command = tools._yt_dlp_base_command()
        self.assertIn("--cookies", command)
        self.assertNotIn("--cookies-from-browser", command)

    def test_uses_browser_cookie_source_when_file_is_missing(self) -> None:
        config = AppConfig(
            **self.base_kwargs,
            yt_dlp_cookies_path=None,
            yt_dlp_cookies_from_browser="chrome",
        )
        tools = MediaTools(config)
        command = tools._yt_dlp_base_command()
        self.assertIn("--cookies-from-browser", command)
        self.assertIn("chrome", command)


if __name__ == "__main__":
    unittest.main()
