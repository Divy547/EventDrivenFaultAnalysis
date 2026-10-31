"""Page 4: Knowledge-Driven AI Diagnosis Service & Conversational Troubleshooting Assistant."""

from __future__ import annotations

import json
from typing import Any
import streamlit as st

from src.models.diagnosis import ChatMessage, StructuredFaultDiagnosis
from src.models.telemetry import FaultEvent, MotorTelemetry
from src.services import ServiceContainer


def render_diagnosis_view(services: ServiceContainer) -> None:
    st.subheader("🤖 Knowledge-Driven AI Diagnostic & Troubleshooting Suite")

    tab_diag, tab_chat = st.tabs([
        "🔬 Automated Root-Cause Diagnostic Service",
        "💬 Conversational Troubleshooting Assistant"
    ])

    # -------------------------------------------------------------
    # SUB-TAB 1: Automated Root-Cause Diagnostic Service
    # -------------------------------------------------------------
    with tab_diag:
        ai_active = services.assistant.ai_config.has_api_key
        if ai_active:
            st.info(
                f"🟢 **Inference Engine:** Google Gemini (`{services.assistant.ai_config.model}`) "
                "with PyMuPDF manual grounding and scikit-learn TF-IDF retrieval."
            )
        else:
            st.info(
                "🟡 **Inference Engine:** Deterministic Demo Fallback (Offline Mode) — "
                "Active without external API keys or network dependencies. Full manual grounding and schema validation enforced."
            )

        # Pull active faults from SQLite
        active_faults = services.db.get_active_faults()
        fault_dict: dict[str, Any] = {}
        target_f_id = st.session_state.get("diagnose_fault_id")
        preselected_idx = 0

        for idx, f in enumerate(active_faults):
            label = f"[{f['severity']}] {f['device_id']}: {f['fault_type']} ({f['metric_name']}={f['metric_value']:.2f})"
            fault_dict[label] = f
            if target_f_id and f["fault_id"] == target_f_id:
                preselected_idx = idx

        if not fault_dict:
            st.warning("No active equipment alerts found. You can synthesize an equipment condition below to test the diagnostic pipeline:")
            c_dev, c_type, c_gen = st.columns([2, 2, 1])
            with c_dev:
                synth_dev = st.selectbox("Equipment:", list(services.simulator.motors.keys()), key="synth_dev")
            with c_type:
                synth_scen = st.selectbox("Fault Type:", ["OVERHEATING", "BEARING_WEAR", "ELECTRICAL_OVERLOAD", "VOLTAGE_SAG", "COMPOUND_BEARING_FAILURE"], key="synth_scen")
            with c_gen:
                st.write("")
                st.write("")
                if st.button("Generate Diagnostic Report", type="primary", use_container_width=True):
                    dummy_f = FaultEvent(
                        fault_id=f"{synth_dev}_{synth_scen}",
                        device_id=synth_dev,
                        fault_type=synth_scen,
                        severity="CRITICAL" if "COMPOUND" in synth_scen or "BEARING" in synth_scen else "WARNING",
                        metric_name="vibration" if "BEARING" in synth_scen or "COMPOUND" in synth_scen else ("temperature" if "OVERHEAT" in synth_scen else "current"),
                        metric_value=7.4 if "BEARING" in synth_scen else (92.0 if "OVERHEAT" in synth_scen else 36.5),
                        threshold_value=7.1 if "BEARING" in synth_scen else (90.0 if "OVERHEAT" in synth_scen else 28.0),
                        message=f"Simulated {synth_scen} incident for diagnostic verification."
                    )
                    recent_tel_raw = services.db.get_recent_telemetry(device_id=synth_dev, limit=1)
                    recent_tel = MotorTelemetry.from_raw_json(recent_tel_raw[0]["raw_json"]) if recent_tel_raw else None
                    diag = services.assistant.diagnose_fault(dummy_f, telemetry=recent_tel)
                    st.session_state["active_diag_report"] = diag
                    st.rerun()

        else:
            col_sel, col_action = st.columns([3, 1])
            with col_sel:
                selected_label = st.selectbox(
                    "Select an Active Equipment Alert to Diagnose:",
                    list(fault_dict.keys()),
                    index=preselected_idx if preselected_idx < len(fault_dict) else 0
                )
            with col_action:
                st.write("")
                st.write("")
                if st.button("🚀 Run AI Diagnosis", type="primary", use_container_width=True):
                    raw_fault = fault_dict[selected_label]
                    f_obj = FaultEvent(**raw_fault)
                    recent_tel_raw = services.db.get_recent_telemetry(device_id=f_obj.device_id, limit=1)
                    recent_tel = MotorTelemetry.from_raw_json(recent_tel_raw[0]["raw_json"]) if recent_tel_raw else None

                    with st.spinner("Analyzing physical telemetry, querying manuals, and synthesizing diagnosis..."):
                        diag = services.assistant.diagnose_fault(f_obj, telemetry=recent_tel)
                        st.session_state["active_diag_report"] = diag
                        st.rerun()

        # Render Diagnosis Report
        diag: StructuredFaultDiagnosis | None = st.session_state.get("active_diag_report")
        if diag:
            st.divider()

            # Disclaimer Banner
            st.warning(
                f"⚠️ **STATUS: {diag.verification_status.upper()}** — "
                "Automated diagnostic findings must be physically verified by a qualified technician prior to executing mechanical repairs."
            )

            # Executive Header
            with st.container(border=True):
                h1, h2 = st.columns([3, 1])
                with h1:
                    sev_class = "badge-critical" if diag.severity == "CRITICAL" else "badge-warning"
                    st.markdown(
                        f"### <span class='{sev_class}'>● {diag.severity}</span> &nbsp; {diag.fault_title}",
                        unsafe_allow_html=True
                    )
                    st.caption(f"Target Motor: `{diag.device_id}` | Diagnostic Timestamp: `{str(diag.timestamp)[:19]}` UTC")
                with h2:
                    conf = diag.qualified_confidence
                    conf_color = "#3fb950" if conf.level == "HIGH" else ("#d29922" if conf.level == "MEDIUM" else "#f85149")
                    st.markdown(
                        f"**Qualified Confidence:** <span style='color:{conf_color}; font-weight:700;'>{conf.level} ({conf.score:.0%})</span>",
                        unsafe_allow_html=True
                    )
                    st.caption(f"Engine: `{diag.engine_used}`")
                    if diag.fallback_reason:
                        st.caption(f"Mode Reason: *{diag.fallback_reason}*")

            # Confidence Explanation
            st.info(f"💡 **Confidence Rationale:** {diag.qualified_confidence.explanation}")

            # 2x2 Breakdown
            row1_c1, row1_c2 = st.columns(2)
            with row1_c1:
                with st.container(border=True):
                    st.markdown("#### 👁️ Direct Empirical Observations")
                    for obs in diag.observations:
                        st.markdown(f"• {obs}")

            with row1_c2:
                with st.container(border=True):
                    st.markdown("#### 🔬 Technical Evidence")
                    for evi in diag.evidence:
                        st.markdown(f"• {evi}")

            row2_c1, row2_c2 = st.columns(2)
            with row2_c1:
                with st.container(border=True):
                    st.markdown("#### ❓ Grounded Possible Causes")
                    for cause in diag.possible_causes:
                        st.markdown(f"• {cause}")

            with row2_c2:
                with st.container(border=True):
                    st.markdown("#### 🛠️ Recommended Actions (OSHA LOTO)")
                    for idx, act in enumerate(diag.recommended_actions, 1):
                        st.markdown(f"**{idx}.** {act}")

            # Source Passages
            st.markdown("#### 📚 Verifiable Technical Manual Sources")
            if diag.sources:
                for idx, src in enumerate(diag.sources, 1):
                    with st.expander(f"📄 Citation {idx}: {src.doc_name} (Page {src.page_number}) — Relevance Score: {src.similarity_score:.4f}"):
                        st.caption(f"Chunk ID: `{src.chunk_id}`")
                        st.text(src.excerpt)
            else:
                st.info("No matching passages in technical manual exceeded similarity threshold.")

            # JSON Download
            st.download_button(
                "📥 Download Structured Diagnosis (JSON)",
                data=json.dumps(diag.model_dump(), default=str, indent=2),
                file_name=f"diagnosis_{diag.device_id}_{diag.severity}.json",
                mime="application/json"
            )

    # -------------------------------------------------------------
    # SUB-TAB 2: Conversational Troubleshooting Assistant
    # -------------------------------------------------------------
    with tab_chat:
        st.markdown("#### 💬 Interactive Industrial Troubleshooting Chat")
        st.caption(
            "Converse with the diagnostic assistant. Questions are matched against the technical documentation "
            "library in real time, citing exact page references without hallucination."
        )

        if "troubleshoot_chat_history" not in st.session_state:
            st.session_state["troubleshoot_chat_history"] = []

        # Quick Prompt Buttons
        st.write("**Quick Diagnostics Prompts:**")
        qp1, qp2, qp3, qp4 = st.columns(4)
        quick_prompt = None
        with qp1:
            if st.button("〰️ ISO 10816 Vibration Limits", use_container_width=True):
                quick_prompt = "Explain the ISO 10816 Zone D critical vibration threshold and recommended alignment procedures."
        with qp2:
            if st.button("🔥 Class F Thermal Limits", use_container_width=True):
                quick_prompt = "What are the NEMA Class F motor thermal limits and causes of stator overheating?"
        with qp3:
            if st.button("💨 Pump Cavitation Fix", use_container_width=True):
                quick_prompt = "What causes centrifugal pump cavitation and what are the immediate corrective actions?"
        with qp4:
            if st.button("⚡ Overcurrent / Single Phase", use_container_width=True):
                quick_prompt = "How do we troubleshoot motor overcurrent exceeding 115% FLA?"

        # Clear chat
        if st.session_state["troubleshoot_chat_history"]:
            if st.button("🧹 Clear Chat History"):
                st.session_state["troubleshoot_chat_history"] = []
                st.rerun()

        # Display Chat History
        for msg in st.session_state["troubleshoot_chat_history"]:
            with st.chat_message(msg.role):
                st.markdown(msg.content)
                if msg.sources:
                    with st.expander("📚 Verified Technical Citations"):
                        for s in msg.sources:
                            st.caption(f"• **{s.doc_name}** (Page {s.page_number}, Score: {s.similarity_score:.2f}): *{s.excerpt[:130]}...*")

        # Chat Input
        user_text = st.chat_input("Ask a troubleshooting question about electric motors, ISO 10816, bearings, or electrical protection...")
        effective_query = quick_prompt or user_text

        if effective_query:
            # Append user turn
            user_msg = ChatMessage(role="user", content=effective_query)
            st.session_state["troubleshoot_chat_history"].append(user_msg)

            # Get active fault if any
            act_faults = services.db.get_active_faults()
            curr_f = FaultEvent(**act_faults[0]) if act_faults else None

            with st.spinner("Retrieving manual passages and reasoning..."):
                resp = services.assistant.chat_troubleshoot(
                    user_message=effective_query,
                    history=st.session_state["troubleshoot_chat_history"][:-1],
                    active_fault=curr_f
                )
                st.session_state["troubleshoot_chat_history"].append(resp)
                st.rerun()
