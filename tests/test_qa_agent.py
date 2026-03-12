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
            teams_webhook_url="https://example.com/webhook",
            yt_dlp_bin="yt-dlp",
            ffmpeg_bin="ffmpeg",
            ffprobe_bin="ffprobe",
        )
        self.agent = QualityAgent(self.config)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_article_review_rejects_banned_phrase_and_missing_captures(self) -> None:
        result = self.agent.review_article(
            {
                "headline": "기사 제목",
                "summary": "요약",
                "body": "이 문장은 방증하는 표현을 포함한다.",
                "captures": [{"path": "/tmp/one.jpg"}],
            }
        )
        self.assertFalse(result.passed)
        codes = {finding.code for finding in result.findings}
        self.assertIn("banned_phrase", codes)
        self.assertIn("capture_count_invalid", codes)

    def test_delivery_review_requires_public_image_urls(self) -> None:
        result = self.agent.review_delivery(
            {
                "webhook_url": "https://example.com/webhook",
                "card": {"type": "message"},
                "captures": [
                    {"path": "/tmp/1.jpg", "public_url": "https://cdn.example.com/1.jpg"},
                    {"path": "/tmp/2.jpg"},
                    {"path": "/tmp/3.jpg", "public_url": "https://cdn.example.com/3.jpg"},
                ],
            }
        )
        self.assertFalse(result.passed)
        codes = {finding.code for finding in result.findings}
        self.assertIn("public_url_missing", codes)

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
