from __future__ import annotations

import json
from typing import Any, Dict, List
from urllib.request import Request, urlopen

from ..config import AppConfig


class TeamsWebhookClient:
    def __init__(self, config: AppConfig):
        self.config = config

    def build_status_card(self, *, title: str, lines: List[str]) -> Dict[str, Any]:
        body_blocks: List[Dict[str, Any]] = [
            {
                "type": "TextBlock",
                "text": title,
                "wrap": True,
                "weight": "Bolder",
                "size": "Large",
            }
        ]
        for line in lines:
            body_blocks.append(
                {
                    "type": "TextBlock",
                    "text": line,
                    "wrap": True,
                    "spacing": "Medium",
                }
            )
        return {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": {
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "msteams": {"width": "Full"},
                        "body": body_blocks,
                    },
                }
            ],
        }

    def build_document_cards(self, *, document: Dict[str, Any], video: Dict[str, Any]) -> List[Dict[str, Any]]:
        chunks = self._chunk_text(document["body"])
        cards: List[Dict[str, Any]] = []
        total = len(chunks)
        for index, chunk in enumerate(chunks, start=1):
            title = video["title"] if total == 1 else f"{video['title']} ({index}/{total})"
            body_blocks: List[Dict[str, Any]] = [
                {
                    "type": "TextBlock",
                    "text": title,
                    "wrap": True,
                    "weight": "Bolder",
                    "size": "Large",
                },
                {
                    "type": "TextBlock",
                    "text": chunk,
                    "wrap": True,
                    "spacing": "Medium",
                },
            ]
            if index == total:
                body_blocks.append(
                    {
                        "type": "TextBlock",
                        "text": f"링크\n{video['youtube_url']}",
                        "wrap": True,
                        "spacing": "Medium",
                    }
                )
            cards.append(
                {
                    "type": "message",
                    "attachments": [
                        {
                            "contentType": "application/vnd.microsoft.card.adaptive",
                            "content": {
                                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                                "type": "AdaptiveCard",
                                "version": "1.4",
                                "msteams": {"width": "Full"},
                                "body": body_blocks,
                            },
                        }
                    ],
                }
            )
        return cards

    @staticmethod
    def _chunk_text(text: str, max_chars: int = 2200) -> List[str]:
        paragraphs = [paragraph.strip() for paragraph in text.split("\n\n") if paragraph.strip()]
        if not paragraphs:
            return [text.strip() or "(빈 스크립트)"]

        chunks: List[str] = []
        current: List[str] = []
        current_length = 0
        for paragraph in paragraphs:
            paragraph_length = len(paragraph)
            if current and current_length + paragraph_length + 2 > max_chars:
                chunks.append("\n\n".join(current))
                current = [paragraph]
                current_length = paragraph_length
                continue
            current.append(paragraph)
            current_length += paragraph_length + (2 if current_length else 0)
        if current:
            chunks.append("\n\n".join(current))
        return chunks

    def post(self, payload: Dict[str, Any]) -> str:
        webhook_url = self.config.require("teams_webhook_url")
        request = Request(
            webhook_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request) as response:
            return response.read().decode("utf-8").strip()
