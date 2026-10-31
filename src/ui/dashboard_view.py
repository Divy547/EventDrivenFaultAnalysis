"""Live Telemetry Dashboard UI view."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.services import ServiceContainer


def render_dashboard_view(services: ServiceContainer) -> None:
    st.subheader("📊 Live Telemetry & Motor Health Dashboard")

    # Fetch stats
    stats = services.db.get_telemetry_stats()
    total_telemetry = stats.get("total_count", 0)
    active_faults = services.db.get_active_faults()
    critical_faults = [f for f in active_faults if f["severity"] == "CRITICAL"]

    # Top KPI row
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Total Readings", f"{total_telemetry:,}")
    with col2:
        st.metric(
            "Active Alerts",
            len(active_faults),
            delta=f"{len(critical_faults)} Critical" if critical_faults else "Normal",
            delta_color="inverse" if critical_faults else "normal"
        )
    with col3:
        sim_status = "Running" if services.simulator.is_running else "Stopped"
        st.metric("Simulator Status", sim_status)
    with col4:
        mqtt_status = "Connected" if services.mqtt.is_connected else "Local Fallback"
        st.metric("Transport Mode", mqtt_status)
    with col5:
        st.metric("Monitored Motors", len(services.simulator.motors))

    st.divider()

    # Device filter
    motor_ids = list(services.simulator.motors.keys())
    selected_device = st.selectbox("Select Industrial Motor:", ["ALL"] + motor_ids, index=0)

    # Fetch recent readings
    device_filter = None if selected_device == "ALL" else selected_device
    recent_readings = services.db.get_recent_telemetry(device_id=device_filter, limit=60)

    if not recent_readings:
        st.info("No telemetry records found. Start the Sensor Simulator or trigger a tick in the controls tab.")
        col_btn1, col_btn2 = st.columns([1, 4])
        with col_btn1:
            if st.button("🚀 Start Simulator Now", type="primary"):
                services.simulator.start()
                st.rerun()
        return

    # Latest reading metrics card
    latest = recent_readings[0]
    dev_name = latest["device_id"]
    st.markdown(f"#### Latest Telemetry Reading: `{dev_name}` ({latest['timestamp'][:19]})")

    m1, m2, m3, m4, m5, m6 = st.columns(6)
    with m1:
        temp = latest["temperature"]
        st.metric("Temperature", f"{temp:.1f} °C", delta=f"{temp - 50.0:+.1f} °C vs base")
    with m2:
        vib = latest["vibration"]
        st.metric("Vibration (RMS)", f"{vib:.2f} mm/s", delta=f"{vib - 1.8:+.2f} mm/s")
    with m3:
        curr = latest["current"]
        st.metric("Current", f"{curr:.1f} A")
    with m4:
        volt = latest["voltage"]
        st.metric("Voltage", f"{volt:.1f} V")
    with m5:
        rpm = latest["rpm"]
        st.metric("Speed", f"{rpm:.0f} RPM")
    with m6:
        acoustic = latest["acoustic_db"]
        st.metric("Acoustic Noise", f"{acoustic:.1f} dB")

    # Time series plots
    st.markdown("### 📈 Real-Time Multi-Sensor Telemetry Trends")
    df = pd.DataFrame(recent_readings)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp")

    tab_temp, tab_vib, tab_elec = st.tabs(["🔥 Temperature", "〰️ Vibration (ISO 10816)", "⚡ Current & Voltage"])

    with tab_temp:
        fig_temp = go.Figure()
        for dev in df["device_id"].unique():
            dev_df = df[df["device_id"] == dev]
            fig_temp.add_trace(go.Scatter(
                x=dev_df["timestamp"], y=dev_df["temperature"],
                mode="lines+markers", name=f"{dev} Temp"
            ))

        # Threshold lines
        fig_temp.add_hline(
            y=services.detector.thresholds.temp_warning,
            line_dash="dash", line_color="orange",
            annotation_text=f"Warning ({services.detector.thresholds.temp_warning}°C)"
        )
        fig_temp.add_hline(
            y=services.detector.thresholds.temp_critical,
            line_dash="dash", line_color="red",
            annotation_text=f"Critical ({services.detector.thresholds.temp_critical}°C)"
        )
        fig_temp.update_layout(
            height=350, margin=dict(l=20, r=20, t=30, b=20),
            yaxis_title="Temperature (°C)", xaxis_title="Time (UTC)"
        )
        st.plotly_chart(fig_temp, use_container_width=True)

    with tab_vib:
        fig_vib = go.Figure()
        for dev in df["device_id"].unique():
            dev_df = df[df["device_id"] == dev]
            fig_vib.add_trace(go.Scatter(
                x=dev_df["timestamp"], y=dev_df["vibration"],
                mode="lines+markers", name=f"{dev} Vibration"
            ))

        # ISO 10816 zones
        fig_vib.add_hline(
            y=services.detector.thresholds.vibration_warning,
            line_dash="dash", line_color="orange",
            annotation_text=f"ISO Zone C Warning ({services.detector.thresholds.vibration_warning} mm/s)"
        )
        fig_vib.add_hline(
            y=services.detector.thresholds.vibration_critical,
            line_dash="dash", line_color="red",
            annotation_text=f"ISO Zone D Critical ({services.detector.thresholds.vibration_critical} mm/s)"
        )
        fig_vib.update_layout(
            height=350, margin=dict(l=20, r=20, t=30, b=20),
            yaxis_title="Vibration Velocity (mm/s RMS)", xaxis_title="Time (UTC)"
        )
        st.plotly_chart(fig_vib, use_container_width=True)

    with tab_elec:
        fig_elec = go.Figure()
        for dev in df["device_id"].unique():
            dev_df = df[df["device_id"] == dev]
            fig_elec.add_trace(go.Scatter(
                x=dev_df["timestamp"], y=dev_df["current"],
                mode="lines+markers", name=f"{dev} Current (A)"
            ))
        fig_elec.update_layout(
            height=350, margin=dict(l=20, r=20, t=30, b=20),
            yaxis_title="Phase Current (A)", xaxis_title="Time (UTC)"
        )
        st.plotly_chart(fig_elec, use_container_width=True)

    # Telemetry Table
    with st.expander("📋 View Recent Raw Ingested Telemetry Records"):
        table_cols = ["id", "device_id", "timestamp", "temperature", "vibration", "current", "voltage", "rpm", "acoustic_db", "state"]
        display_df = df[table_cols].sort_values("id", ascending=False)
        st.dataframe(display_df, use_container_width=True, hide_index=True)
