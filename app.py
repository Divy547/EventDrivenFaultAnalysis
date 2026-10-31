"""P_311: Knowledge-Driven IoT Fault Diagnosis Assistant.

Main Streamlit Application Entrypoint.
Five-page architecture: Overview, Live Monitoring, Fault Management,
AI Diagnosis, and Knowledge Base.
"""

from __future__ import annotations

import time
import streamlit as st

from src.services import get_services
from src.ui.diagnosis_view import render_diagnosis_view
from src.ui.fault_view import render_fault_view
from src.ui.knowledge_view import render_knowledge_view
from src.ui.monitoring_view import render_monitoring_view
from src.ui.overview_view import render_overview_view
from src.ui.theme import apply_industrial_theme

# Page Configuration
st.set_page_config(
    page_title="P_311 | IoT Fault Diagnosis Assistant",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Apply Dark Industrial Theme CSS
apply_industrial_theme()

# Acquire Singleton Services
services = get_services()

# --- Navigation Pages ---
PAGE_OVERVIEW = "Overview"
PAGE_MONITORING = "Live Monitoring"
PAGE_FAULTS = "Fault Management"
PAGE_DIAGNOSIS = "AI Diagnosis"
PAGE_KNOWLEDGE = "Knowledge Base"

PAGES = [
    PAGE_OVERVIEW,
    PAGE_MONITORING,
    PAGE_FAULTS,
    PAGE_DIAGNOSIS,
    PAGE_KNOWLEDGE,
]

PAGE_ICONS = {
    PAGE_OVERVIEW: "🏭",
    PAGE_MONITORING: "📊",
    PAGE_FAULTS: "🚨",
    PAGE_DIAGNOSIS: "🤖",
    PAGE_KNOWLEDGE: "📚",
}

# --- Sidebar ---
with st.sidebar:
    st.markdown("## ⚙️ P_311 Assistant")
    st.caption("Knowledge-Driven Industrial Motor Fault Diagnosis")

    st.divider()

    # Determine Active Navigation
    target_nav = st.session_state.get("active_nav", PAGE_OVERVIEW)
    current_index = PAGES.index(target_nav) if target_nav in PAGES else 0

    selected_nav = st.radio(
        "Navigation:",
        PAGES,
        index=current_index,
        format_func=lambda p: f"{PAGE_ICONS[p]} {p}"
    )
    st.session_state["active_nav"] = selected_nav

    st.divider()

    # Telemetry Transport Pipeline Status
    st.markdown("### 🔌 Pipeline Status")
    mqtt_ok = services.mqtt.is_connected
    if mqtt_ok:
        st.markdown("<span class='badge-operational'>🟢 MQTT CONNECTED</span>", unsafe_allow_html=True)
    else:
        st.markdown("<span class='badge-warning'>🟡 LOCAL FALLBACK MODE</span>", unsafe_allow_html=True)

    st.caption(f"Broker: `{services.mqtt.config.broker}:{services.mqtt.config.port}`")

    # Simulator Controls
    sim_running = services.simulator.is_running
    st.write(f"Simulator: **{'RUNNING' if sim_running else 'PAUSED'}**")
    c_btn1, c_btn2 = st.columns(2)
    with c_btn1:
        if sim_running:
            if st.button("⏹️ Pause", use_container_width=True):
                services.simulator.stop()
                st.rerun()
        else:
            if st.button("▶️ Start", type="primary", use_container_width=True):
                services.simulator.start()
                st.rerun()
    with c_btn2:
        if st.button("⚡ Quick Tick", use_container_width=True):
            services.simulator.tick_all_motors()
            st.rerun()

    st.divider()

    # Knowledge Base & Diagnostic Model Status
    st.markdown("### 🧠 AI & Manual RAG")
    total_chunks = services.assistant.tfidf_index.total_chunks
    st.write(f"Indexed Manuals: **{total_chunks} chunks**")

    has_gemini = services.assistant.ai_config.has_api_key
    if has_gemini:
        st.markdown(f"<span class='badge-operational'>🟢 Gemini ({services.assistant.ai_config.model})</span>", unsafe_allow_html=True)
    else:
        st.markdown("<span class='badge-warning'>🟡 Local Grounded Fallback</span>", unsafe_allow_html=True)

    st.divider()

    # Auto-refresh
    auto_refresh = st.checkbox("Auto-refresh Dashboard (3s)", value=False)
    if auto_refresh:
        time.sleep(3.0)
        st.rerun()

    st.caption("P_311 Industrial Fault Diagnosis Assistant | HCL Event-Driven Architecture")


# --- Route to Active Page ---
if selected_nav == PAGE_OVERVIEW:
    render_overview_view(services)

elif selected_nav == PAGE_MONITORING:
    render_monitoring_view(services)

elif selected_nav == PAGE_FAULTS:
    render_fault_view(services)

elif selected_nav == PAGE_DIAGNOSIS:
    render_diagnosis_view(services)

elif selected_nav == PAGE_KNOWLEDGE:
    render_knowledge_view(services)
