from __future__ import annotations

import json
from typing import Any, Dict, List

from .config import AppConfig
from .models import QualityFinding, QualityResult
from .prompts import BANNED_ARTICLE_PHRASES, QUALITY_SYSTEM_PROMPT

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None  # type: ignore[assignment]


class QualityAgent:
    def __init__(self, config: AppConfig):
        self.config = config
        self.client = OpenAI(api_key=config.openai_api_key) if OpenAI and config.openai_api_key else None

    def review_video(self, payload: Dict[str, Any]) -> QualityResult:
        findings: List[QualityFinding] = []
        if not payload.get("youtube_video_id"):
            findings.append(QualityFinding(code="video_id_missing", message="youtube_video_id가 비어 있다."))
        if not payload.get("title"):
            findings.append(QualityFinding(code="title_missing", message="영상 제목이 비어 있다."))
        if not payload.get("youtube_url"):
            findings.append(QualityFinding(code="url_missing", message="영상 URL이 비어 있다."))
        if int(payload.get("duration_sec") or 0) <= 0:
            findings.append(QualityFinding(code="duration_invalid", message="영상 길이를 확인하지 못했다."))
        if payload.get("is_short"):
            findings.append(QualityFinding(code="short_filtered", message="Shorts로 분류된 영상이다."))
        result = self._maybe_llm_review("video", payload, findings)
        return result

    def review_transcript(self, payload: Dict[str, Any]) -> QualityResult:
        findings: List[QualityFinding] = []
        text = (payload.get("text") or "").strip()
        segments = payload.get("segments") or []
        if len(text) < 200:
            findings.append(QualityFinding(code="transcript_too_short", message="전사 길이가 너무 짧다."))
        if not segments:
            findings.append(QualityFinding(code="segments_missing", message="타임스탬프 세그먼트가 없다.", severity="warning"))
        result = self._maybe_llm_review("transcript", payload, findings)
        return result

    def review_article(self, payload: Dict[str, Any]) -> QualityResult:
        findings: List[QualityFinding] = []
        body = (payload.get("body") or "").strip()
        captures = payload.get("captures") or []
        headline = (payload.get("headline") or "").strip()
        if not headline:
            findings.append(QualityFinding(code="headline_missing", message="기사 제목이 비어 있다."))
        if not body:
            findings.append(QualityFinding(code="body_missing", message="기사 본문이 비어 있다."))
        if len(body) > 5000:
            findings.append(QualityFinding(code="body_too_long", message="기사 길이가 5000자를 넘는다."))
        for phrase in BANNED_ARTICLE_PHRASES:
            if phrase in body:
                findings.append(QualityFinding(code="banned_phrase", message=f"금지 표현이 포함돼 있다: {phrase}"))
        if len(captures) != 3:
            findings.append(QualityFinding(code="capture_count_invalid", message="캡처는 정확히 3개여야 한다."))
        result = self._maybe_llm_review("article", payload, findings)
        return result

    def review_delivery(self, payload: Dict[str, Any]) -> QualityResult:
        findings: List[QualityFinding] = []
        captures = payload.get("captures") or []
        if not payload.get("webhook_url"):
            findings.append(QualityFinding(code="webhook_missing", message="Teams webhook URL이 비어 있다."))
        if not payload.get("card"):
            findings.append(QualityFinding(code="card_missing", message="Teams 카드 payload가 없다."))
        if len(captures) != 3:
            findings.append(QualityFinding(code="captures_missing", message="Teams 송출 전 캡처 3개가 준비돼야 한다."))
        elif any(not capture.get("public_url") for capture in captures):
            findings.append(
                QualityFinding(
                    code="public_url_missing",
                    message="Teams incoming webhook에는 공개 이미지 URL이 필요하다.",
                )
            )
        result = self._maybe_llm_review("delivery", payload, findings)
        return result

    def _maybe_llm_review(
        self,
        stage: str,
        payload: Dict[str, Any],
        heuristic_findings: List[QualityFinding],
    ) -> QualityResult:
        llm_findings: List[QualityFinding] = []
        raw_response: Dict[str, Any] | None = None

        if self.client:
            schema = {
                "name": "quality_review",
                "schema": {
                    "type": "object",
                    "properties": {
                        "passed": {"type": "boolean"},
                        "score": {"type": "number"},
                        "findings": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "code": {"type": "string"},
                                    "message": {"type": "string"},
                                    "severity": {"type": "string"},
                                },
                                "required": ["code", "message", "severity"],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "required": ["passed", "score", "findings"],
                    "additionalProperties": False,
                },
            }
            response = self.client.responses.create(
                model=self.config.openai_qa_model,
                input=[
                    {"role": "system", "content": QUALITY_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": json.dumps(
                            {"stage": stage, "payload": payload},
                            ensure_ascii=False,
                        ),
                    },
                ],
                text={"format": {"type": "json_schema", "name": schema["name"], "schema": schema["schema"]}},
            )
            raw_response = {"output_text": response.output_text}
            parsed = json.loads(response.output_text)
            llm_findings = [QualityFinding(**item) for item in parsed["findings"]]
            passed = parsed["passed"] and not heuristic_findings
            score = float(parsed["score"])
        else:
            passed = not heuristic_findings
            score = 1.0 if passed else 0.0

        combined = [*heuristic_findings, *llm_findings]
        return QualityResult(
            stage=stage,
            passed=passed and not combined,
            findings=combined,
            score=score,
            raw_response=raw_response,
        )
