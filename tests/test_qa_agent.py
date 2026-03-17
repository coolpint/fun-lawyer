import tempfile
import unittest
from pathlib import Path

from fun_lawyer.config import AppConfig
from fun_lawyer.qa_agent import QualityAgent


class QualityAgentTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        base = Path(self.temp_dir.name)
        self.config = AppConfig(
            db_path=base / "app.db",
            storage_dir=base / "storage",
            public_media_base_url="https://cdn.example.com",
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
        self.agent = QualityAgent(self.config)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_document_review_requires_title_body_and_link(self) -> None:
        result = self.agent.review_document(
            {
                "title": "",
                "body": "짧다",
                "source_url": "",
            }
        )
        self.assertFalse(result.passed)
        codes = {finding.code for finding in result.findings}
        self.assertIn("title_missing", codes)
        self.assertIn("body_too_short", codes)
        self.assertIn("source_url_missing", codes)

    def test_delivery_review_accepts_card_list(self) -> None:
        result = self.agent.review_delivery(
            {
                "webhook_url": "https://example.com/webhook",
                "cards": [{"type": "message"}],
            }
        )
        self.assertTrue(result.passed)

    def test_transcript_review_accepts_complete_payload(self) -> None:
        result = self.agent.review_transcript(
            {
                "text": "가" * 220,
                "segments": [
                    {"start_sec": 0.0, "end_sec": 12.0, "text": "가" * 220},
                ],
            }
        )
        self.assertTrue(result.passed)


if __name__ == "__main__":
    unittest.main()
