"""System Configuration & MQTT Settings UI view."""

from __future__ import annotations

import streamlit as st

from src.services import ServiceContainer


def render_settings_view(services: ServiceContainer) -> None:
    st.subheader("🔧 System Settings & Network Configuration")

    tab_mqtt, tab_rules, tab_ai, tab_db = st.tabs([
        "📡 MQTT Broker & Transport",
        "⚖️ Fault Detection Thresholds",
        "🧠 AI & Gemini API",
        "💾 Database Maintenance"
    ])

    with tab_mqtt:
        st.markdown("#### MQTT Client & Broker Coordinates")
        st.write(
            f"**Current Status:** `{services.mqtt.connection_state}` "
            f"({'Connected' if services.mqtt.is_connected else 'Operating in Local Fallback'})"
        )
        if services.mqtt.last_error:
            st.caption(f"Last MQTT Event: `{services.mqtt.last_error}`")

        c1, c2 = st.columns(2)
        with c1:
            broker_input = st.text_input("MQTT Broker Host:", value=services.mqtt.config.broker)
            topic_input = st.text_input("Telemetry Base Topic:", value=services.mqtt.config.telemetry_topic)
        with c2:
            port_input = st.number_input("MQTT Broker Port:", value=int(services.mqtt.config.port), step=1)
            client_id_input = st.text_input("Client ID Prefix:", value=services.mqtt.config.client_id)

        col_recon1, col_recon2 = st.columns(2)
        with col_recon1:
            if st.button("🔄 Attempt MQTT Reconnection", type="primary", use_container_width=True):
                services.mqtt.config.broker = broker_input
                services.mqtt.config.port = int(port_input)
                services.mqtt.config.telemetry_topic = topic_input
                services.mqtt.config.client_id = client_id_input
                services.mqtt.reconnect(new_broker=broker_input, new_port=int(port_input))
                st.info("Reconnection initiated.")
                st.rerun()

        with col_recon2:
            mode_label = "Force Local Fallback Mode" if not services.mqtt.is_fallback_mode else "Disable Forced Fallback"
            if st.button(mode_label, use_container_width=True):
                services.mqtt._fallback_mode = not services.mqtt._fallback_mode
                st.rerun()

    with tab_rules:
        st.markdown("#### Configurable Fault Detection Thresholds & Deduplication")
        st.caption("Adjust real-time physical limits. Changes take effect on subsequent telemetry cycles.")

        th = services.detector.thresholds
        r1, r2 = st.columns(2)
        with r1:
            new_temp_warn = st.number_input("Temperature Warning (°C):", value=float(th.temp_warning), step=1.0)
            new_temp_crit = st.number_input("Temperature Critical (°C):", value=float(th.temp_critical), step=1.0)
            new_vib_warn = st.number_input("Vibration Warning (mm/s RMS):", value=float(th.vibration_warning), step=0.1)
            new_vib_crit = st.number_input("Vibration Critical (mm/s RMS):", value=float(th.vibration_critical), step=0.1)

        with r2:
            new_volt_warn = st.number_input("Low Voltage Warning (V):", value=float(th.voltage_low_warning), step=1.0)
            new_volt_crit = st.number_input("Low Voltage Critical (V):", value=float(th.voltage_low_critical), step=1.0)
            new_acoust_warn = st.number_input("Acoustic Warning (dB):", value=float(th.acoustic_warning), step=1.0)
            new_dedup = st.number_input("Fault Deduplication Window (sec):", value=float(th.deduplication_window_sec), step=5.0)

        if st.button("💾 Apply Updated Thresholds", type="primary"):
            services.detector.update_thresholds(
                temp_warning=new_temp_warn,
                temp_critical=new_temp_crit,
                vibration_warning=new_vib_warn,
                vibration_critical=new_vib_crit,
                voltage_low_warning=new_volt_warn,
                voltage_low_critical=new_volt_crit,
                acoustic_warning=new_acoust_warn,
                deduplication_window_sec=new_dedup
            )
            st.success("Rule thresholds successfully updated!")

    with tab_ai:
        st.markdown("#### Google Gemini API Configuration")
        st.caption("Optional: Set your Gemini API key to activate generative synthesis. If empty, local TF-IDF grounded reasoning is used.")

        api_key_input = st.text_input("Gemini API Key:", type="password", value=services.assistant.ai_config.api_key or "")
        model_input = st.selectbox("Gemini Model:", ["gemini-2.5-flash", "gemini-1.5-flash", "gemini-1.5-pro"], index=0)

        if st.button("Save AI Settings"):
            services.assistant.ai_config.api_key = api_key_input.strip() if api_key_input else None
            services.assistant.ai_config.model = model_input
            st.success("AI configuration saved.")
            st.rerun()

    with tab_db:
        st.markdown("#### SQLite Database Operations")
        st.write(f"Database File: `{services.db.db_path}`")
        if st.button("⚠️ Clear Telemetry & Fault History", type="secondary"):
            services.db.clear_all_data()
            st.success("Database records cleared.")
            st.rerun()
