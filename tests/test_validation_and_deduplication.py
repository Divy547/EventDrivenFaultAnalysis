"""Comprehensive test suite for telemetry validation, threshold detection, fault deduplication, and RAG retrieval."""

from datetime import datetime, timezone
from pathlib import Path
import pytest
from pydantic import ValidationError

from config import FaultThresholds
from src.database.db_manager import DatabaseManager
from src.fault_detection.detector import FaultDetector
from src.knowledge.pdf_processor import PDFProcessor
from src.knowledge.tfidf_index import TFIDFIndex
from src.models.diagnosis import DocumentSourceReference
from src.models.telemetry import FaultEvent, MotorTelemetry


# ============================================================================
# 1. TELEMETRY VALIDATION TESTS
# ============================================================================

def test_telemetry_valid_boundaries():
    """Verify standard boundary limits for industrial sensors."""
    reading = MotorTelemetry(
        device_id="MOTOR-PUMP-01",
        timestamp="2026-10-31T14:00:00Z",
        temperature=74.9,
        vibration=4.49,
        current=28.0,
        voltage=230.0,
        rpm=1450.0,
        acoustic_db=84.9,
        pressure_bar=4.2,
        power_factor=0.88
    )
    assert reading.device_id == "MOTOR-PUMP-01"
    assert reading.temperature == 74.9
    assert reading.timestamp.tzinfo == timezone.utc


def test_telemetry_timestamp_formats():
    """Ensure timestamp parser correctly converts epochs, ISO strings, and datetimes to UTC."""
    # From epoch timestamp
    r1 = MotorTelemetry(
        device_id="MOTOR-TEST",
        timestamp=1700000000.0,
        temperature=50.0,
        vibration=1.5,
        current=20.0,
        voltage=230.0,
        rpm=1450.0,
        acoustic_db=65.0
    )
    assert r1.timestamp.tzinfo == timezone.utc

    # From ISO string with Z
    r2 = MotorTelemetry(
        device_id="MOTOR-TEST",
        timestamp="2026-10-31T12:30:00Z",
        temperature=50.0,
        vibration=1.5,
        current=20.0,
        voltage=230.0,
        rpm=1450.0,
        acoustic_db=65.0
    )
    assert r2.timestamp.hour == 12
    assert r2.timestamp.tzinfo == timezone.utc


def test_telemetry_invalid_ranges():
    """Verify pydantic raises ValidationError for out-of-range sensor values."""
    # Temperature above 250°C
    with pytest.raises(ValidationError):
        MotorTelemetry(
            device_id="MOTOR-PUMP-01",
            temperature=251.0,
            vibration=1.0,
            current=10.0,
            voltage=230.0,
            rpm=1450.0,
            acoustic_db=60.0
        )

    # Negative vibration velocity
    with pytest.raises(ValidationError):
        MotorTelemetry(
            device_id="MOTOR-PUMP-01",
            temperature=50.0,
            vibration=-1.0,
            current=10.0,
            voltage=230.0,
            rpm=1450.0,
            acoustic_db=60.0
        )

    # Invalid power factor > 1.0
    with pytest.raises(ValidationError):
        MotorTelemetry(
            device_id="MOTOR-PUMP-01",
            temperature=50.0,
            vibration=1.0,
            current=10.0,
            voltage=230.0,
            rpm=1450.0,
            acoustic_db=60.0,
            power_factor=1.5
        )


# ============================================================================
# 2. THRESHOLD DETECTION TESTS
# ============================================================================

@pytest.fixture
def test_detector(tmp_path):
    db = DatabaseManager(db_path=tmp_path / "detector_rules_test.db")
    thresholds = FaultThresholds(
        deduplication_window_sec=60.0,
        temp_warning=75.0,
        temp_critical=90.0,
        vibration_warning=4.5,
        vibration_critical=7.1,
        voltage_low_warning=207.0,
        voltage_low_critical=195.0,
        acoustic_warning=85.0,
        acoustic_critical=95.0
    )
    return FaultDetector(db_manager=db, thresholds=thresholds)


