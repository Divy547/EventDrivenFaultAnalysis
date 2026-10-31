"""Global singleton service container for P_311.

Ensures long-running background threads (MQTT client, Simulator) and databases
are initialized once and remain persistent across Streamlit re-renders.
"""

from __future__ import annotations

import logging
from typing import Optional

from config import settings
from src.database.db_manager import DatabaseManager
from src.fault_detection.detector import FaultDetector
from src.knowledge.ai_assistant import DiagnosticAssistant
from src.mqtt.mqtt_client import MQTTManager
from src.simulator.motor_simulator import MotorSimulator

logger = logging.getLogger(__name__)


class ServiceContainer:
    """Thread-safe container holding core application services."""

    def __init__(self) -> None:
        self.db = DatabaseManager()
        self.detector = FaultDetector(db_manager=self.db)
        self.mqtt = MQTTManager(db_manager=self.db, fault_detector=self.detector)
        self.assistant = DiagnosticAssistant(db_manager=self.db)
        self.simulator = MotorSimulator(
            interval_sec=settings.simulator.interval_sec,
            on_reading_generated=self._on_simulator_reading
        )
        self._initialized = False

    def _on_simulator_reading(self, reading) -> None:
        """Route reading from simulator through MQTT manager (live or fallback)."""
        self.mqtt.publish_telemetry(reading)

    def start_all(self) -> None:
        """Start background services."""
        if self._initialized:
            return

        # Start MQTT manager (and fallback worker)
        self.mqtt.start()

        # Start simulator if auto_start is true
        if settings.simulator.auto_start:
            self.simulator.start()

        self._initialized = True
        logger.info("All P_311 background services started")

    def stop_all(self) -> None:
        """Stop all background workers gracefully."""
        self.simulator.stop()
        self.mqtt.stop()
        self._initialized = False
        logger.info("All P_311 background services stopped")


# Singleton instance
_container: Optional[ServiceContainer] = None


def get_services() -> ServiceContainer:
    """Retrieve or initialize global service container."""
    global _container
    if _container is None:
        _container = ServiceContainer()
        _container.start_all()
    return _container
