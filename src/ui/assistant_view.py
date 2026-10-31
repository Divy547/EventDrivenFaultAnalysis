"""Knowledge-Driven AI Diagnostic Assistant UI view."""

from __future__ import annotations

import streamlit as st

from src.models.telemetry import FaultEvent
from src.services import ServiceContainer


def render_assistant_view(services: ServiceContainer) -> None:
    st.subheader("🤖 Knowledge-Driven Industrial Diagnostic Assistant")

    # Engine Status Badge
    ai_has_key = services.assistant.ai_config.has_api_key
    if ai_has_key:
        st.info(
            f"🟢 **Active Engine:** Google Gemini API (`{services.assistant.ai_config.model}`) "
            "with PyMuPDF + scikit-learn TF-IDF RAG Manual Context."
        )
    else:
        st.info(
            "🟡 **Active Engine:** Local Deterministic TF-IDF Grounded Synthesis "
            "(Offline mode active — no Google API key required; full technical manual grounding enabled)."
        )

    # Active Faults for Quick Diagnosis
    active_faults = services.db.get_active_faults()
    fault_options = {"None (Custom Inquiry)": None}
    preselected_idx = 0

    target_fault_id = st.session_state.get("diagnose_fault_id")

    for idx, f in enumerate(active_faults):
        key = f"[{f['severity']}] {f['device_id']}: {f['fault_type']} ({f['message'][:60]}...)"
        fault_options[key] = f
        if target_fault_id and f["fault_id"] == target_fault_id:
            preselected_idx = idx + 1

    col_select, col_mode = st.columns([3, 1])
    with col_select:
        selected_fault_label = st.selectbox(
            "Select an Active Equipment Fault to Diagnose:",
            list(fault_options.keys()),
            index=preselected_idx if preselected_idx < len(fault_options) else 0
        )

    selected_fault_dict = fault_options[selected_fault_label]

    default_query = ""
    if selected_fault_dict:
        default_query = (
            f"Diagnose {selected_fault_dict['fault_type']} on {selected_fault_dict['device_id']}. "
            f"Metric {selected_fault_dict['metric_name']} was {selected_fault_dict['metric_value']} "
            f"(threshold {selected_fault_dict['threshold_value']}). What is the root cause and required maintenance procedure?"
        )
    else:
        default_query = "What are the vibration limits under ISO 10816 and how do we resolve bearing raceway spalling?"

    query = st.text_area("Technical Query / Fault Description:", value=default_query, height=100)

    if st.button("🔍 Run Grounded Technical Diagnosis", type="primary"):
        with st.spinner("Retrieving manual excerpts and analyzing failure mechanics..."):
            if selected_fault_dict:
                # Convert dict to FaultEvent
                fault_obj = FaultEvent(**selected_fault_dict)
                # Fetch recent telemetry reading for context
                recent = services.db.get_recent_telemetry(device_id=fault_obj.device_id, limit=1)
                latest_tel = None
                if recent:
                    try:
                        from src.models.telemetry import MotorTelemetry
                        latest_tel = MotorTelemetry.from_raw_json(recent[0]["raw_json"])
                    except Exception:
                        pass
                report = services.assistant.diagnose_fault(fault_obj, telemetry=latest_tel)
            else:
                report = services.assistant.ask_assistant(query=query)

            st.session_state["last_report"] = report

    # Display Report
    report = st.session_state.get("last_report")
    if report:
        st.divider()
        st.markdown(f"### 📋 Diagnostic Report (`{report.engine_used}`)")

        # Summary Banner
        st.markdown(f"**Executive Assessment:** {report.summary}")

        c_root, c_safety = st.columns(2)
        with c_root:
            with st.container(border=True):
                st.markdown("#### 🔬 Root Cause Analysis")
                st.write(report.root_cause_analysis)

        with c_safety:
            with st.container(border=True):
                st.markdown("#### 🛡️ Mandatory Safety Precautions")
                for p in report.safety_precautions:
                    st.markdown(f"- ⚠️ {p}")

        # Maintenance Procedure
        with st.container(border=True):
            st.markdown("#### 🛠️ Recommended Maintenance Procedures")
            for idx, act in enumerate(report.maintenance_actions, start=1):
                st.markdown(f"**{idx}.** {act}")

        # Grounded Sources from Industrial Manual
        st.markdown("#### 📚 Grounded Evidence from Technical Documentation (PyMuPDF + TF-IDF)")
        if report.retrieved_sources:
            for s in report.retrieved_sources:
                doc_name = s.get("doc_name", "Manual")
                page = s.get("metadata", {}).get("page", 1)
                score = s.get("score", 0.0)
                with st.expander(f"📄 {doc_name} — Page {page} (Similarity Relevance: {score:.2f})"):
                    st.code(s.get("content", ""), language="markdown")
        else:
            st.info("No specific manual excerpt matched above threshold.")