def test_temperature_warning_and_critical_thresholds(test_detector):
    base_kwargs = dict(
        device_id="MOTOR-PUMP-01",
        vibration=1.5,
        current=25.0,
        voltage=230.0,
        rpm=1450.0,
        acoustic_db=65.0,
        metadata={"rated_current": 28.0}
    )

    # Normal: 74°C
    s_norm, f_norm = test_detector.analyze_telemetry(MotorTelemetry(temperature=74.0, **base_kwargs))
    assert s_norm == "NORMAL"
    assert len(f_norm) == 0

    # Warning: 76°C
    s_warn, f_warn = test_detector.analyze_telemetry(MotorTelemetry(temperature=76.0, **base_kwargs))
    assert s_warn == "WARNING"
    assert len(f_warn) == 1
    assert f_warn[0].severity == "WARNING"
    assert f_warn[0].fault_type == "OVERHEATING"

    # Critical: 91°C
    s_crit, f_crit = test_detector.analyze_telemetry(MotorTelemetry(temperature=91.0, **base_kwargs))
    assert s_crit == "CRITICAL"
    assert len(f_crit) == 1
    assert f_crit[0].severity == "CRITICAL"


def test_vibration_iso_10816_zones(test_detector):
    base_kwargs = dict(
        device_id="MOTOR-CONV-02",
        temperature=50.0,
        current=20.0,
        voltage=230.0,
        rpm=1470.0,
        acoustic_db=65.0,
        metadata={"rated_current": 21.0}
    )

    # Warning (Zone C): 4.8 mm/s
    s_warn, f_warn = test_detector.analyze_telemetry(MotorTelemetry(vibration=4.8, **base_kwargs))
    assert s_warn == "WARNING"
    assert any(f.fault_type == "BEARING_WEAR" and f.severity == "WARNING" for f in f_warn)

    # Critical (Zone D): 7.5 mm/s
    s_crit, f_crit = test_detector.analyze_telemetry(MotorTelemetry(vibration=7.5, **base_kwargs))
    assert s_crit == "CRITICAL"
    assert any(f.fault_type == "BEARING_WEAR" and f.severity == "CRITICAL" for f in f_crit)


def test_electrical_overcurrent_and_voltage_sag(test_detector):
    # Rated current 28A -> Warning at 28*1.15 = 32.2A, Critical at 28*1.35 = 37.8A
    reading_oc = MotorTelemetry(
        device_id="MOTOR-PUMP-01",
        temperature=55.0,
        vibration=1.5,
        current=38.5,  # Exceeds 37.8A critical limit
        voltage=230.0,
        rpm=1450.0,
        acoustic_db=65.0,
        metadata={"rated_current": 28.0}
    )
    s_oc, f_oc = test_detector.analyze_telemetry(reading_oc)
    assert s_oc == "CRITICAL"
    assert any(f.fault_type == "ELECTRICAL_OVERLOAD" and f.severity == "CRITICAL" for f in f_oc)

    # Voltage Sag: 190V (below 195V critical)
    reading_sag = MotorTelemetry(
        device_id="MOTOR-PUMP-01",
        temperature=55.0,
        vibration=1.5,
        current=25.0,
        voltage=190.0,
        rpm=1450.0,
        acoustic_db=65.0,
        metadata={"rated_current": 28.0}
    )
    s_sag, f_sag = test_detector.analyze_telemetry(reading_sag)
    assert any(f.fault_type == "VOLTAGE_SAG" and f.severity == "CRITICAL" for f in f_sag)


# ============================================================================
# 3. FAULT DEDUPLICATION & LIFECYCLE TESTS
# ============================================================================

