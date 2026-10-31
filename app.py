"""P_311: Knowledge-Driven IoT Fault Diagnosis Assistant.

Main Streamlit Application Entrypoint.
Orchestrates real-time telemetry streaming, rule-based fault detection,
deduplication, PDF technical manual extraction, and RAG AI diagnosis.
"""

from __future__ import annotations

import time
import streamlit as st

from src.services import get_services
from src.ui.assistant_view import render_assistant_view
from src.ui.dashboard_view import render_dashboard_view
from src.ui.faults_view import render_faults_view
from src.ui.knowledge_view import render_knowledge_view
from src.ui.settings_view import render_settings_view
from src.ui.simulator_view import render_simulator_view

# Initialize Streamlit Page
st.set_page_config(
    page_title="P_311 | IoT Fault Diagnosis Assistant",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Acquire singleton services
services = get_services()

# --- Sidebar ---
with st.sidebar:
    st.title("⚙️ P_311 IoT Assistant")
    st.caption("Knowledge-Driven Fault Diagnosis for Industrial Motors")

    st.divider()

    # System Status Card
    st.markdown("### 🔌 System Telemetry Pipeline")
    mqtt_conn = services.mqtt.is_connected
    st.write(
        f"**MQTT Transport:** `{'🟢 CONNECTED' if mqtt_conn else '🟡 LOCAL FALLBACK'}`"
    )
    st.caption(f"Broker: `{services.mqtt.config.broker}:{services.mqtt.config.port}`")

    sim_running = services.simulator.is_running
    st.write(
        f"**Motor Simulator:** `{'🟢 RUNNING' if sim_running else '⚪ STOPPED'}`"
    )

    col_sim_btn1, col_sim_btn2 = st.columns(2)
    with col_sim_btn1:
        if sim_running:
            if st.button("⏹️ Pause", use_container_width=True):
                services.simulator.stop()
                st.rerun()
        else:
            if st.button("▶️ Start", type="primary", use_container_width=True):
                services.simulator.start()
                st.rerun()
    with col_sim_btn2:
        if st.button("⚡ Quick Tick", use_container_width=True):
            services.simulator.tick_all_motors()
            st.rerun()

    st.divider()

    # Knowledge & AI Status
    st.markdown("### 🧠 Diagnostic Intelligence")
    st.write(f"**Indexed Manuals:** `{services.assistant.tfidf_index.total_chunks} chunks`")
    ai_active = services.assistant.ai_config.has_api_key
    st.write(
        f"**LLM Reasoner:** `{'🟢 Gemini API' if ai_active else '🟡 Local TF-IDF'}`"
    )

    st.divider()

    # Auto-refresh setting for live dashboard
    auto_refresh = st.checkbox("Auto-refresh Dashboard (3s)", value=False)
    if auto_refresh:
        time.sleep(3.0)
        st.rerun()

    st.caption("P_311 Industrial Fault Diagnosis Assistant | HCL Event-Driven Architecture")


# --- Main Navigation Tabs ---
tabs = [
    "📊 Live Dashboard",
    "🚨 Fault Alerts",
    "⚙️ Sensor Simulator",
    "🤖 AI Assistant",
    "📚 Technical Manuals",
    "🔧 Settings"
]

# Support tab navigation from button redirects (e.g. from alerts view to AI assistant)
target_tab = st.session_state.get("active_tab", "📊 Live Dashboard")
default_index = tabs.index(target_tab) if target_tab in tabs else 0

selected_tab = st.radio(
    "Navigation:",
    tabs,
    index=default_index,
    horizontal=True,
    label_visibility="collapsed"
)
st.session_state["active_tab"] = selected_tab

st.write("")  # Visual spacing

# --- Route to Active View ---
if selected_tab == "📊 Live Dashboard":
    render_dashboard_view(services)

elif selected_tab == "🚨 Fault Alerts":
    render_faults_view(services)

elif selected_tab == "⚙️ Sensor Simulator":
    render_simulator_view(services)

elif selected_tab == "🤖 AI Assistant":
    render_assistant_view(services)

elif selected_tab == "📚 Technical Manuals":
    render_knowledge_view(services)

elif selected_tab == "🔧 Settings":
    render_settings_view(services)
