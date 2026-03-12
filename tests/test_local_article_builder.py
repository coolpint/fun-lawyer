import tempfile
import unittest
from pathlib import Path

from fun_lawyer.config import AppConfig
from fun_lawyer.integrations.openai_client import OpenAIService


class LocalArticleBuilderTest(unittest.TestCase):
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
            teams_webhook_url=None,
            yt_dlp_bin="yt-dlp",
            ffmpeg_bin="ffmpeg",
            ffprobe_bin="ffprobe",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_local_fallback_builds_article_package(self) -> None:
        service = OpenAIService(self.config)
        payload = service.build_article_package(
            video={
                "title": "부동산 분쟁에서 꼭 봐야 할 포인트",
                "youtube_url": "https://www.youtube.com/watch?v=abc123",
                "published_at": "2026-03-12T00:00:00Z",
                "duration_sec": 360,
            },
            transcript={
                "text": (
                    "오늘은 부동산 분쟁에서 계약 해지와 손해배상 문제를 함께 보겠습니다. "
                    "실무에서는 특약 문구를 어떻게 읽느냐가 중요합니다. "
                    "중간금 지급 이후에는 해제 방식이 달라질 수 있습니다. "
                    "판단 기준을 모르면 분쟁 비용이 커질 수 있습니다."
                ),
                "segments": [
                    {"start_sec": 10, "end_sec": 20, "text": "오늘은 부동산 분쟁에서 계약 해지와 손해배상 문제를 함께 보겠습니다."},
                    {"start_sec": 120, "end_sec": 130, "text": "실무에서는 특약 문구를 어떻게 읽느냐가 중요합니다."},
                    {"start_sec": 240, "end_sec": 250, "text": "중간금 지급 이후에는 해제 방식이 달라질 수 있습니다."},
                ],
            },
        )
        self.assertTrue(payload["headline"])
        self.assertTrue(payload["body"])
        self.assertEqual(3, len(payload["captures"]))
        self.assertEqual("원문 영상", payload["sources"][0]["note"])


if __name__ == "__main__":
    unittest.main()
