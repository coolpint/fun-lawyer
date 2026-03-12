from __future__ import annotations

import json
from typing import Any, Dict, List
from urllib.request import Request, urlopen

from ..config import AppConfig


class TeamsWebhookClient:
    def __init__(self, config: AppConfig):
        self.config = config

    def build_article_card(self, *, article: Dict[str, Any], video: Dict[str, Any]) -> Dict[str, Any]:
        captures = article.get("captures") or []
        body_blocks: List[Dict[str, Any]] = [
            {
                "type": "TextBlock",
                "text": article["headline"],
                "wrap": True,
                "weight": "Bolder",
                "size": "Large",
            },
            {
                "type": "TextBlock",
                "text": article.get("summary", ""),
                "wrap": True,
                "spacing": "Medium",
            },
            {
                "type": "TextBlock",
                "text": article["body"],
                "wrap": True,
                "spacing": "Medium",
            },
        ]

        for capture in captures:
            public_url = capture.get("public_url")
            if not public_url:
                continue
            body_blocks.append(
                {
                    "type": "Image",
                    "url": public_url,
                    "altText": capture.get("note", "영상 캡처"),
                    "size": "Stretch",
                    "spacing": "Medium",
                }
            )

        body_blocks.append(
            {
                "type": "FactSet",
                "facts": [
                    {"title": "영상", "value": video["title"]},
                    {"title": "링크", "value": video["youtube_url"]},
                ],
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
