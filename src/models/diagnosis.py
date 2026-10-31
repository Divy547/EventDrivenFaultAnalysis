"""Pydantic schemas for validated AI fault diagnosis and conversational troubleshooting."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field, field_validator


class DocumentSourceReference(BaseModel):
    """Verifiable source citation from technical manuals."""

    doc_name: str = Field(..., description="Filename of the technical documentation")
    page_number: int = Field(..., ge=1, description="Page number where the text excerpt is located")
    chunk_id: int = Field(..., ge=0, description="Index of the chunk in the document")
    excerpt: str = Field(..., min_length=5, description="Exact or condensed excerpt from manual")
    similarity_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Cosine similarity score from TF-IDF vector retrieval"
    )


class QualifiedConfidence(BaseModel):
    """Standardized confidence score with rigorous engineering justification."""

    level: Literal["HIGH", "MEDIUM", "LOW"] = Field(..., description="Qualitative rating")
    score: float = Field(..., ge=0.0, le=1.0, description="Normalized confidence score (0.0 - 1.0)")
    explanation: str = Field(..., min_length=10, description="Justification for confidence determination")


class StructuredFaultDiagnosis(BaseModel):
    """Validated structured diagnosis output for equipment faults."""

    fault_title: str = Field(..., min_length=3, description="Technical classification of the fault")
    severity: Literal["CRITICAL", "WARNING", "INFORMATIONAL"] = Field(..., description="Operational severity")
    device_id: str = Field(..., description="Target industrial motor identifier")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp of diagnosis creation in UTC"
    )
    observations: list[str] = Field(
        ...,
        min_length=1,
        description="Direct empirical sensor measurements and threshold deviations"
    )
    possible_causes: list[str] = Field(
        ...,
        min_length=1,
        description="Mechanisms of failure grounded in technical literature"
    )
    recommended_actions: list[str] = Field(
        ...,
        min_length=1,
        description="Step-by-step corrective maintenance and safety procedures"
    )
    evidence: list[str] = Field(
        ...,
        min_length=1,
        description="Correlation between empirical telemetry and cited manual criteria"
    )
    sources: list[DocumentSourceReference] = Field(
        default_factory=list,
        description="Verifiable document source citations (empty if no manuals match)"
    )
    qualified_confidence: QualifiedConfidence = Field(
        ...,
        description="Qualified confidence rating and rationale"
    )
    is_verified: bool = Field(
        default=False,
        description="Always False for algorithmic diagnosis until confirmed by a certified field technician"
    )
    verification_status: str = Field(
        default="Preliminary (Pending Physical Inspection)",
        description="Explicit notice that diagnosis requires physical confirmation"
    )
    engine_used: str = Field(
        ...,
        description="Identifies the inference model or deterministic fallback engine"
    )
    fallback_reason: Optional[str] = Field(
        default=None,
        description="Explicit explanation if deterministic demo fallback was engaged"
    )

    @field_validator("timestamp", mode="before")
    @classmethod
    def parse_timestamp(cls, value: Any) -> datetime:
        if isinstance(value, str):
            try:
                dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
                return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except ValueError:
                pass
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc)


class ChatMessage(BaseModel):
    """Message item in conversational troubleshooting session."""

    role: Literal["user", "assistant", "system"] = Field(...)
    content: str = Field(..., min_length=1)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    sources: list[DocumentSourceReference] = Field(default_factory=list)
    engine_used: Optional[str] = Field(default=None)
    fallback_reason: Optional[str] = Field(default=None)
