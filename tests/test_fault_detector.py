"""Unit tests for rule-based fault detector and deduplication."""

import tempfile
from pathlib import Path
import pytest

from config import FaultThresholds
from src.database.db_manager import DatabaseManager
from src.fault_detection.detector import FaultDetector
from src.models.telemetry import MotorTelemetry


@pytest.fixture
def detector(tmp_path):
    db = DatabaseManager(db_path=tmp_path / "detector_test.db")
    thresholds = FaultThresholds(
        deduplication_window_sec=60.0,
        temp_warning=75.0,
        temp_critical=90.0,
        vibration_warning=4.5,
        vibration_critical=7.1
    )
    return FaultDetector(db_manager=db, thresholds=thresholds)


def test_normal_telemetry(detector):
    reading = MotorTelemetry(
        device_id="MOTOR-PUMP-01",
        temperature=50.0,
        vibration=1.5,
        current=25.0,
        voltage=230.0,
        rpm=1450.0,
        acoustic_db=65.0,
        metadata={"rated_current": 28.0}
    )
    status, faults = detector.analyze_telemetry(reading)
    assert status == "NORMAL"
    assert len(faults) == 0


def test_temperature_fault_and_deduplication(detector):
    reading_warn = MotorTelemetry(
        device_id="MOTOR-PUMP-01",
        temperature=78.0,
        vibration=1.5,
        current=25.0,
        voltage=230.0,
        rpm=1450.0,
        acoustic_db=65.0,
        metadata={"rated_current": 28.0}
    )
    status, faults = detector.analyze_telemetry(reading_warn)
    assert status == "WARNING"
    assert len(faults) == 1
    assert faults[0].fault_type == "OVERHEATING"
    assert faults[0].occurrence_count == 1

    # Second reading within deduplication window
    reading_crit = MotorTelemetry(
        device_id="MOTOR-PUMP-01",
        temperature=92.0,
        vibration=1.5,
        current=25.0,
        voltage=230.0,
        rpm=1450.0,
        acoustic_db=65.0,
        metadata={"rated_current": 28.0}
    )
    status2, faults2 = detector.analyze_telemetry(reading_crit)
    assert status2 == "CRITICAL"
    assert len(faults2) == 1
    assert faults2[0].occurrence_count == 2  # Deduplicated increment


def test_compound_bearing_failure(detector):
    # Both vibration and temperature elevated
    reading = MotorTelemetry(
        device_id="MOTOR-COMP-03",
        temperature=85.0,
        vibration=6.2,
        current=35.0,
        voltage=230.0,
        rpm=2950.0,
        acoustic_db=78.0,
        metadata={"rated_current": 41.0}
    )
    status, faults = detector.analyze_telemetry(reading)
    assert status == "CRITICAL"
    types = [f.fault_type for f in faults]
    assert "COMPOUND_BEARING_FAILURE" in types
