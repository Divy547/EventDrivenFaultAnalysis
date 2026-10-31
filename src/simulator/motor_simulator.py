"""Industrial multi-motor sensor simulator.

Simulates three distinct industrial motors with realistic physical telemetry,
dynamic operating scenarios, stochastic sensor noise, and fault injection.
"""

from __future__ import annotations

import logging
import math
import random
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from config import settings
from src.models.telemetry import MotorTelemetry

logger = logging.getLogger(__name__)


@dataclass
class MotorProfile:
    """Specification and baseline parameters for an industrial motor."""

    device_id: str
    name: str
    motor_type: str
    rated_kw: float
    rated_current: float
    nominal_rpm: float
    nominal_voltage: float = 230.0
    nominal_temp: float = 50.0
    nominal_vibration: float = 1.8
    nominal_acoustic: float = 68.0
    nominal_pressure: Optional[float] = None
    nominal_power_factor: float = 0.88
    active_scenario: str = "NORMAL"
    step_counter: int = 0


# Industrial 3-Motor Catalog
DEFAULT_MOTORS: dict[str, MotorProfile] = {
    "MOTOR-PUMP-01": MotorProfile(
        device_id="MOTOR-PUMP-01",
        name="Primary Coolant Centrifugal Pump",
        motor_type="Centrifugal Pump Induction Motor",
        rated_kw=15.0,
        rated_current=28.0,
        nominal_rpm=1450.0,
        nominal_voltage=230.0,
        nominal_temp=52.0,
        nominal_vibration=1.8,
        nominal_acoustic=68.0,
        nominal_pressure=4.2,
        nominal_power_factor=0.88,
    ),
    "MOTOR-CONV-02": MotorProfile(
        device_id="MOTOR-CONV-02",
        name="Raw Material Incline Belt Conveyor",
        motor_type="Heavy-Duty Incline Conveyor Motor",
        rated_kw=11.0,
        rated_current=21.0,
        nominal_rpm=1470.0,
        nominal_voltage=230.0,
        nominal_temp=58.0,
        nominal_vibration=2.2,
        nominal_acoustic=72.0,
        nominal_pressure=None,
        nominal_power_factor=0.85,
    ),
    "MOTOR-COMP-03": MotorProfile(
        device_id="MOTOR-COMP-03",
        name="High-Pressure Rotary Screw Compressor",
        motor_type="Twin-Screw Air Compressor Motor",
        rated_kw=22.0,
        rated_current=41.0,
        nominal_rpm=2960.0,
        nominal_voltage=230.0,
        nominal_temp=65.0,
        nominal_vibration=2.5,
        nominal_acoustic=76.0,
        nominal_pressure=7.5,
        nominal_power_factor=0.90,
    ),
}

AVAILABLE_SCENARIOS = [
    "NORMAL",
    "OVERHEATING",
    "BEARING_WEAR",
    "ELECTRICAL_OVERLOAD",
    "VOLTAGE_SAG",
    "COMPOUND_FAILURE",
    "CAVITATION",
]


