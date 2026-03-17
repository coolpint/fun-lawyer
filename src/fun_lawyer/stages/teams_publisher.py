from __future__ import annotations

import json

from ..artifacts import write_json
from ..config import AppConfig
from ..db import Repository, utc_now
from ..qa_agent import QualityAgent


class TeamsPublisher:
    def __init__(self, config: AppConfig, repository: Repository, teams_client, qa_agent: QualityAgent):
        self.config = config
        self.repository = repository
        self.teams_client = teams_client
        self.qa_agent = qa_agent

    def process(self, article_id: int) -> int:
        document = self.repository.get_article_by_id(article_id)
        if not document:
            raise RuntimeError(f"Document not found: {article_id}")
        video = self.repository.get_video(int(document["video_id"]))
        if not video:
            raise RuntimeError(f"Video not found for document: {article_id}")

        document_payload = dict(document)
        cards = self.teams_client.build_document_cards(document=document_payload, video=dict(video))
        quality = self.qa_agent.review_delivery(
            {
                "webhook_url": self.config.teams_webhook_url,
                "cards": cards,
            }
        )
        delivery_status = quality.status()
        self.repository.save_quality_check(
            stage="teams_publisher.preflight",
            entity_type="document",
            entity_id=article_id,
            status=delivery_status,
            findings=[finding.to_dict() for finding in quality.findings],
            score=quality.score,
            raw_response=quality.raw_response,
        )
        if not quality.passed:
            self._export_delivery_payload(video["youtube_video_id"], cards, delivery_status)
            self.repository.save_delivery(
                article_id=article_id,
                destination="teams",
                provider="incoming_webhook",
                external_id=None,
                payload={"cards": cards},
                status=delivery_status,
                last_error="Preflight failed",
            )
            return article_id

        external_ids = [self.teams_client.post(card) for card in cards]
        self._export_delivery_payload(video["youtube_video_id"], cards, "success")
        self.repository.save_delivery(
            article_id=article_id,
            destination="teams",
            provider="incoming_webhook",
            external_id=",".join(filter(None, external_ids)) or str(len(cards)),
            payload={"cards": cards},
            status="success",
            sent_at=utc_now(),
        )
        return article_id

    def _export_delivery_payload(self, youtube_video_id: str, cards: list[dict], status: str) -> None:
        base_dir = self.config.storage_dir / youtube_video_id
        write_json(
            base_dir / "delivery.teams.json",
            {
                "status": status,
                "cards": cards,
            },
        )
