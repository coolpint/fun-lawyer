import tempfile
import unittest
from pathlib import Path

from fun_lawyer.config import AppConfig
from fun_lawyer.db import Repository
from fun_lawyer.qa_agent import QualityAgent
from fun_lawyer.stages.youtube_watcher import YoutubeWatcher


class FakeYouTubeClient:
    def list_recent_uploads(self, max_results: int = 5):
        return [
            {
                "youtube_video_id": "video-1",
                "channel_handle": "@lawfun_official",
                "title": "샘플 영상",
                "youtube_url": "https://www.youtube.com/watch?v=video-1",
                "published_at": "2026-03-12T00:00:00Z",
                "duration_sec": 420,
                "is_short": False,
                "raw_json": {"id": "video-1"},
            }
        ]


class YoutubeWatcherTest(unittest.TestCase):
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
            teams_webhook_url=None,
            yt_dlp_bin="yt-dlp",
            ffmpeg_bin="ffmpeg",
            ffprobe_bin="ffprobe",
        )
        self.repository = Repository(self.config.db_path)
        self.repository.init_schema()
        self.qa_agent = QualityAgent(self.config)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_scan_writes_video_and_transcript_job(self) -> None:
        watcher = YoutubeWatcher(self.repository, FakeYouTubeClient(), self.qa_agent)
        created = watcher.scan()
        self.assertEqual(1, created)
        self.assertEqual(1, len(list(self.repository.list_videos())))
        jobs = list(self.repository.list_jobs())
        self.assertEqual(1, len(jobs))
        self.assertEqual("transcribe", jobs[0]["job_type"])


if __name__ == "__main__":
    unittest.main()