class MotorSimulator:
    """Multi-device sensor telemetry generator with realistic degradation curves."""

    def __init__(
        self,
        interval_sec: float | None = None,
        on_reading_generated: Optional[Callable[[MotorTelemetry], None]] = None
    ) -> None:
        self.interval_sec = interval_sec or settings.simulator.interval_sec
        self.on_reading = on_reading_generated
        self.motors: dict[str, MotorProfile] = {
            k: MotorProfile(**v.__dict__) for k, v in DEFAULT_MOTORS.items()
        }

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def set_scenario(self, device_id: str, scenario: str) -> bool:
        """Change the active operational scenario for a specific motor."""
        with self._lock:
            if device_id in self.motors and scenario in AVAILABLE_SCENARIOS:
                self.motors[device_id].active_scenario = scenario
                self.motors[device_id].step_counter = 0
                logger.info("Motor %s switched to scenario: %s", device_id, scenario)
                return True
            return False

    def get_motor_status(self) -> list[dict[str, Any]]:
        """Return status overview of all simulated motors."""
        with self._lock:
            return [
                {
                    "device_id": m.device_id,
                    "name": m.name,
                    "type": m.motor_type,
                    "rated_kw": m.rated_kw,
                    "rated_current": m.rated_current,
                    "active_scenario": m.active_scenario,
                }
                for m in self.motors.values()
            ]

    def generate_reading(self, device_id: str) -> MotorTelemetry:
        """Synthesize next time-series reading for a motor based on its active scenario."""
        motor = self.motors[device_id]
        motor.step_counter += 1
        step = motor.step_counter

        # Base nominal operating parameters
        temp = motor.nominal_temp + random.gauss(0, 0.4)
        vibration = motor.nominal_vibration + random.gauss(0, 0.08)
        current = (motor.rated_current * 0.90) + random.gauss(0, 0.3)
        voltage = motor.nominal_voltage + random.gauss(0, 0.8)
        rpm = motor.nominal_rpm + random.gauss(0, 3.0)
        acoustic = motor.nominal_acoustic + random.gauss(0, 0.5)
        pressure = (motor.nominal_pressure + random.gauss(0, 0.05)) if motor.nominal_pressure else None
        pf = motor.nominal_power_factor + random.gauss(0, 0.005)

        scenario = motor.active_scenario

        # Realistic physics based on fault scenario
        if scenario == "OVERHEATING":
            # Progressive thermal rise up to 96°C
            ramp = min(step * 1.5, 42.0)
            temp += ramp
            acoustic += min(step * 0.3, 8.0)
            current += min(step * 0.15, 3.0)  # Thermal resistance rise

        elif scenario == "BEARING_WEAR":
            # Progressive vibration escalation with high frequency harmonics
            ramp = min(step * 0.28, 6.5)
            vibration += ramp + (0.5 * math.sin(step * 0.8))
            acoustic += min(step * 0.7, 18.0)
            temp += min(step * 0.4, 15.0)  # Mechanical friction

        elif scenario == "ELECTRICAL_OVERLOAD":
            # Severe load spike (jam or mechanical resistance)
            overload_mult = 1.38 + random.uniform(0.02, 0.08)
            current = motor.rated_current * overload_mult
            rpm -= min(step * 8.0, 150.0)  # Slip increases under overload
            temp += min(step * 0.9, 32.0)
            voltage -= min(step * 0.2, 5.0)

        elif scenario == "VOLTAGE_SAG":
            # Grid feeder sag
            voltage = 192.0 + random.gauss(0, 1.2)
            # Motor draws extra current to deliver same shaft power P = V * I * pf * sqrt(3)
            current = (motor.rated_current * 1.22) + random.gauss(0, 0.4)
            temp += min(step * 0.5, 18.0)

        elif scenario == "COMPOUND_FAILURE":
            # Unlubricated bearing seizure: both violent vibration AND excessive heat
            vibration = 7.8 + min(step * 0.2, 4.0) + random.gauss(0, 0.2)
            temp = 86.0 + min(step * 0.8, 20.0) + random.gauss(0, 0.5)
            acoustic = 94.0 + random.gauss(0, 1.0)
            current = motor.rated_current * 1.25

        elif scenario == "CAVITATION":
            # Specific to pump cavitation
            if pressure is not None:
                pressure = max(1.2, pressure - (step * 0.15))
            acoustic = 92.0 + (3.0 * random.random())
            vibration = 4.8 + random.gauss(0, 0.3)

        # Clamping to physically sensible ranges
        temp = max(-10.0, round(temp, 2))
        vibration = max(0.1, round(vibration, 2))
        current = max(0.5, round(current, 2))
        voltage = max(50.0, round(voltage, 2))
        rpm = max(0.0, round(rpm, 1))
        acoustic = max(30.0, round(acoustic, 1))
        pressure = round(pressure, 2) if pressure is not None else None
        pf = max(0.3, min(1.0, round(pf, 3)))

        return MotorTelemetry(
            device_id=motor.device_id,
            timestamp=datetime.now(timezone.utc),
            temperature=temp,
            vibration=vibration,
            current=current,
            voltage=voltage,
            rpm=rpm,
            acoustic_db=acoustic,
            pressure_bar=pressure,
            power_factor=pf,
            state="NORMAL",
            metadata={
                "name": motor.name,
                "motor_type": motor.motor_type,
                "rated_kw": motor.rated_kw,
                "rated_current": motor.rated_current,
                "scenario": scenario,
            }
        )

    def tick_all_motors(self) -> list[MotorTelemetry]:
        """Generate one reading for each of the three industrial motors."""
        readings: list[MotorTelemetry] = []
        with self._lock:
            device_ids = list(self.motors.keys())

        for dev_id in device_ids:
            reading = self.generate_reading(dev_id)
            readings.append(reading)
            if self.on_reading:
                try:
                    self.on_reading(reading)
                except Exception as exc:
                    logger.error("Simulator callback error: %s", exc)
        return readings

    def start(self) -> None:
        """Start autonomous background simulation loop."""
        with self._lock:
            if self._running:
                return
            self._running = True
            self._thread = threading.Thread(target=self._run_loop, daemon=True, name="MotorSimulatorThread")
            self._thread.start()
            logger.info("Motor simulator thread started (interval: %.1fs)", self.interval_sec)

    def stop(self) -> None:
        """Stop background simulation loop."""
        with self._lock:
            self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
            logger.info("Motor simulator thread stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    def _run_loop(self) -> None:
        while self._running:
            try:
                self.tick_all_motors()
            except Exception as exc:
                logger.error("Error during simulator tick: %s", exc)
            time.sleep(self.interval_sec)


if __name__ == "__main__":
    # Standalone demo run
    logging.basicConfig(level=logging.INFO)
    sim = MotorSimulator(interval_sec=1.5, on_reading_generated=lambda r: print(f"[{r.device_id}] Temp: {r.temperature}°C, Vib: {r.vibration} mm/s, State: {r.state}"))
    print("Testing 3-Motor Simulator for 5 ticks...")
    for _ in range(5):
        sim.tick_all_motors()
        time.sleep(1.0)
    print("Done!")
