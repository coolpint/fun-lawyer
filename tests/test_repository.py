import tempfile
import unittest
from pathlib import Path

from fun_lawyer.db import Repository


class RepositoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "app.db"
        self.repository = Repository(self.db_path)
        self.repository.init_schema()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_upsert_and_enqueue_job_are_deduped(self) -> None:
        video_id = self.repository.upsert_video(
            youtube_video_id="abc123",
            channel_handle="@lawfun_official",
            title="샘플 영상",
            youtube_url="https://www.youtube.com/watch?v=abc123",
            published_at="2026-03-12T00:00:00Z",
            duration_sec=601,
            is_short=False,
            raw_json={"id": "abc123"},
            status="pending",
        )
        same_video_id = self.repository.upsert_video(
            youtube_video_id="abc123",
            channel_handle="@lawfun_official",
            title="샘플 영상 수정",
            youtube_url="https://www.youtube.com/watch?v=abc123",
            published_at="2026-03-12T00:00:00Z",
            duration_sec=601,
            is_short=False,
            raw_json={"id": "abc123", "updated": True},
            status="pending",
        )
        self.assertEqual(video_id, same_video_id)

        first_job = self.repository.enqueue_job(
            job_type="transcribe",
            entity_type="video",
            entity_id=video_id,
            dedupe_key=f"transcribe:{video_id}",
        )
        second_job = self.repository.enqueue_job(
            job_type="transcribe",
            entity_type="video",
            entity_id=video_id,
            dedupe_key=f"transcribe:{video_id}",
        )
        self.assertEqual(first_job, second_job)
        self.assertEqual(1, len(list(self.repository.list_jobs())))

    def test_save_pipeline_records(self) -> None:
        video_id = self.repository.upsert_video(
            youtube_video_id="video-1",
            channel_handle="@lawfun_official",
            title="샘플 영상",
            youtube_url="https://www.youtube.com/watch?v=video-1",
            published_at="2026-03-12T00:00:00Z",
            duration_sec=420,
            is_short=False,
            raw_json={"id": "video-1"},
            status="pending",
        )
        transcript_id = self.repository.save_transcript(
            video_id=video_id,
            source="youtube_subtitles",
            language="ko",
            text="전사 본문",
            segments=[{"start_sec": 0, "end_sec": 2, "text": "전사 본문"}],
            status="success",
        )
        article_id = self.repository.save_article(
            video_id=video_id,
            headline="기사 제목",
            summary="기사 요약",
            body="기사 본문",
            sources=[{"title": "참고", "url": "https://example.com", "note": "참고 링크"}],
            captures=[
                {"timestamp_sec": 10, "path": "/tmp/a.jpg", "public_url": "https://cdn.example.com/a.jpg"},
                {"timestamp_sec": 20, "path": "/tmp/b.jpg", "public_url": "https://cdn.example.com/b.jpg"},
                {"timestamp_sec": 30, "path": "/tmp/c.jpg", "public_url": "https://cdn.example.com/c.jpg"},
            ],
            status="success",
        )
        delivery_id = self.repository.save_delivery(
            article_id=article_id,
            destination="teams",
            provider="incoming_webhook",
            external_id="1",
            payload={"ok": True},
            status="success",
        )

        self.assertIsInstance(transcript_id, int)
        self.assertIsInstance(article_id, int)
        self.assertIsInstance(delivery_id, int)
        self.assertEqual(1, len(list(self.repository.list_transcripts())))
        self.assertEqual(1, len(list(self.repository.list_articles())))
        self.assertEqual(1, len(list(self.repository.list_deliveries())))


if __name__ == "__main__":
    unittest.main()
