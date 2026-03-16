import tempfile
import unittest
from pathlib import Path

from fun_lawyer.config import AppConfig
from fun_lawyer.integrations.teams import TeamsWebhookClient


class TeamsWebhookClientTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        base = Path(self.temp_dir.name)
        self.config = AppConfig(
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
            teams_webhook_url="https://example.com/webhook",
            yt_dlp_bin="yt-dlp",
            yt_dlp_cookies_path=None,
            yt_dlp_cookies_from_browser=None,
            ffmpeg_bin="ffmpeg",
            ffprobe_bin="ffprobe",
        )
        self.client = TeamsWebhookClient(self.config)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_build_article_card_skips_non_public_images(self) -> None:
        payload = self.client.build_article_card(
            article={
                "headline": "기사 제목",
                "summary": "요약",
                "body": "본문",
                "captures": [
                    {"path": "/tmp/a.jpg", "note": "장면 1"},
                    {"path": "/tmp/b.jpg", "note": "장면 2"},
                    {"path": "/tmp/c.jpg", "note": "장면 3"},
                ],
            },
            video={
                "title": "영상 제목",
                "youtube_url": "https://www.youtube.com/watch?v=abc123",
            },
        )
        body = payload["attachments"][0]["content"]["body"]
        image_blocks = [item for item in body if item["type"] == "Image"]
        self.assertEqual([], image_blocks)


if __name__ == "__main__":
    unittest.main()
