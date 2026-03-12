from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any, Dict, List

from ..config import AppConfig
from ..prompts import ARTICLE_SYSTEM_PROMPT

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None  # type: ignore[assignment]

try:
    from faster_whisper import WhisperModel
except ImportError:  # pragma: no cover
    WhisperModel = None  # type: ignore[assignment]


STOPWORDS = {
    "그리고",
    "그런데",
    "하지만",
    "그러니까",
    "이제",
    "지금",
    "때문에",
    "영상",
    "채널",
    "펀무법인",
    "정리",
    "설명",
    "부분",
    "내용",
    "문제",
    "경우",
    "관련",
    "대한",
    "이런",
    "저런",
    "그거",
    "이거",
    "저희",
    "여기",
}


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
        self._whisper_model = None

    def transcribe_audio(self, audio_path: str) -> Dict[str, Any]:
        if not self.client:
            return self._transcribe_audio_locally(audio_path)
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
            return self._build_article_package_locally(video=video, transcript=transcript)

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

    def _transcribe_audio_locally(self, audio_path: str) -> Dict[str, Any]:
        if WhisperModel is None:
            raise RuntimeError(
                "No transcription backend is configured. Install faster-whisper or set OPENAI_API_KEY."
            )
        if self._whisper_model is None:
            self._whisper_model = WhisperModel(
                self.config.local_transcribe_model,
                device="cpu",
                compute_type=self.config.local_transcribe_compute_type,
            )
        segments_iter, info = self._whisper_model.transcribe(
            audio_path,
            language="ko",
            beam_size=1,
            vad_filter=True,
        )
        segments: List[Dict[str, Any]] = []
        texts: List[str] = []
        for segment in segments_iter:
            text = str(segment.text).strip()
            if not text:
                continue
            texts.append(text)
            segments.append(
                {
                    "start_sec": float(segment.start),
                    "end_sec": float(segment.end),
                    "text": text,
                }
            )
        return {
            "text": "\n".join(texts),
            "segments": segments,
            "language": getattr(info, "language", "ko"),
        }

    def _build_article_package_locally(self, *, video: Dict[str, Any], transcript: Dict[str, Any]) -> Dict[str, Any]:
        sentences = self._extract_sentences(transcript["text"])
        keywords = self._top_keywords(transcript["text"])
        keyword_phrase = ", ".join(keywords[:4]) if keywords else "핵심 쟁점"
        quotes = self._pick_quotes(transcript["segments"])
        lead = sentences[0] if sentences else f"{video['title']} 내용을 다루는 영상이다."
        middle = sentences[min(len(sentences) // 2, max(len(sentences) - 1, 0))] if sentences else lead
        tail = sentences[-1] if sentences else lead

        paragraphs = [
            f"펀무법인 채널에 올라온 '{video['title']}' 영상은 {keyword_phrase}를 중심으로 내용을 풀어간다. 초반 전개에서는 {self._to_statement(lead)}.",
            f"영상에서 직접 눈에 띄는 대목은 \"{quotes[0]}\"라는 말이다. 설명의 축이 처음부터 비교적 분명하게 잡혀 있다는 점이 드러난다.",
            f"중반부에는 {self._to_statement(middle)}. 같은 흐름 안에서 {keyword_phrase}가 어떻게 이어지는지 차례로 짚는 방식이다.",
            f"후반부에는 \"{quotes[1]}\"라는 언급이 나온다. 전체적으로 보면 {self._to_statement(tail)}. 영상은 쟁점을 나열하는 데서 그치지 않고 실제 판단 포인트가 어디에 놓이는지를 정리하는 구성에 가깝다.",
        ]
        body = "\n\n".join(self._clean_spacing(paragraph) for paragraph in paragraphs)
        body = body[:4800].rstrip()
        summary_parts = [self._clean_spacing(sentence) for sentence in sentences[:2] if sentence]
        summary = " ".join(summary_parts)[:280].strip() or f"{keyword_phrase}를 다룬 영상이다."

        payload = {
            "headline": self._fallback_headline(video["title"], keywords),
            "summary": summary,
            "body": body,
            "sources": [
                {
                    "title": video["title"],
                    "url": video["youtube_url"],
                    "note": "원문 영상",
                }
            ],
            "captures": self._fallback_capture_points(transcript["segments"], int(video["duration_sec"])),
        }
        payload["captures"] = self._normalize_captures(
            payload["captures"],
            transcript["segments"],
            int(video["duration_sec"]),
        )
        return payload

    @staticmethod
    def _extract_sentences(text: str) -> List[str]:
        normalized = re.sub(r"\s+", " ", text).strip()
        if not normalized:
            return []
        chunks = re.split(r"(?<=[\.\?!])\s+|(?<=다\.)\s+|(?<=요\.)\s+|\n+", normalized)
        cleaned = []
        seen = set()
        for chunk in chunks:
            sentence = chunk.strip().strip('"')
            if len(sentence) < 12:
                continue
            if sentence in seen:
                continue
            seen.add(sentence)
            cleaned.append(sentence)
        return cleaned[:12]

    @staticmethod
    def _top_keywords(text: str, limit: int = 6) -> List[str]:
        tokens = re.findall(r"[가-힣A-Za-z]{2,}", text)
        counter = Counter(token.lower() for token in tokens if token not in STOPWORDS and len(token) >= 2)
        return [token for token, _count in counter.most_common(limit)]

    @staticmethod
    def _pick_quotes(segments: List[Dict[str, Any]]) -> List[str]:
        picks: List[str] = []
        for segment in segments:
            text = OpenAIService._clean_spacing(str(segment.get("text") or ""))
            if not (18 <= len(text) <= 90):
                continue
            if text in picks:
                continue
            picks.append(text)
            if len(picks) == 2:
                break
        while len(picks) < 2:
            picks.append("영상에서 핵심 쟁점을 직접 설명하는 대목이다.")
        return picks

    @staticmethod
    def _fallback_headline(title: str, keywords: List[str]) -> str:
        clean_title = re.sub(r"\s+", " ", title).strip()
        if keywords:
            return f"{clean_title}, {keywords[0]} 쟁점 짚은 영상"
        return f"{clean_title}, 핵심 쟁점 짚은 영상"

    @staticmethod
    def _to_statement(sentence: str) -> str:
        text = OpenAIService._clean_spacing(sentence).rstrip(". ")
        text = re.sub(r"(입니다|있습니다|같습니다)$", "이다", text)
        if not text.endswith("다"):
            text = text + "다"
        return text

    @staticmethod
    def _clean_spacing(text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()

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
