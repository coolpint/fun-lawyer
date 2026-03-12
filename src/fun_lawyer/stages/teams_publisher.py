from __future__ import annotations

import json

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
        article = self.repository.get_article_by_id(article_id)
        if not article:
            raise RuntimeError(f"Article not found: {article_id}")
        video = self.repository.get_video(int(article["video_id"]))
        if not video:
            raise RuntimeError(f"Video not found for article: {article_id}")

        article_payload = dict(article)
        article_payload["captures"] = json.loads(article["captures_json"])
        card = self.teams_client.build_article_card(article=article_payload, video=dict(video))
        quality = self.qa_agent.review_delivery(
            {
                "webhook_url": self.config.teams_webhook_url,
                "card": card,
                "captures": article_payload["captures"],
            }
        )
        delivery_status = quality.status()
        self.repository.save_quality_check(
            stage="teams_publisher.preflight",
            entity_type="article",
            entity_id=article_id,
            status=delivery_status,
            findings=[finding.to_dict() for finding in quality.findings],
            score=quality.score,
            raw_response=quality.raw_response,
        )
        if not quality.passed:
            self.repository.save_delivery(
                article_id=article_id,
                destination="teams",
                provider="incoming_webhook",
                external_id=None,
                payload=card,
                status=delivery_status,
                last_error="Preflight failed",
            )
            return article_id

        external_id = self.teams_client.post(card)
        self.repository.save_delivery(
            article_id=article_id,
            destination="teams",
            provider="incoming_webhook",
            external_id=external_id,
            payload=card,
            status="success",
            sent_at=utc_now(),
        )
        return article_id
