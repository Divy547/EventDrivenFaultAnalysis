"""Sensor Simulator & Fault Injection UI view."""

from __future__ import annotations

import streamlit as st

from src.services import ServiceContainer
from src.simulator.motor_simulator import AVAILABLE_SCENARIOS


def render_simulator_view(services: ServiceContainer) -> None:
    st.subheader("⚙️ Industrial Multi-Motor Sensor Simulator & Fault Injector")

    st.markdown(
        "Simulate physical operation across three industrial motors. "
        "Inject operational degradation scenarios to test event-driven rule detection, "
        "deduplication, and AI diagnostics in real time."
    )

    # Master Simulator Control Bar
    with st.container(border=True):
        col_ctrl1, col_ctrl2, col_ctrl3, col_ctrl4 = st.columns([2, 2, 2, 2])

        with col_ctrl1:
            if services.simulator.is_running:
                if st.button("⏹️ Stop Simulation", type="secondary", use_container_width=True):
                    services.simulator.stop()
                    st.rerun()
            else:
                if st.button("▶️ Start Autonomous Simulator", type="primary", use_container_width=True):
                    services.simulator.start()
                    st.rerun()

        with col_ctrl2:
            if st.button("⚡ Generate Single Tick (All)", use_container_width=True):
                services.simulator.tick_all_motors()
                st.success("Generated 1 reading per motor!")
                st.rerun()

        with col_ctrl3:
            if st.button("🔄 Reset All to NORMAL", use_container_width=True):
                for dev_id in services.simulator.motors:
                    services.simulator.set_scenario(dev_id, "NORMAL")
                st.success("All motors set to NORMAL baseline.")
                st.rerun()

        with col_ctrl4:
            new_interval = st.number_input(
                "Tick Rate (sec):",
                min_value=0.5,
                max_value=10.0,
                value=float(services.simulator.interval_sec),
                step=0.5
            )
            if new_interval != services.simulator.interval_sec:
                services.simulator.interval_sec = new_interval

    st.markdown("### 🏭 Industrial Motor Assets")

    col_m1, col_m2, col_m3 = st.columns(3)

    motors = list(services.simulator.motors.values())

    cols = [col_m1, col_m2, col_m3]
    for idx, motor in enumerate(motors):
        with cols[idx]:
            with st.container(border=True):
                st.markdown(f"#### `{motor.device_id}`")
                st.caption(f"**{motor.name}**")
                st.write(f"• **Type:** {motor.motor_type}")
                st.write(f"• **Rated Power:** {motor.rated_kw} kW")
                st.write(f"• **Rated Current:** {motor.rated_current} A")
                st.write(f"• **Nominal RPM:** {motor.nominal_rpm} RPM")

                scenario_badge = "green" if motor.active_scenario == "NORMAL" else "red"
                st.markdown(f"Current State: :{scenario_badge}[**{motor.active_scenario}**]")

                selected_scen = st.selectbox(
                    "Inject Scenario:",
                    AVAILABLE_SCENARIOS,
                    index=AVAILABLE_SCENARIOS.index(motor.active_scenario),
                    key=f"scen_select_{motor.device_id}"
                )

                if st.button("Apply Scenario", key=f"btn_apply_{motor.device_id}", use_container_width=True):
                    services.simulator.set_scenario(motor.device_id, selected_scen)
                    st.success(f"Set `{motor.device_id}` to {selected_scen}")
                    st.rerun()

    st.divider()

    # Pre-configured Industrial Stress Test Scenarios
    st.markdown("### 🎯 One-Click Stress Test Scenarios")
    p1, p2, p3 = st.columns(3)
    with p1:
        if st.button("🔥 Scenario: Thermal Overload Cascade", use_container_width=True):
            services.simulator.set_scenario("MOTOR-PUMP-01", "OVERHEATING")
            services.simulator.set_scenario("MOTOR-CONV-02", "NORMAL")
            services.simulator.set_scenario("MOTOR-COMP-03", "NORMAL")
            services.simulator.tick_all_motors()
            st.warning("Injected OVERHEATING scenario into MOTOR-PUMP-01.")
            st.rerun()

    with p2:
        if st.button("〰️ Scenario: ISO 10816 Bearing Wear", use_container_width=True):
            services.simulator.set_scenario("MOTOR-PUMP-01", "NORMAL")
            services.simulator.set_scenario("MOTOR-CONV-02", "BEARING_WEAR")
            services.simulator.set_scenario("MOTOR-COMP-03", "NORMAL")
            services.simulator.tick_all_motors()
            st.warning("Injected BEARING_WEAR scenario into MOTOR-CONV-02.")
            st.rerun()

    with p3:
        if st.button("⚡ Scenario: Feeder Voltage Sag", use_container_width=True):
            services.simulator.set_scenario("MOTOR-PUMP-01", "VOLTAGE_SAG")
            services.simulator.set_scenario("MOTOR-CONV-02", "VOLTAGE_SAG")
            services.simulator.set_scenario("MOTOR-COMP-03", "VOLTAGE_SAG")
            services.simulator.tick_all_motors()
            st.warning("Injected VOLTAGE_SAG into all 3 motors.")
            st.rerun()
