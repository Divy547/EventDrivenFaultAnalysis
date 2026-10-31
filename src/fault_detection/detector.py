"""Configurable Fault Detection Engine with stateful deduplication.

Evaluates multi-sensor telemetry against engineering rules, manages
alert lifecycles, and prevents alert flooding via deduplication windows.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Callable, Optional

from config import FaultThresholds, settings
from src.database.db_manager import DatabaseManager
from src.fault_detection.rules import (
    AcousticAnomalyRule,
    BaseFaultRule,
    CompoundBearingFailureRule,
    HighTemperatureRule,
    HighVibrationRule,
    OvercurrentRule,
    VoltageSagRule,
)
from src.models.telemetry import FaultEvent, MotorTelemetry

logger = logging.getLogger(__name__)


class FaultDetector:
    """Stateful fault detector executing rule chains with deduplication."""

    def __init__(
        self,
        db_manager: Optional[DatabaseManager] = None,
        thresholds: Optional[FaultThresholds] = None,
        on_new_fault_callback: Optional[Callable[[FaultEvent], None]] = None
    ) -> None:
        self.db = db_manager or DatabaseManager()
        self.thresholds = thresholds or settings.thresholds
        self.on_new_fault = on_new_fault_callback

        # In-memory deduplication cache: fault_id -> FaultEvent
        self._active_faults_cache: dict[str, FaultEvent] = {}

        # Default rules pipeline
        self.rules: list[BaseFaultRule] = [
            CompoundBearingFailureRule(),
            HighTemperatureRule(),
            HighVibrationRule(),
            OvercurrentRule(),
            VoltageSagRule(),
            AcousticAnomalyRule(),
        ]

    def register_rule(self, rule: BaseFaultRule) -> None:
        """Register a custom detection rule into the evaluation pipeline."""
        self.rules.append(rule)

    def analyze_telemetry(self, telemetry: MotorTelemetry) -> tuple[str, list[FaultEvent]]:
        """Evaluate telemetry across all rules with deduplication.

        Returns:
            Tuple of (overall_status: 'NORMAL'|'WARNING'|'CRITICAL', detected_faults: list[FaultEvent])
        """
        now = telemetry.timestamp
        detected_events: list[FaultEvent] = []
        overall_severity: str = "NORMAL"

        for rule in self.rules:
            event = rule.evaluate(telemetry, self.thresholds)
            if not event:
                continue

            # Check if this rule severity upgrades overall status
            if event.severity == "CRITICAL":
                overall_severity = "CRITICAL"
            elif event.severity == "WARNING" and overall_severity != "CRITICAL":
                overall_severity = "WARNING"

            # Deduplication logic
            fault_id = event.fault_id
            cached_event = self._active_faults_cache.get(fault_id)

            if cached_event and cached_event.status == "ACTIVE":
                # Check deduplication window
                time_since_last = (now - cached_event.last_detected).total_seconds()
                if time_since_last <= self.thresholds.deduplication_window_sec:
                    # Update existing event in cache and database
                    cached_event.occurrence_count += 1
                    cached_event.last_detected = now
                    cached_event.metric_value = event.metric_value
                    cached_event.message = event.message
                    self.db.insert_or_update_fault(cached_event)
                    detected_events.append(cached_event)
                    continue

            # New fault event or outside deduplication window
            event.first_detected = now
            event.last_detected = now
            event.occurrence_count = 1
            event.status = "ACTIVE"

            self._active_faults_cache[fault_id] = event
            self.db.insert_or_update_fault(event)
            detected_events.append(event)

            # Trigger external callback if registered
            if self.on_new_fault:
                try:
                    self.on_new_fault(event)
                except Exception as exc:
                    logger.error("Error executing on_new_fault callback: %s", exc)

        # Update telemetry object state
        telemetry.state = overall_severity

        # Automatically check if previously active faults for this device have recovered
        self._check_auto_recovery(telemetry)

        return overall_severity, detected_events

    def _check_auto_recovery(self, telemetry: MotorTelemetry) -> None:
        """Check if previously triggered faults for this device have returned to normal."""
        device_id = telemetry.device_id

        # Temperature recovery
        temp_fault_id = f"{device_id}_OVERHEATING"
        if temp_fault_id in self._active_faults_cache:
            if telemetry.temperature < self.thresholds.temp_warning:
                self.resolve_fault(temp_fault_id, "Auto-resolved: Temperature returned to normal operational range")

        # Vibration recovery
        vib_fault_id = f"{device_id}_BEARING_WEAR"
        if vib_fault_id in self._active_faults_cache:
            if telemetry.vibration < self.thresholds.vibration_warning:
                self.resolve_fault(vib_fault_id, "Auto-resolved: Vibration levels returned within ISO 10816 limits")

    def resolve_fault(
        self,
        fault_id: str,
        technician_note: str = "Resolved",
        technician_name: str = "Field Technician"
    ) -> bool:
        """Explicitly resolve a fault."""
        if fault_id in self._active_faults_cache:
            self._active_faults_cache[fault_id].status = "RESOLVED"
            self._active_faults_cache[fault_id].resolved_at = datetime.now(timezone.utc)
            del self._active_faults_cache[fault_id]

        return self.db.resolve_fault(fault_id, technician_note, technician_name=technician_name)

    def acknowledge_fault(self, fault_id: str) -> bool:
        """Acknowledge a fault."""
        if fault_id in self._active_faults_cache:
            self._active_faults_cache[fault_id].status = "ACKNOWLEDGED"
        return self.db.acknowledge_fault(fault_id)

    def update_thresholds(self, **kwargs) -> None:
        """Dynamically update threshold values at runtime."""
        for key, value in kwargs.items():
            if hasattr(self.thresholds, key):
                setattr(self.thresholds, key, float(value))
