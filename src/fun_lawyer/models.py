from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List


class EntityStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    QA_FAILED = "qa_failed"


class JobType(str, Enum):
    TRANSCRIBE = "transcribe"
    BUILD_ARTICLE = "build_article"
    PUBLISH_TEAMS = "publish_teams"


@dataclass
class CaptureFrame:
    timestamp_sec: int
    path: str
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp_sec": self.timestamp_sec,
            "path": self.path,
            "note": self.note,
        }


@dataclass
class QualityFinding:
    code: str
    message: str
    severity: str = "error"

    def to_dict(self) -> Dict[str, str]:
        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
        }


@dataclass
class QualityResult:
    stage: str
    passed: bool
    findings: List[QualityFinding] = field(default_factory=list)
    score: float | None = None
    raw_response: Dict[str, Any] | None = None

    def status(self) -> str:
        return EntityStatus.SUCCESS.value if self.passed else EntityStatus.QA_FAILED.value
