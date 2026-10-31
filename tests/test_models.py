"""Unit tests for telemetry models and validation."""

from datetime import datetime, timezone
import pytest
from pydantic import ValidationError
from src.models.telemetry import FaultEvent, MotorTelemetry


def test_motor_telemetry_valid():
    reading = MotorTelemetry(
        device_id="MOTOR-PUMP-01",
        temperature=55.2,
        vibration=1.85,
        current=24.0,
        voltage=230.0,
        rpm=1450.0,
        acoustic_db=68.5,
        pressure_bar=4.2
    )
    assert reading.device_id == "MOTOR-PUMP-01"
    assert reading.temperature == 55.2
    assert reading.state == "NORMAL"
    assert reading.timestamp is not None

    json_str = reading.to_json_str()
    assert "MOTOR-PUMP-01" in json_str

    deserialized = MotorTelemetry.from_raw_json(json_str)
    assert deserialized.device_id == reading.device_id
    assert deserialized.temperature == reading.temperature


def test_motor_telemetry_validation_errors():
    # Temperature out of bounds
    with pytest.raises(ValidationError):
        MotorTelemetry(
            device_id="MOTOR-PUMP-01",
            temperature=999.0,  # exceeds le=250.0
            vibration=1.0,
            current=10.0,
            voltage=230.0,
            rpm=1000.0,
            acoustic_db=60.0
        )

    # Negative vibration
    with pytest.raises(ValidationError):
        MotorTelemetry(
            device_id="MOTOR-PUMP-01",
            temperature=50.0,
            vibration=-5.0,  # ge=0.0
            current=10.0,
            voltage=230.0,
            rpm=1000.0,
            acoustic_db=60.0
        )


def test_fault_event_creation():
    fault = FaultEvent(
        fault_id="MOTOR-PUMP-01_OVERHEATING",
        device_id="MOTOR-PUMP-01",
        fault_type="OVERHEATING",
        severity="CRITICAL",
        metric_name="temperature",
        metric_value=94.5,
        threshold_value=90.0,
        message="Critical overheating detected."
    )
    assert fault.severity == "CRITICAL"
    assert fault.occurrence_count == 1
    assert fault.status == "ACTIVE"
