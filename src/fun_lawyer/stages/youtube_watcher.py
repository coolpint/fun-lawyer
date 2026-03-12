from __future__ import annotations

from ..db import Repository
from ..models import JobType
from ..qa_agent import QualityAgent


class YoutubeWatcher:
    def __init__(self, repository: Repository, youtube_client, qa_agent: QualityAgent):
        self.repository = repository
        self.youtube_client = youtube_client
        self.qa_agent = qa_agent

    def scan(self, max_results: int = 5) -> int:
        candidates = self.youtube_client.list_recent_uploads(max_results=max_results)
        created = 0
        for payload in candidates:
            existing = self.repository.get_video_by_youtube_id(payload["youtube_video_id"])
            status = "pending"
            if existing:
                continue
            quality = self.qa_agent.review_video(payload)
            status = quality.status()
            video_id = self.repository.upsert_video(status=status, **payload)
            self.repository.save_quality_check(
                stage="youtube_watcher",
                entity_type="video",
                entity_id=video_id,
                status=status,
                findings=[finding.to_dict() for finding in quality.findings],
                score=quality.score,
                raw_response=quality.raw_response,
            )
            if quality.passed:
                self.repository.enqueue_job(
                    job_type=JobType.TRANSCRIBE.value,
                    entity_type="video",
                    entity_id=video_id,
                    dedupe_key=f"transcribe:{video_id}",
                )
                created += 1
        return created
