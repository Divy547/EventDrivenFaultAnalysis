"""Unit tests for SQLite database manager."""

import tempfile
from datetime import datetime, timezone
from pathlib import Path
import pytest

from src.database.db_manager import DatabaseManager
from src.models.telemetry import FaultEvent, MotorTelemetry


@pytest.fixture
def temp_db(tmp_path):
    db_path = tmp_path / "test_iot.db"
    return DatabaseManager(db_path=db_path)


def test_insert_and_get_telemetry(temp_db):
    reading = MotorTelemetry(
        device_id="MOTOR-PUMP-01",
        temperature=52.0,
        vibration=1.5,
        current=25.0,
        voltage=230.0,
        rpm=1450.0,
        acoustic_db=65.0
    )
    row_id = temp_db.insert_telemetry(reading)
    assert row_id > 0

    recent = temp_db.get_recent_telemetry("MOTOR-PUMP-01", limit=10)
    assert len(recent) == 1
    assert recent[0]["device_id"] == "MOTOR-PUMP-01"
    assert recent[0]["temperature"] == 52.0


def test_fault_lifecycle_and_deduplication(temp_db):
    fault = FaultEvent(
        fault_id="MOTOR-TEST_OVERHEAT",
        device_id="MOTOR-TEST",
        fault_type="OVERHEATING",
        severity="WARNING",
        metric_name="temperature",
        metric_value=76.5,
        threshold_value=75.0,
        message="Warning temperature"
    )

    # Initial insert
    created = temp_db.insert_or_update_fault(fault)
    assert created is True

    # Active faults check
    active = temp_db.get_active_faults("MOTOR-TEST")
    assert len(active) == 1
    assert active[0]["occurrence_count"] == 1

    # Second occurrence update
    fault.metric_value = 79.0
    fault.last_detected = datetime.now(timezone.utc)
    updated = temp_db.insert_or_update_fault(fault)
    assert updated is False  # Updated existing

    active = temp_db.get_active_faults("MOTOR-TEST")
    assert len(active) == 1
    assert active[0]["occurrence_count"] == 2
    assert active[0]["metric_value"] == 79.0

    # Resolve fault with technician name and notes
    res = temp_db.resolve_fault(
        "MOTOR-TEST_OVERHEAT",
        technician_note="Cleaned cooling fan and verified grease port",
        technician_name="Senior Engineer Bob"
    )
    assert res is True

    # Check maintenance log
    logs = temp_db.get_maintenance_logs("MOTOR-TEST")
    assert len(logs) == 1
    assert logs[0]["technician"] == "Senior Engineer Bob"
    assert "Cleaned cooling fan" in logs[0]["notes"]

    # No more active faults
    active = temp_db.get_active_faults("MOTOR-TEST")
    assert len(active) == 0

    # Present in history as RESOLVED
    hist = temp_db.get_fault_history("MOTOR-TEST", status="RESOLVED")
    assert len(hist) == 1
    assert hist[0]["status"] == "RESOLVED"


def test_fleet_summary(temp_db):
    temp_db.insert_telemetry(MotorTelemetry(
        device_id="MOTOR-PUMP-01",
        temperature=52.0,
        vibration=1.5,
        current=25.0,
        voltage=230.0,
        rpm=1450.0,
        acoustic_db=65.0
    ))
    summary = temp_db.get_fleet_summary(["MOTOR-PUMP-01", "MOTOR-CONV-02"])
    assert len(summary["devices"]) == 2
    assert summary["fleet_health_score"] == 100
    pump_info = next(d for d in summary["devices"] if d["device_id"] == "MOTOR-PUMP-01")
    assert pump_info["health_status"] == "OPERATIONAL"
    conv_info = next(d for d in summary["devices"] if d["device_id"] == "MOTOR-CONV-02")
    assert conv_info["health_status"] == "STANDBY"
