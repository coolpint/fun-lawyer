from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from ..config import AppConfig
from ..db import Repository
from ..models import JobType
from ..qa_agent import QualityAgent


class ArticleBuilder:
    def __init__(self, config: AppConfig, repository: Repository, media_tools, openai_service, qa_agent: QualityAgent):
        self.config = config
        self.repository = repository
        self.media_tools = media_tools
        self.openai_service = openai_service
        self.qa_agent = qa_agent

    def process(self, video_id: int) -> int:
        video = self.repository.get_video(video_id)
        transcript = self.repository.get_transcript(video_id)
        if not video or not transcript:
            raise RuntimeError(f"Video or transcript missing for video_id={video_id}")
        if not video["local_video_path"]:
            raise RuntimeError(f"Local video path missing for video_id={video_id}")

        self.repository.set_entity_status("transcripts", transcript["id"], "running")
        transcript_payload = {
            "text": transcript["text"],
            "segments": json.loads(transcript["segments_json"]),
        }
        article_payload = self.openai_service.build_article_package(video=dict(video), transcript=transcript_payload)
        captures = self._materialize_captures(
            Path(video["local_video_path"]),
            video["youtube_video_id"],
            article_payload["captures"],
        )

        article_id = self.repository.save_article(
            video_id=video_id,
            headline=article_payload["headline"],
            summary=article_payload["summary"],
            body=article_payload["body"],
            sources=article_payload["sources"],
            captures=captures,
            status="running",
        )
        quality = self.qa_agent.review_article(
            {
                "headline": article_payload["headline"],
                "summary": article_payload["summary"],
                "body": article_payload["body"],
                "captures": captures,
                "sources": article_payload["sources"],
            }
        )
        article_status = quality.status()
        self.repository.save_article(
            video_id=video_id,
            headline=article_payload["headline"],
            summary=article_payload["summary"],
            body=article_payload["body"],
            sources=article_payload["sources"],
            captures=captures,
            status=article_status,
        )
        self.repository.save_quality_check(
            stage="article_builder",
            entity_type="article",
            entity_id=article_id,
            status=article_status,
            findings=[finding.to_dict() for finding in quality.findings],
            score=quality.score,
            raw_response=quality.raw_response,
        )
        if quality.passed:
            self.repository.enqueue_job(
                job_type=JobType.PUBLISH_TEAMS.value,
                entity_type="article",
                entity_id=article_id,
                dedupe_key=f"publish:{article_id}",
            )
        return article_id

    def _materialize_captures(self, video_path: Path, youtube_video_id: str, captures: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        capture_dir = self.config.storage_dir / youtube_video_id / "captures"
        materialized: List[Dict[str, Any]] = []
        for index, item in enumerate(captures, start=1):
            output_path = capture_dir / f"capture_{index:02d}.jpg"
            self.media_tools.capture_frame(video_path, int(item["timestamp_sec"]), output_path)
            record = {
                "timestamp_sec": int(item["timestamp_sec"]),
                "note": item.get("note", ""),
                "path": str(output_path),
            }
            public_url = self._public_url_for(output_path)
            if public_url:
                record["public_url"] = public_url
            materialized.append(record)
        return materialized

    def _public_url_for(self, path: Path) -> str | None:
        if not self.config.public_media_base_url:
            return None
        relative = path.relative_to(self.config.storage_dir).as_posix()
        return f"{self.config.public_media_base_url.rstrip('/')}/{relative}"
