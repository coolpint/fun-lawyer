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

    def test_build_document_cards_splits_body_and_appends_link(self) -> None:
        payloads = self.client.build_document_cards(
            document={
                "headline": "문서 제목",
                "body": ("첫 문단입니다. " * 250) + "\n\n" + ("둘째 문단입니다. " * 250),
            },
            video={
                "title": "영상 제목",
                "youtube_url": "https://www.youtube.com/watch?v=abc123",
            },
        )
        self.assertGreaterEqual(len(payloads), 2)
        last_body = payloads[-1]["attachments"][0]["content"]["body"]
        self.assertIn("링크\nhttps://www.youtube.com/watch?v=abc123", last_body[-1]["text"])

    def test_build_status_card_renders_all_lines(self) -> None:
        payload = self.client.build_status_card(title="경고", lines=["첫 줄", "둘째 줄"])
        body = payload["attachments"][0]["content"]["body"]
        self.assertEqual("경고", body[0]["text"])
        self.assertEqual("첫 줄", body[1]["text"])
        self.assertEqual("둘째 줄", body[2]["text"])


if __name__ == "__main__":
    unittest.main()
