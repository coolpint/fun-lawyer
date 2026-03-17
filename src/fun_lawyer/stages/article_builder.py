from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from ..artifacts import write_json, write_text
from ..config import AppConfig
from ..db import Repository
from ..models import JobType
from ..qa_agent import QualityAgent


class DocumentBuilder:
    def __init__(self, config: AppConfig, repository: Repository, media_tools, openai_service, qa_agent: QualityAgent):
        self.config = config
        self.repository = repository
        self.qa_agent = qa_agent

    def process(self, video_id: int) -> int:
        video = self.repository.get_video(video_id)
        transcript = self.repository.get_transcript(video_id)
        if not video or not transcript:
            raise RuntimeError(f"Video or transcript missing for video_id={video_id}")
        transcript_payload = {
            "text": transcript["text"],
            "segments": json.loads(transcript["segments_json"]),
        }
        document_body = self._format_script_body(transcript_payload["segments"], transcript_payload["text"])

        document_id = self.repository.save_article(
            video_id=video_id,
            headline=video["title"],
            summary="스크립트",
            body=document_body,
            sources=[
                {
                    "title": video["title"],
                    "url": video["youtube_url"],
                    "note": "원문 영상",
                }
            ],
            captures=[],
            status="running",
        )
        quality = self.qa_agent.review_document(
            {
                "title": video["title"],
                "body": document_body,
                "source_url": video["youtube_url"],
            }
        )
        document_status = quality.status()
        self.repository.save_article(
            video_id=video_id,
            headline=video["title"],
            summary="스크립트",
            body=document_body,
            sources=[
                {
                    "title": video["title"],
                    "url": video["youtube_url"],
                    "note": "원문 영상",
                }
            ],
            captures=[],
            status=document_status,
        )
        self.repository.save_quality_check(
            stage="document_builder",
            entity_type="document",
            entity_id=document_id,
            status=document_status,
            findings=[finding.to_dict() for finding in quality.findings],
            score=quality.score,
            raw_response=quality.raw_response,
        )
        self._export_document_artifacts(
            youtube_video_id=video["youtube_video_id"],
            title=video["title"],
            body=document_body,
            source_url=video["youtube_url"],
            status=document_status,
        )
        if quality.passed:
            self.repository.enqueue_job(
                job_type=JobType.PUBLISH_TEAMS.value,
                entity_type="document",
                entity_id=document_id,
                dedupe_key=f"publish:{document_id}",
            )
        return document_id

    def _format_script_body(self, segments: List[Dict[str, Any]], fallback_text: str) -> str:
        lines = [self._normalize_line(str(segment.get("text") or "")) for segment in segments]
        cleaned_lines = [line for line in lines if line]
        if not cleaned_lines:
            return fallback_text.strip()

        paragraphs: List[str] = []
        current: List[str] = []
        current_length = 0
        for line in cleaned_lines:
            if current and (current_length + len(line) + 1 > 700):
                paragraphs.append(" ".join(current).strip())
                current = [line]
                current_length = len(line)
                continue
            current.append(line)
            current_length += len(line) + 1
            if line.endswith((".", "?", "!", "다")) and current_length >= 240:
                paragraphs.append(" ".join(current).strip())
                current = []
                current_length = 0
        if current:
            paragraphs.append(" ".join(current).strip())
        return "\n\n".join(paragraph for paragraph in paragraphs if paragraph).strip()

    @staticmethod
    def _normalize_line(value: str) -> str:
        cleaned = " ".join(value.split()).strip()
        if cleaned.startswith(">> "):
            cleaned = cleaned[3:].strip()
        elif cleaned.startswith(">>"):
            cleaned = cleaned[2:].strip()
        if len(cleaned) < 2:
            return ""
        return cleaned

    def _export_document_artifacts(
        self,
        *,
        youtube_video_id: str,
        title: str,
        body: str,
        source_url: str,
        status: str,
    ) -> None:
        base_dir = self.config.storage_dir / youtube_video_id
        markdown = "\n".join(
            [
                f"# {title}",
                "",
                body,
                "",
                f"링크: {source_url}",
            ]
        ).strip() + "\n"
        write_text(base_dir / "script.md", markdown)
        write_json(
            base_dir / "script.json",
            {
                "title": title,
                "body": body,
                "source_url": source_url,
                "status": status,
            },
        )


ArticleBuilder = DocumentBuilder
