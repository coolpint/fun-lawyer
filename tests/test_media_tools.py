import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def test_reuses_existing_subtitle_file_before_network_call(self) -> None:
        config = AppConfig(
            **self.base_kwargs,
            yt_dlp_cookies_path=None,
            yt_dlp_cookies_from_browser=None,
        )
        tools = MediaTools(config)
        output_dir = Path(self.temp_dir.name) / "subs"
        output_dir.mkdir(parents=True, exist_ok=True)
        subtitle_path = output_dir / "abc123.ko.vtt"
        subtitle_path.write_text("WEBVTT\n", encoding="utf-8")

        with patch("fun_lawyer.integrations.media_tools._run") as mock_run:
            result = tools.download_subtitles("https://youtube.com/watch?v=abc123", output_dir, "abc123")

        self.assertEqual(subtitle_path, result)
        mock_run.assert_not_called()

    def test_parse_subtitles_removes_incremental_caption_duplicates(self) -> None:
        config = AppConfig(
            **self.base_kwargs,
            yt_dlp_cookies_path=None,
            yt_dlp_cookies_from_browser=None,
        )
        tools = MediaTools(config)
        subtitle_path = Path(self.temp_dir.name) / "sample.vtt"
        subtitle_path.write_text(
            "\n".join(
                [
                    "WEBVTT",
                    "",
                    "00:00:00.000 --> 00:00:01.000",
                    "안녕하세요",
                    "",
                    "00:00:01.000 --> 00:00:02.000",
                    "안녕하세요 반갑습니다",
                    "",
                    "00:00:02.000 --> 00:00:03.000",
                    "반갑습니다 오늘 이야기합니다",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        parsed = tools.parse_subtitles(subtitle_path)
        self.assertEqual("안녕하세요\n반갑습니다\n오늘 이야기합니다", parsed["text"])


if __name__ == "__main__":
    unittest.main()
