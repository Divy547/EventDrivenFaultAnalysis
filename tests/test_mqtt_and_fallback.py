"""Unit tests for MQTT client and local fallback mode."""

import tempfile
import time
from pathlib import Path
import pytest

from config import MQTTConfig
from src.database.db_manager import DatabaseManager
from src.fault_detection.detector import FaultDetector
from src.models.telemetry import MotorTelemetry
from src.mqtt.mqtt_client import MQTTManager


def test_local_fallback_ingestion(tmp_path):
    db = DatabaseManager(db_path=tmp_path / "test_mqtt.db")
    detector = FaultDetector(db_manager=db)

    # Force local fallback by disabling MQTT connection
    cfg = MQTTConfig(enabled=False, fallback_if_unavailable=True)
    mqtt_mgr = MQTTManager(config=cfg, db_manager=db, fault_detector=detector)
    mqtt_mgr.start()

    assert mqtt_mgr.is_fallback_mode is True

    # Publish reading through manager
    reading = MotorTelemetry(
        device_id="MOTOR-PUMP-01",
        temperature=51.5,
        vibration=1.7,
        current=26.0,
        voltage=230.0,
        rpm=1450.0,
        acoustic_db=67.0
    )
    ok = mqtt_mgr.publish_telemetry(reading)
    assert ok is True

    # Wait briefly for worker queue to process
    time.sleep(0.3)

    # Confirm persisted into database
    recs = db.get_recent_telemetry("MOTOR-PUMP-01")
    assert len(recs) == 1
    assert recs[0]["device_id"] == "MOTOR-PUMP-01"

    mqtt_mgr.stop()
