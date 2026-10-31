"""Unit tests for the 3-motor sensor simulator."""

import pytest
from src.simulator.motor_simulator import MotorSimulator, DEFAULT_MOTORS


def test_motor_catalog():
    sim = MotorSimulator()
    assert len(sim.motors) == 3
    assert "MOTOR-PUMP-01" in sim.motors
    assert "MOTOR-CONV-02" in sim.motors
    assert "MOTOR-COMP-03" in sim.motors


def test_generate_readings_all_motors():
    readings = []
    sim = MotorSimulator(on_reading_generated=lambda r: readings.append(r))
    results = sim.tick_all_motors()
    assert len(results) == 3
    assert len(readings) == 3

    device_ids = {r.device_id for r in results}
    assert device_ids == {"MOTOR-PUMP-01", "MOTOR-CONV-02", "MOTOR-COMP-03"}


def test_scenario_transition():
    sim = MotorSimulator()
    assert sim.motors["MOTOR-PUMP-01"].active_scenario == "NORMAL"

    # Switch to OVERHEATING
    ok = sim.set_scenario("MOTOR-PUMP-01", "OVERHEATING")
    assert ok is True
    assert sim.motors["MOTOR-PUMP-01"].active_scenario == "OVERHEATING"

    # Step forward 5 ticks to ramp temperature
    for _ in range(5):
        reading = sim.generate_reading("MOTOR-PUMP-01")

    # In overheating, temperature must have risen substantially above baseline (52°C)
    assert reading.temperature > 55.0
