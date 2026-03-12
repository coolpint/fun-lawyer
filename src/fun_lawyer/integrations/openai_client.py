from __future__ import annotations

import json
from typing import Any, Dict, List

from ..config import AppConfig
from ..prompts import ARTICLE_SYSTEM_PROMPT

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None  # type: ignore[assignment]


def _article_schema() -> Dict[str, Any]:
    return {
        "name": "article_package",
        "schema": {
            "type": "object",
            "properties": {
                "headline": {"type": "string"},
                "summary": {"type": "string"},
                "body": {"type": "string"},
                "sources": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "url": {"type": "string"},
                            "note": {"type": "string"},
                        },
                        "required": ["title", "url", "note"],
                        "additionalProperties": False,
                    },
                },
                "captures": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "timestamp_sec": {"type": "integer"},
                            "note": {"type": "string"},
                        },
                        "required": ["timestamp_sec", "note"],
                        "additionalProperties": False,
                    },
                    "minItems": 3,
                    "maxItems": 3,
                },
            },
            "required": ["headline", "summary", "body", "sources", "captures"],
            "additionalProperties": False,
        },
    }


class OpenAIService:
    def __init__(self, config: AppConfig):
        self.config = config
        if not OpenAI or not config.openai_api_key:
            self.client = None
        else:
            self.client = OpenAI(api_key=config.openai_api_key)

    def transcribe_audio(self, audio_path: str) -> Dict[str, Any]:
        if not self.client:
            raise RuntimeError("OpenAI client is not configured.")
        with open(audio_path, "rb") as audio_file:
            response = self.client.audio.transcriptions.create(
                model=self.config.openai_transcribe_model,
                file=audio_file,
                response_format="verbose_json",
                timestamp_granularities=["segment"],
            )
        segments = [
            {
                "start_sec": float(segment.start),
                "end_sec": float(segment.end),
                "text": str(segment.text).strip(),
            }
            for segment in getattr(response, "segments", []) or []
        ]
        return {
            "text": str(response.text).strip(),
            "segments": segments,
            "language": getattr(response, "language", None),
        }

    def build_article_package(self, *, video: Dict[str, Any], transcript: Dict[str, Any]) -> Dict[str, Any]:
        if not self.client:
            raise RuntimeError("OpenAI client is not configured.")

        schema = _article_schema()
        user_payload = {
            "video": {
                "title": video["title"],
                "youtube_url": video["youtube_url"],
                "published_at": video["published_at"],
                "duration_sec": video["duration_sec"],
            },
            "transcript": {
                "text": transcript["text"],
                "segments": transcript["segments"],
            },
        }
        try:
            response = self.client.responses.create(
                model=self.config.openai_article_model,
                tools=[{"type": "web_search_preview"}],
                input=[
                    {"role": "system", "content": ARTICLE_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": json.dumps(user_payload, ensure_ascii=False),
                    },
                ],
                text={"format": {"type": "json_schema", "name": schema["name"], "schema": schema["schema"]}},
            )
        except Exception:
            response = self.client.responses.create(
                model=self.config.openai_article_model,
                input=[
                    {"role": "system", "content": ARTICLE_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": json.dumps(user_payload, ensure_ascii=False),
                    },
                ],
                text={"format": {"type": "json_schema", "name": schema["name"], "schema": schema["schema"]}},
            )

        payload = json.loads(response.output_text)
        payload["captures"] = self._normalize_captures(
            payload.get("captures") or [],
            transcript["segments"],
            int(video["duration_sec"]),
        )
        return payload

    @staticmethod
    def _normalize_captures(
        captures: List[Dict[str, Any]],
        segments: List[Dict[str, Any]],
        duration_sec: int,
    ) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        seen: set[int] = set()
        for item in captures:
            timestamp = max(0, int(item.get("timestamp_sec") or 0))
            if duration_sec:
                timestamp = min(duration_sec, timestamp)
            if timestamp in seen:
                continue
            seen.add(timestamp)
            normalized.append({"timestamp_sec": timestamp, "note": str(item.get("note") or "").strip()})
            if len(normalized) == 3:
                break

        if len(normalized) == 3:
            return normalized

        fallback_points = OpenAIService._fallback_capture_points(segments, duration_sec)
        for item in fallback_points:
            timestamp = item["timestamp_sec"]
            if timestamp in seen:
                continue
            seen.add(timestamp)
            normalized.append(item)
            if len(normalized) == 3:
                break
        return normalized[:3]

    @staticmethod
    def _fallback_capture_points(
        segments: List[Dict[str, Any]],
        duration_sec: int,
    ) -> List[Dict[str, Any]]:
        if segments:
            indices = [0, len(segments) // 2, max(len(segments) - 1, 0)]
            return [
                {
                    "timestamp_sec": int(float(segments[index]["start_sec"])),
                    "note": f"본문 핵심 장면 {position}",
                }
                for position, index in enumerate(indices, start=1)
            ]
        if not duration_sec:
            return [
                {"timestamp_sec": 5, "note": "본문 핵심 장면 1"},
                {"timestamp_sec": 15, "note": "본문 핵심 장면 2"},
                {"timestamp_sec": 25, "note": "본문 핵심 장면 3"},
            ]
        checkpoints = [max(1, duration_sec // 6), max(2, duration_sec // 2), max(3, (duration_sec * 5) // 6)]
        return [
            {"timestamp_sec": point, "note": f"본문 핵심 장면 {position}"}
            for position, point in enumerate(checkpoints, start=1)
        ]
