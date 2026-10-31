"""Rule definitions for industrial motor fault detection.

Covers ISO 10816 vibration thresholds, thermal limits, overcurrent conditions,
voltage deviations, acoustic anomalies, and multi-sensor compound rules.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional
from config import FaultThresholds, settings
from src.models.telemetry import FaultEvent, MotorTelemetry


class BaseFaultRule(ABC):
    """Abstract base class for all telemetry evaluation rules."""

    def __init__(self, rule_name: str, fault_type: str) -> None:
        self.rule_name = rule_name
        self.fault_type = fault_type

    @abstractmethod
    def evaluate(self, telemetry: MotorTelemetry, thresholds: FaultThresholds) -> Optional[FaultEvent]:
        """Evaluate telemetry reading. Return FaultEvent if rule is violated, else None."""
        pass


class HighTemperatureRule(BaseFaultRule):
    """Detects casing or bearing overheating exceeding thermal limits."""

    def __init__(self) -> None:
        super().__init__("High Temperature Rule", "OVERHEATING")

    def evaluate(self, telemetry: MotorTelemetry, thresholds: FaultThresholds) -> Optional[FaultEvent]:
        temp = telemetry.temperature
        if temp >= thresholds.temp_critical:
            return FaultEvent(
                fault_id=f"{telemetry.device_id}_{self.fault_type}",
                device_id=telemetry.device_id,
                timestamp=telemetry.timestamp,
                fault_type=self.fault_type,
                severity="CRITICAL",
                metric_name="temperature",
                metric_value=round(temp, 2),
                threshold_value=thresholds.temp_critical,
                message=(
                    f"CRITICAL: Temperature {temp:.1f}°C exceeds critical threshold "
                    f"({thresholds.temp_critical}°C). Immediate shutdown or load reduction advised."
                )
            )
        elif temp >= thresholds.temp_warning:
            return FaultEvent(
                fault_id=f"{telemetry.device_id}_{self.fault_type}",
                device_id=telemetry.device_id,
                timestamp=telemetry.timestamp,
                fault_type=self.fault_type,
                severity="WARNING",
                metric_name="temperature",
                metric_value=round(temp, 2),
                threshold_value=thresholds.temp_warning,
                message=(
                    f"WARNING: Temperature {temp:.1f}°C exceeds warning threshold "
                    f"({thresholds.temp_warning}°C). Inspect cooling fan and lubrication."
                )
            )
        return None


class HighVibrationRule(BaseFaultRule):
    """Detects mechanical vibration anomalies according to ISO 10816 standards."""

    def __init__(self) -> None:
        super().__init__("High Vibration Rule", "BEARING_WEAR")

    def evaluate(self, telemetry: MotorTelemetry, thresholds: FaultThresholds) -> Optional[FaultEvent]:
        vib = telemetry.vibration
        if vib >= thresholds.vibration_critical:
            return FaultEvent(
                fault_id=f"{telemetry.device_id}_{self.fault_type}",
                device_id=telemetry.device_id,
                timestamp=telemetry.timestamp,
                fault_type=self.fault_type,
                severity="CRITICAL",
                metric_name="vibration",
                metric_value=round(vib, 2),
                threshold_value=thresholds.vibration_critical,
                message=(
                    f"CRITICAL: Vibration velocity {vib:.2f} mm/s violates ISO 10816 Zone D "
                    f"(limit: {thresholds.vibration_critical} mm/s). Severe unbalance or bearing spalling."
                )
            )
        elif vib >= thresholds.vibration_warning:
            return FaultEvent(
                fault_id=f"{telemetry.device_id}_{self.fault_type}",
                device_id=telemetry.device_id,
                timestamp=telemetry.timestamp,
                fault_type=self.fault_type,
                severity="WARNING",
                metric_name="vibration",
                metric_value=round(vib, 2),
                threshold_value=thresholds.vibration_warning,
                message=(
                    f"WARNING: Vibration velocity {vib:.2f} mm/s exceeds advisory limit "
                    f"({thresholds.vibration_warning} mm/s). Schedule shaft alignment and bearing check."
                )
            )
        return None


class OvercurrentRule(BaseFaultRule):
    """Detects electrical motor overcurrent relative to motor rated amperage."""

    def __init__(self) -> None:
        super().__init__("Overcurrent Rule", "ELECTRICAL_OVERLOAD")

    def evaluate(self, telemetry: MotorTelemetry, thresholds: FaultThresholds) -> Optional[FaultEvent]:
        rated_current = float(telemetry.metadata.get("rated_current", 25.0))
        current = telemetry.current
        critical_limit = rated_current * 1.35
        warning_limit = rated_current * 1.15

        if current >= critical_limit:
            return FaultEvent(
                fault_id=f"{telemetry.device_id}_{self.fault_type}",
                device_id=telemetry.device_id,
                timestamp=telemetry.timestamp,
                fault_type=self.fault_type,
                severity="CRITICAL",
                metric_name="current",
                metric_value=round(current, 2),
                threshold_value=round(critical_limit, 2),
                message=(
                    f"CRITICAL: Phase current {current:.1f}A is 35%+ over rated ({rated_current:.1f}A). "
                    f"Risk of winding insulation breakdown or rotor lock."
                )
            )
        elif current >= warning_limit:
            return FaultEvent(
                fault_id=f"{telemetry.device_id}_{self.fault_type}",
                device_id=telemetry.device_id,
                timestamp=telemetry.timestamp,
                fault_type=self.fault_type,
                severity="WARNING",
                metric_name="current",
                metric_value=round(current, 2),
                threshold_value=round(warning_limit, 2),
                message=(
                    f"WARNING: Current {current:.1f}A exceeds 115% rated ({rated_current:.1f}A). "
                    f"Mechanical drag or mild overload detected."
                )
            )
        return None


class VoltageSagRule(BaseFaultRule):
    """Detects low AC supply voltage causing current surges and thermal stress."""

    def __init__(self) -> None:
        super().__init__("Voltage Sag Rule", "VOLTAGE_SAG")

    def evaluate(self, telemetry: MotorTelemetry, thresholds: FaultThresholds) -> Optional[FaultEvent]:
        volt = telemetry.voltage
        if volt <= thresholds.voltage_low_critical and volt > 10.0:
            return FaultEvent(
                fault_id=f"{telemetry.device_id}_{self.fault_type}",
                device_id=telemetry.device_id,
                timestamp=telemetry.timestamp,
                fault_type=self.fault_type,
                severity="CRITICAL",
                metric_name="voltage",
                metric_value=round(volt, 2),
                threshold_value=thresholds.voltage_low_critical,
                message=(
                    f"CRITICAL: Voltage sag to {volt:.1f}V (critical min: {thresholds.voltage_low_critical}V). "
                    f"Power quality failure may trigger inverter trip."
                )
            )
        elif volt <= thresholds.voltage_low_warning and volt > 10.0:
            return FaultEvent(
                fault_id=f"{telemetry.device_id}_{self.fault_type}",
                device_id=telemetry.device_id,
                timestamp=telemetry.timestamp,
                fault_type=self.fault_type,
                severity="WARNING",
                metric_name="voltage",
                metric_value=round(volt, 2),
                threshold_value=thresholds.voltage_low_warning,
                message=(
                    f"WARNING: Low line voltage {volt:.1f}V below nominal threshold "
                    f"({thresholds.voltage_low_warning}V). Check grid feeder or bus bar."
                )
            )
        return None


class AcousticAnomalyRule(BaseFaultRule):
    """Detects abnormal high-frequency noise from mechanical friction or cavitation."""

    def __init__(self) -> None:
        super().__init__("Acoustic Anomaly Rule", "ACOUSTIC_ANOMALY")

    def evaluate(self, telemetry: MotorTelemetry, thresholds: FaultThresholds) -> Optional[FaultEvent]:
        noise = telemetry.acoustic_db
        if noise >= thresholds.acoustic_critical:
            return FaultEvent(
                fault_id=f"{telemetry.device_id}_{self.fault_type}",
                device_id=telemetry.device_id,
                timestamp=telemetry.timestamp,
                fault_type=self.fault_type,
                severity="CRITICAL",
                metric_name="acoustic_db",
                metric_value=round(noise, 2),
                threshold_value=thresholds.acoustic_critical,
                message=(
                    f"CRITICAL: Acoustic noise {noise:.1f} dB exceeds safety limit "
                    f"({thresholds.acoustic_critical} dB). Cavitation or metal-on-metal contact suspected."
                )
            )
        elif noise >= thresholds.acoustic_warning:
            return FaultEvent(
                fault_id=f"{telemetry.device_id}_{self.fault_type}",
                device_id=telemetry.device_id,
                timestamp=telemetry.timestamp,
                fault_type=self.fault_type,
                severity="WARNING",
                metric_name="acoustic_db",
                metric_value=round(noise, 2),
                threshold_value=thresholds.acoustic_warning,
                message=(
                    f"WARNING: High acoustic emissions {noise:.1f} dB (warning: {thresholds.acoustic_warning} dB). "
                    f"Check pump inlet or bearing raceway."
                )
            )
        return None


class CompoundBearingFailureRule(BaseFaultRule):
    """Detects simultaneous elevated vibration AND temperature, indicating imminent bearing seizure."""

    def __init__(self) -> None:
        super().__init__("Compound Bearing Failure Rule", "COMPOUND_BEARING_FAILURE")

    def evaluate(self, telemetry: MotorTelemetry, thresholds: FaultThresholds) -> Optional[FaultEvent]:
        # Triggers when both vibration is elevated (> 5.5 mm/s) and temp is elevated (> 80.0°C)
        if telemetry.vibration >= 5.5 and telemetry.temperature >= 80.0:
            return FaultEvent(
                fault_id=f"{telemetry.device_id}_{self.fault_type}",
                device_id=telemetry.device_id,
                timestamp=telemetry.timestamp,
                fault_type=self.fault_type,
                severity="CRITICAL",
                metric_name="vibration+temperature",
                metric_value=round(telemetry.vibration, 2),
                threshold_value=5.5,
                message=(
                    f"CRITICAL COMPOUND FAULT: Simultaneous high vibration ({telemetry.vibration:.2f} mm/s) "
                    f"and casing heat ({telemetry.temperature:.1f}°C). Imminent bearing seizure risk! "
                    f"Immediate maintenance required."
                )
            )
        return None
