import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from fun_lawyer.config import AppConfig
from fun_lawyer.models import QualityResult
from fun_lawyer.stages.article_builder import DocumentBuilder


class DocumentBuilderTest(unittest.TestCase):
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
            teams_webhook_url=None,
            yt_dlp_bin="yt-dlp",
            yt_dlp_cookies_path=None,
            yt_dlp_cookies_from_browser=None,
            ffmpeg_bin="ffmpeg",
            ffprobe_bin="ffprobe",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_process_builds_script_document_without_touching_transcript_status(self) -> None:
        repository = MagicMock()
        repository.get_video.return_value = {
            "id": 17,
            "youtube_video_id": "abc123",
            "title": "샘플 영상",
            "youtube_url": "https://www.youtube.com/watch?v=abc123",
            "published_at": "2026-03-17T00:00:00Z",
            "duration_sec": 240,
            "local_video_path": str(self.config.storage_dir / "abc123.mp4"),
        }
        repository.get_transcript.return_value = {
            "id": 1,
            "text": "첫 문장입니다.\n둘째 문장입니다.",
            "segments_json": '[{"start_sec": 1, "end_sec": 2, "text": "첫 문장입니다."}, {"start_sec": 3, "end_sec": 4, "text": "둘째 문장입니다."}]',
        }
        repository.save_article.side_effect = [1, 1]

        qa_agent = MagicMock()
        qa_agent.review_document.return_value = QualityResult(stage="document", passed=True, findings=[], score=1.0)

        builder = DocumentBuilder(self.config, repository, MagicMock(), MagicMock(), qa_agent)
        builder.process(17)

        repository.set_entity_status.assert_not_called()
        save_call = repository.save_article.call_args_list[0]
        self.assertEqual("샘플 영상", save_call.kwargs["headline"])
        self.assertEqual([], save_call.kwargs["captures"])


if __name__ == "__main__":
    unittest.main()
