"""Page 1: Plant Overview & Fleet Health Summary."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.services import ServiceContainer


def render_overview_view(services: ServiceContainer) -> None:
    st.subheader("🏭 Plant Overview & Fleet Health Management")

    # Fetch actual persisted fleet data
    motor_ids = list(services.simulator.motors.keys())
    fleet_summary = services.db.get_fleet_summary(motor_ids)
    stats = services.db.get_telemetry_stats()
    total_telemetry = stats.get("total_count", 0)
    indexed_doc_count = services.assistant.tfidf_index.total_chunks

    # Top KPI Metrics Row
    kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
    with kpi1:
        score = fleet_summary["fleet_health_score"]
        score_delta = f"{score - 100}%" if score < 100 else "Nominal"
        st.metric("Fleet Health Index", f"{score}%", delta=score_delta, delta_color="inverse" if score < 100 else "normal")

    with kpi2:
        crits = fleet_summary["total_critical"]
        st.metric("Active Critical Alerts", crits, delta=f"{crits} Critical" if crits > 0 else "0", delta_color="inverse")

    with kpi3:
        warns = fleet_summary["total_warning"]
        st.metric("Active Warnings", warns, delta=f"{warns} Advisory" if warns > 0 else "0", delta_color="inverse")

    with kpi4:
        st.metric("Total Ingested Telemetry", f"{total_telemetry:,}")

    with kpi5:
        mqtt_mode = "🟢 MQTT Connected" if services.mqtt.is_connected else "🟡 Local Fallback"
        st.metric("Telemetry Pipeline", mqtt_mode)

    st.write("")

    # Simulator Master Bar
    with st.container(border=True):
        sc_col1, sc_col2, sc_col3, sc_col4 = st.columns([2, 2, 2, 2])
        with sc_col1:
            sim_on = services.simulator.is_running
            if sim_on:
                if st.button("⏹️ Pause Simulator", type="secondary", use_container_width=True):
                    services.simulator.stop()
                    st.rerun()
            else:
                if st.button("▶️ Start Simulator", type="primary", use_container_width=True):
                    services.simulator.start()
                    st.rerun()

        with sc_col2:
            if st.button("⚡ Quick Tick (All Motors)", use_container_width=True):
                services.simulator.tick_all_motors()
                st.success("Emitted 1 reading per motor!")
                st.rerun()

        with sc_col3:
            if st.button("🔄 Reset All to NORMAL", use_container_width=True):
                for dev_id in services.simulator.motors:
                    services.simulator.set_scenario(dev_id, "NORMAL")
                st.success("All motor operating scenarios reset to NORMAL.")
                st.rerun()

        with sc_col4:
            st.caption(
                f"Tick Rate: **{services.simulator.interval_sec:.1f}s** | "
                f"KB Manuals: **{indexed_doc_count} chunks**"
            )

    st.markdown("### 🎛️ Monitored Industrial Motor Assets")

    # Three Device Health Cards
    col_dev1, col_dev2, col_dev3 = st.columns(3)
    dev_cols = [col_dev1, col_dev2, col_dev3]

    for idx, dev_info in enumerate(fleet_summary["devices"]):
        dev_id = dev_info["device_id"]
        motor_profile = services.simulator.motors.get(dev_id)
        latest = dev_info["latest_telemetry"]
        status = dev_info["health_status"]

        with dev_cols[idx]:
            with st.container(border=True):
                # Header
                st.markdown(f"#### `{dev_id}`")
                if motor_profile:
                    st.caption(f"**{motor_profile.name}** ({motor_profile.rated_kw} kW)")

                # Status Badge
                if status == "CRITICAL":
                    st.markdown("<span class='badge-critical'>● CRITICAL FAULT</span>", unsafe_allow_html=True)
                elif status == "WARNING":
                    st.markdown("<span class='badge-warning'>▲ WARNING / DEGRADED</span>", unsafe_allow_html=True)
                elif status == "OPERATIONAL":
                    st.markdown("<span class='badge-operational'>✔ OPERATIONAL NORMAL</span>", unsafe_allow_html=True)
                else:
                    st.markdown("<span class='badge-warning'>STANDBY (No readings)</span>", unsafe_allow_html=True)

                st.write("")

                # Telemetry Readings
                if latest:
                    c_t1, c_t2 = st.columns(2)
                    with c_t1:
                        st.write(f"🔥 Temp: **{latest['temperature']:.1f} °C**")
                        st.write(f"〰️ Vib: **{latest['vibration']:.2f} mm/s**")
                        st.write(f"⚡ Current: **{latest['current']:.1f} A**")
                    with c_t2:
                        st.write(f"⚙️ Speed: **{latest['rpm']:.0f} RPM**")
                        st.write(f"🔊 Noise: **{latest['acoustic_db']:.1f} dB**")
                        if latest.get("pressure_bar") is not None:
                            st.write(f"💨 Press: **{latest['pressure_bar']:.1f} bar**")
                        else:
                            st.write(f"🔌 Volt: **{latest['voltage']:.1f} V**")
                    st.caption(f"Last ping: {latest['timestamp'][11:19]} UTC")
                else:
                    st.info("No telemetry received yet. Click 'Quick Tick' above.")

                st.divider()

                # Action Links
                c_act1, c_act2 = st.columns(2)
                with c_act1:
                    if st.button("📊 Live Monitor", key=f"ov_mon_{dev_id}", use_container_width=True):
                        st.session_state["monitor_selected_device"] = dev_id
                        st.session_state["active_nav"] = "Live Monitoring"
                        st.rerun()

                with c_act2:
                    scen = motor_profile.active_scenario if motor_profile else "NORMAL"
                    scen_color = "green" if scen == "NORMAL" else "red"
                    st.caption(f"Scenario: :{scen_color}[**{scen}**]")

    st.write("")

    # Recent Alerts Feed
    st.markdown("### 🚨 Recent Critical & Warning Alerts")
    active_alerts = services.db.get_active_faults()

    if active_alerts:
        df_alerts = pd.DataFrame(active_alerts)[
            ["fault_id", "device_id", "severity", "fault_type", "metric_name", "metric_value", "threshold_value", "occurrence_count", "last_detected"]
        ]
        st.dataframe(df_alerts, use_container_width=True, hide_index=True)
    else:
        st.success("✅ Fleet operating normally. Zero active unresolved alerts.")