def test_deduplication_cooldown_window(test_detector):
    """Ensure repeated abnormal readings within deduplication window do not duplicate database records."""
    t0 = datetime(2026, 10, 31, 14, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 10, 31, 14, 0, 10, tzinfo=timezone.utc)  # +10s (inside 60s window)
    t2 = datetime(2026, 10, 31, 14, 0, 20, tzinfo=timezone.utc)  # +20s

    base = dict(
        device_id="MOTOR-COMP-03",
        temperature=50.0,
        vibration=7.6,  # Critical vibration
        current=38.0,
        voltage=230.0,
        rpm=2960.0,
        acoustic_db=70.0,
        metadata={"rated_current": 41.0}
    )

    # Reading 1
    _, faults_1 = test_detector.analyze_telemetry(MotorTelemetry(timestamp=t0, **base))
    assert len(faults_1) == 1
    assert faults_1[0].occurrence_count == 1

    # Reading 2 (+10s)
    _, faults_2 = test_detector.analyze_telemetry(MotorTelemetry(timestamp=t1, **base))
    assert len(faults_2) == 1
    assert faults_2[0].occurrence_count == 2
    assert faults_2[0].last_detected == t1

    # Reading 3 (+20s)
    _, faults_3 = test_detector.analyze_telemetry(MotorTelemetry(timestamp=t2, **base))
    assert len(faults_3) == 1
    assert faults_3[0].occurrence_count == 3
    assert faults_3[0].last_detected == t2

    # Verify only ONE active fault row exists in SQLite despite 3 triggers
    active_in_db = test_detector.db.get_active_faults("MOTOR-COMP-03")
    assert len(active_in_db) == 1
    assert active_in_db[0]["occurrence_count"] == 3


def test_auto_recovery_and_manual_resolution(test_detector):
    """Test auto-recovery when metrics return to safe range and manual resolution with technician notes."""
    # 1. Trigger temperature fault
    t0 = datetime(2026, 10, 31, 14, 0, 0, tzinfo=timezone.utc)
    test_detector.analyze_telemetry(MotorTelemetry(
        device_id="MOTOR-PUMP-01",
        timestamp=t0,
        temperature=80.0,
        vibration=1.5,
        current=25.0,
        voltage=230.0,
        rpm=1450.0,
        acoustic_db=65.0
    ))
    assert len(test_detector.db.get_active_faults("MOTOR-PUMP-01")) == 1

    # 2. Reading returns to normal (52°C) -> Should auto-resolve
    t1 = datetime(2026, 10, 31, 14, 0, 5, tzinfo=timezone.utc)
    test_detector.analyze_telemetry(MotorTelemetry(
        device_id="MOTOR-PUMP-01",
        timestamp=t1,
        temperature=52.0,
        vibration=1.5,
        current=25.0,
        voltage=230.0,
        rpm=1450.0,
        acoustic_db=65.0
    ))
    assert len(test_detector.db.get_active_faults("MOTOR-PUMP-01")) == 0

    # 3. Trigger manual fault and resolve with technician note
    f_id = "TEST_MANUAL_FAULT"
    fault = FaultEvent(
        fault_id=f_id,
        device_id="MOTOR-PUMP-01",
        fault_type="TEST_FAULT",
        severity="WARNING",
        metric_name="current",
        metric_value=35.0,
        threshold_value=30.0,
        message="Manual test fault"
    )
    test_detector.db.insert_or_update_fault(fault)
    test_detector.resolve_fault(f_id, technician_note="Replaced contactor", technician_name="Alice Smith")

    logs = test_detector.db.get_maintenance_logs("MOTOR-PUMP-01")
    assert len(logs) >= 1
    assert logs[0]["technician"] == "Alice Smith"
    assert "Replaced contactor" in logs[0]["notes"]


# ============================================================================
# 4. RAG RETRIEVAL & GROUNDING TESTS
# ============================================================================

def test_rag_retrieval_ranking_and_source_references(tmp_path):
    """Test TF-IDF semantic retrieval over industrial motor manuals."""
    pdf_path = tmp_path / "iso_standards.pdf"
    PDFProcessor.generate_sample_manual(pdf_path)

    processor = PDFProcessor()
    meta, chunks = processor.process_pdf_with_metadata(pdf_path, "iso_standards.pdf")

    index = TFIDFIndex()
    index.build_index(chunks)
    assert index.total_chunks >= 4

    # Query for ISO 10816 criteria
    sources = index.search_source_references("ISO 10816 vibration Zone D limit", top_k=2)
    assert len(sources) >= 1
    top = sources[0]

    assert isinstance(top, DocumentSourceReference)
    assert top.doc_name == "iso_standards.pdf"
    assert top.page_number >= 1
    assert "Zone D" in top.excerpt or "10816" in top.excerpt
    assert top.similarity_score > 0.05

    # Test zero hallucination: search for completely unrelated terms (e.g. quantum biology)
    unrelated = index.search_source_references("photosynthetic quantum entanglement in plants", min_score=0.25)
    assert len(unrelated) == 0  # Does not invent or fabricate false citations
