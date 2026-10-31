"""Page 2: Live Monitoring with Plotly Charts for Temperature, Vibration, RPM and Current."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.services import ServiceContainer
from src.simulator.motor_simulator import AVAILABLE_SCENARIOS
from src.ui.theme import format_plotly_chart


def render_monitoring_view(services: ServiceContainer) -> None:
    st.subheader("📊 High-Resolution Telemetry & Live Sensor Monitoring")

    # Filter Controls Bar
    with st.container(border=True):
        col_dev, col_samples, col_sim = st.columns([2, 1, 3])

        with col_dev:
            motor_keys = list(services.simulator.motors.keys())
            preselected_dev = st.session_state.get("monitor_selected_device", "ALL")
            dev_index = (["ALL"] + motor_keys).index(preselected_dev) if preselected_dev in (["ALL"] + motor_keys) else 0

            selected_device = st.selectbox(
                "Filter Monitored Motor:",
                ["ALL"] + motor_keys,
                index=dev_index
            )
            st.session_state["monitor_selected_device"] = selected_device

        with col_samples:
            sample_limit = st.selectbox("Telemetry Depth:", [30, 60, 100, 200], index=1)

        with col_sim:
            st.write("**Autonomous Simulator Controls:**")
            sim_col1, sim_col2, sim_col3 = st.columns(3)
            with sim_col1:
                if services.simulator.is_running:
                    if st.button("⏹️ Stop", use_container_width=True):
                        services.simulator.stop()
                        st.rerun()
                else:
                    if st.button("▶️ Start", type="primary", use_container_width=True):
                        services.simulator.start()
                        st.rerun()
            with sim_col2:
                if st.button("⚡ Step Tick", use_container_width=True):
                    services.simulator.tick_all_motors()
                    st.rerun()
            with sim_col3:
                st.caption(f"Status: `{'RUNNING' if services.simulator.is_running else 'STOPPED'}`")

    # Fetch Real Persisted Data from SQLite
    dev_query = None if selected_device == "ALL" else selected_device
    recent_readings = services.db.get_recent_telemetry(device_id=dev_query, limit=sample_limit)

    if not recent_readings:
        st.info("No telemetry records currently in database. Click 'Step Tick' or 'Start' to stream sensor data.")
        return

    # Latest Telemetry Metric Cards
    latest = recent_readings[0]
    dev_title = latest["device_id"] if selected_device == "ALL" else selected_device
    st.markdown(f"#### ⏱️ Real-Time Telemetry Snapshot: `{dev_title}` ({latest['timestamp'][11:19]} UTC)")

    m_temp, m_vib, m_rpm, m_curr, m_volt, m_acoust = st.columns(6)
    with m_temp:
        temp_val = latest["temperature"]
        st.metric("Temperature", f"{temp_val:.1f} °C", delta=f"{temp_val - 50.0:+.1f} °C vs base")
    with m_vib:
        vib_val = latest["vibration"]
        st.metric("Vibration RMS", f"{vib_val:.2f} mm/s", delta=f"{vib_val - 1.8:+.2f} mm/s")
    with m_rpm:
        rpm_val = latest["rpm"]
        st.metric("Shaft Speed", f"{rpm_val:.0f} RPM")
    with m_curr:
        curr_val = latest["current"]
        st.metric("Phase Current", f"{curr_val:.1f} A")
    with m_volt:
        volt_val = latest["voltage"]
        st.metric("Line Voltage", f"{volt_val:.1f} V")
    with m_acoust:
        acoust_val = latest["acoustic_db"]
        st.metric("Acoustic Noise", f"{acoust_val:.1f} dB")

    # Prepare DataFrame
    df = pd.DataFrame(recent_readings)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp")

    st.write("")

    # Plotly Visualizations: 2x2 Grid for Temperature, Vibration, Current, RPM
    st.markdown("### 📈 Time-Series Engineering Waveforms")

    chart_row1_col1, chart_row1_col2 = st.columns(2)

    # 1. Temperature Chart with Thresholds
    with chart_row1_col1:
        fig_temp = go.Figure()
        for dev in df["device_id"].unique():
            dev_df = df[df["device_id"] == dev]
            fig_temp.add_trace(go.Scatter(
                x=dev_df["timestamp"], y=dev_df["temperature"],
                mode="lines+markers", name=f"{dev}",
                line=dict(width=2), marker=dict(size=4)
            ))
        fig_temp.add_hline(
            y=services.detector.thresholds.temp_warning,
            line_dash="dash", line_color="#d29922",
            annotation_text=f"Warning ({services.detector.thresholds.temp_warning}°C)"
        )
        fig_temp.add_hline(
            y=services.detector.thresholds.temp_critical,
            line_dash="dash", line_color="#f85149",
            annotation_text=f"Critical ({services.detector.thresholds.temp_critical}°C)"
        )
        format_plotly_chart(fig_temp, y_title="Temperature (°C)")
        st.plotly_chart(fig_temp, use_container_width=True)

    # 2. Vibration Chart with ISO 10816 Standard Thresholds
    with chart_row1_col2:
        fig_vib = go.Figure()
        for dev in df["device_id"].unique():
            dev_df = df[df["device_id"] == dev]
            fig_vib.add_trace(go.Scatter(
                x=dev_df["timestamp"], y=dev_df["vibration"],
                mode="lines+markers", name=f"{dev}",
                line=dict(width=2), marker=dict(size=4)
            ))
        fig_vib.add_hline(
            y=services.detector.thresholds.vibration_warning,
            line_dash="dash", line_color="#d29922",
            annotation_text=f"ISO Zone C Warning ({services.detector.thresholds.vibration_warning} mm/s)"
        )
        fig_vib.add_hline(
            y=services.detector.thresholds.vibration_critical,
            line_dash="dash", line_color="#f85149",
            annotation_text=f"ISO Zone D Critical ({services.detector.thresholds.vibration_critical} mm/s)"
        )
        format_plotly_chart(fig_vib, y_title="Vibration Velocity (mm/s RMS)")
        st.plotly_chart(fig_vib, use_container_width=True)

    chart_row2_col1, chart_row2_col2 = st.columns(2)

    # 3. RPM / Shaft Speed Chart
    with chart_row2_col1:
        fig_rpm = go.Figure()
        for dev in df["device_id"].unique():
            dev_df = df[df["device_id"] == dev]
            fig_rpm.add_trace(go.Scatter(
                x=dev_df["timestamp"], y=dev_df["rpm"],
                mode="lines+markers", name=f"{dev}",
                line=dict(width=2), marker=dict(size=4)
            ))
        format_plotly_chart(fig_rpm, y_title="Shaft Speed (RPM)")
        st.plotly_chart(fig_rpm, use_container_width=True)

    # 4. Current Chart with Rated Full-Load Lines
    with chart_row2_col2:
        fig_curr = go.Figure()
        for dev in df["device_id"].unique():
            dev_df = df[df["device_id"] == dev]
            fig_curr.add_trace(go.Scatter(
                x=dev_df["timestamp"], y=dev_df["current"],
                mode="lines+markers", name=f"{dev}",
                line=dict(width=2), marker=dict(size=4)
            ))
        format_plotly_chart(fig_curr, y_title="Phase Current (A RMS)")
        st.plotly_chart(fig_curr, use_container_width=True)

    st.write("")

    # Abnormal Scenario Injection Panel
    with st.container(border=True):
        st.markdown("#### ⚡ Dynamic Fault Injection Panel")
        st.caption("Trigger individual mechanical or electrical degradation scenarios across any of the three industrial motors:")

        inj_c1, inj_c2, inj_c3 = st.columns([2, 2, 1])
        with inj_c1:
            target_motor = st.selectbox(
                "Target Equipment:",
                list(services.simulator.motors.keys()),
                key="inj_motor_select"
            )
        with inj_c2:
            target_scen = st.selectbox(
                "Inject Scenario:",
                AVAILABLE_SCENARIOS,
                key="inj_scen_select"
            )
        with inj_c3:
            st.write("")
            st.write("")
            if st.button("🔥 Inject Scenario", type="primary", use_container_width=True):
                services.simulator.set_scenario(target_motor, target_scen)
                services.simulator.generate_reading(target_motor)
                st.warning(f"Injected **{target_scen}** into `{target_motor}`.")
                st.rerun()

    # Data Table Expander
    with st.expander("📋 View Raw Ingested Time-Series Table"):
        display_cols = ["id", "device_id", "timestamp", "temperature", "vibration", "current", "voltage", "rpm", "acoustic_db", "state"]
        st.dataframe(df[display_cols].sort_values("id", ascending=False), use_container_width=True, hide_index=True)
