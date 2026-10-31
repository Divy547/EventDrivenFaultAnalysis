"""Data models for telemetry and fault events with strict validation."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Literal
from pydantic import BaseModel, Field, field_validator


class MotorTelemetry(BaseModel):
    """Telemetry packet emitted by industrial motor sensors."""

    device_id: str = Field(..., description="Unique industrial motor identifier")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Reading timestamp in UTC"
    )
    temperature: float = Field(..., ge=-40.0, le=250.0, description="Motor casing/bearing temperature in °C")
    vibration: float = Field(..., ge=0.0, le=100.0, description="Overall vibration velocity RMS in mm/s")
    current: float = Field(..., ge=0.0, le=500.0, description="RMS phase current in Amperes")
    voltage: float = Field(..., ge=0.0, le=600.0, description="RMS line-to-line/line-to-neutral voltage in Volts")
    rpm: float = Field(..., ge=0.0, le=10000.0, description="Motor rotational speed in RPM")
    acoustic_db: float = Field(..., ge=20.0, le=160.0, description="Acoustic sensor measurement in dB")
    pressure_bar: float | None = Field(default=None, ge=0.0, le=100.0, description="Discharge or fluid pressure in bar")
    power_factor: float = Field(default=0.88, ge=0.1, le=1.0, description="Electrical power factor")
    state: Literal["NORMAL", "WARNING", "CRITICAL"] = Field(
        default="NORMAL",
        description="Assigned health status"
    )
    metadata: dict[str, Any] = Field(default_factory=dict, description="Device metadata and specs")

    @field_validator("timestamp", mode="before")
    @classmethod
    def parse_timestamp(cls, value: Any) -> datetime:
        if isinstance(value, str):
            # Parse ISO 8601 strings
            try:
                dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    return dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                pass
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=timezone.utc)
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value
        return datetime.now(timezone.utc)

    def to_json_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary with ISO timestamps."""
        data = self.model_dump()
        data["timestamp"] = self.timestamp.isoformat()
        return data

    def to_json_str(self) -> str:
        """Convert directly to JSON string."""
        return json.dumps(self.to_json_dict())

    @classmethod
    def from_raw_json(cls, raw: str | bytes | dict[str, Any]) -> MotorTelemetry:
        """Parse raw JSON string, bytes, or dictionary into MotorTelemetry."""
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8")
        if isinstance(raw, str):
            parsed = json.loads(raw)
        else:
            parsed = raw
        return cls(**parsed)


class FaultEvent(BaseModel):
    """Detected equipment fault or anomaly alert."""

    fault_id: str = Field(..., description="Unique fault event identifier")
    device_id: str = Field(..., description="Target device identifier")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Alert creation timestamp"
    )
    fault_type: str = Field(..., description="Category: OVERHEATING, BEARING_WEAR, OVERCURRENT, etc.")
    severity: Literal["WARNING", "CRITICAL"] = Field(..., description="Alert severity level")
    metric_name: str = Field(..., description="Triggering metric (e.g., vibration, temperature)")
    metric_value: float = Field(..., description="Observed measurement value")
    threshold_value: float = Field(..., description="Violated rule threshold value")
    message: str = Field(..., description="Human-readable fault description and recommendation")
    status: Literal["ACTIVE", "ACKNOWLEDGED", "RESOLVED"] = Field(
        default="ACTIVE",
        description="Fault resolution lifecycle state"
    )
    occurrence_count: int = Field(default=1, ge=1, description="Deduplicated trigger count")
    first_detected: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="First occurrence timestamp"
    )
    last_detected: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Most recent occurrence timestamp"
    )
    resolved_at: datetime | None = Field(default=None, description="Resolution timestamp")

    @field_validator("timestamp", "first_detected", "last_detected", "resolved_at", mode="before")
    @classmethod
    def parse_datetimes(cls, value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, str):
            try:
                dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
                return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except ValueError:
                pass
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=timezone.utc)
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return None
