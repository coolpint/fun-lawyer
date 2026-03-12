from __future__ import annotations

from pathlib import Path

from ..artifacts import write_json, write_text
from ..config import AppConfig
from ..db import Repository
from ..models import JobType
from ..qa_agent import QualityAgent


class TranscriptWorker:
    def __init__(self, config: AppConfig, repository: Repository, media_tools, openai_service, qa_agent: QualityAgent):
        self.config = config
        self.repository = repository
        self.media_tools = media_tools
        self.openai_service = openai_service
        self.qa_agent = qa_agent

    def process(self, video_id: int) -> int:
        video = self.repository.get_video(video_id)
        if not video:
            raise RuntimeError(f"Video not found: {video_id}")

        working_dir = self.config.storage_dir / video["youtube_video_id"]
        video_path = Path(video["local_video_path"]) if video["local_video_path"] else self.media_tools.download_video(video["youtube_url"], working_dir)
        audio_path = working_dir / f"{video['youtube_video_id']}.wav"
        self.repository.update_video_paths(
            video_id,
            local_video_path=str(video_path),
            local_audio_path=str(audio_path),
        )

        if self.media_tools.is_short_form(video_path, int(video["duration_sec"])):
            quality = self.qa_agent.review_video({**dict(video), "is_short": True})
            self.repository.save_quality_check(
                stage="transcript_worker.short_check",
                entity_type="video",
                entity_id=video_id,
                status=quality.status(),
                findings=[finding.to_dict() for finding in quality.findings],
                score=quality.score,
                raw_response=quality.raw_response,
            )
            self.repository.set_entity_status("videos", video_id, quality.status())
            return video_id

        subtitle_path = self.media_tools.download_subtitles(video["youtube_url"], working_dir, video["youtube_video_id"])
        if subtitle_path:
            transcript_payload = self.media_tools.parse_subtitles(subtitle_path)
            source = "youtube_subtitles"
        else:
            extracted_audio = self.media_tools.extract_audio(video_path, audio_path)
            transcript_payload = self.openai_service.transcribe_audio(str(extracted_audio))
            source = "openai_transcription"

        transcript_id = self.repository.save_transcript(
            video_id=video_id,
            source=source,
            language=transcript_payload.get("language"),
            text=transcript_payload["text"],
            segments=transcript_payload["segments"],
            status="running",
        )
        quality = self.qa_agent.review_transcript(transcript_payload)
        transcript_status = quality.status()
        self.repository.save_transcript(
            video_id=video_id,
            source=source,
            language=transcript_payload.get("language"),
            text=transcript_payload["text"],
            segments=transcript_payload["segments"],
            status=transcript_status,
        )
        self.repository.save_quality_check(
            stage="transcript_worker",
            entity_type="transcript",
            entity_id=transcript_id,
            status=transcript_status,
            findings=[finding.to_dict() for finding in quality.findings],
            score=quality.score,
            raw_response=quality.raw_response,
        )
        self._export_transcript_artifacts(
            youtube_video_id=video["youtube_video_id"],
            transcript_payload=transcript_payload,
            source=source,
            status=transcript_status,
        )
        if quality.passed:
            self.repository.enqueue_job(
                job_type=JobType.BUILD_ARTICLE.value,
                entity_type="video",
                entity_id=video_id,
                dedupe_key=f"article:{video_id}",
            )
        return transcript_id

    def _export_transcript_artifacts(
        self,
        *,
        youtube_video_id: str,
        transcript_payload: dict,
        source: str,
        status: str,
    ) -> None:
        base_dir = self.config.storage_dir / youtube_video_id
        write_text(base_dir / "transcript.txt", transcript_payload["text"])
        write_json(
            base_dir / "transcript.json",
            {
                "source": source,
                "status": status,
                "language": transcript_payload.get("language"),
                "segments": transcript_payload["segments"],
            },
        )
