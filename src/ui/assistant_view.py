"""Knowledge-Driven AI Diagnostic Assistant and Conversational Troubleshooting UI view."""

from __future__ import annotations

import streamlit as st

from src.models.diagnosis import ChatMessage, StructuredFaultDiagnosis
from src.models.telemetry import FaultEvent, MotorTelemetry
from src.services import ServiceContainer


def render_assistant_view(services: ServiceContainer) -> None:
    st.subheader("🤖 Knowledge-Driven AI Diagnostic & Troubleshooting Suite")

    tab_diag, tab_chat = st.tabs([
        "🔬 Automated Fault Diagnosis Service",
        "💬 Conversational Troubleshooting Assistant"
    ])

    # -------------------------------------------------------------
    # TAB 1: Structured Fault Diagnosis Service
    # -------------------------------------------------------------
    with tab_diag:
        ai_has_key = services.assistant.ai_config.has_api_key
        if ai_has_key:
            st.info(
                f"🟢 **Diagnostic Engine:** Google Gemini API (`{services.assistant.ai_config.model}`) "
                "with PyMuPDF + scikit-learn TF-IDF grounded manual retrieval."
            )
        else:
            st.info(
                "🟡 **Diagnostic Engine:** Deterministic Demo Fallback (Offline Mode) "
                "— Operating offline without a Gemini API key. Strict manual grounding and schema validation active."
            )

        active_faults = services.db.get_active_faults()
        fault_options: dict[str, Any] = {}

        target_fault_id = st.session_state.get("diagnose_fault_id")
        preselected_idx = 0

        for idx, f in enumerate(active_faults):
            key = f"[{f['severity']}] {f['device_id']}: {f['fault_type']} ({f['metric_name']}={f['metric_value']})"
            fault_options[key] = f
            if target_fault_id and f["fault_id"] == target_fault_id:
                preselected_idx = idx

        if not fault_options:
            st.warning("No active equipment alerts currently registered. You can inject a fault scenario in the Simulator tab or synthesize a test diagnosis below.")
            col_m, col_f = st.columns(2)
            with col_m:
                test_motor = st.selectbox("Select Motor Asset:", list(services.simulator.motors.keys()))
            with col_f:
                test_fault_type = st.selectbox("Select Fault Scenario:", ["OVERHEATING", "BEARING_WEAR", "ELECTRICAL_OVERLOAD", "VOLTAGE_SAG", "COMPOUND_BEARING_FAILURE"])

            if st.button("Generate Test Anomaly Diagnosis", type="primary"):
                dummy_fault = FaultEvent(
                    fault_id=f"{test_motor}_{test_fault_type}",
                    device_id=test_motor,
                    fault_type=test_fault_type,
                    severity="CRITICAL" if "COMPOUND" in test_fault_type else "WARNING",
                    metric_name="temperature" if "OVERHEAT" in test_fault_type else ("vibration" if "BEARING" in test_fault_type else "current"),
                    metric_value=92.5 if "OVERHEAT" in test_fault_type else (7.4 if "BEARING" in test_fault_type else 38.0),
                    threshold_value=90.0 if "OVERHEAT" in test_fault_type else (7.1 if "BEARING" in test_fault_type else 28.0),
                    message=f"Simulated {test_fault_type} condition for diagnosis verification."
                )
                diag = services.assistant.diagnose_fault(dummy_fault)
                st.session_state["active_diagnosis"] = diag
                st.rerun()

        else:
            col_fsel, col_btn = st.columns([3, 1])
            with col_fsel:
                selected_label = st.selectbox(
                    "Select an Active Equipment Alert:",
                    list(fault_options.keys()),
                    index=preselected_idx if preselected_idx < len(fault_options) else 0
                )
            with col_btn:
                st.write("")
                st.write("")
                run_diag_btn = st.button("🚀 Run AI Diagnosis", type="primary", use_container_width=True)

            if run_diag_btn:
                raw_f = fault_options[selected_label]
                fault_obj = FaultEvent(**raw_f)
                recent = services.db.get_recent_telemetry(device_id=fault_obj.device_id, limit=1)
                latest_tel = None
                if recent:
                    try:
                        latest_tel = MotorTelemetry.from_raw_json(recent[0]["raw_json"])
                    except Exception:
                        pass
                with st.spinner("Executing grounded RAG diagnosis pipeline..."):
                    diag = services.assistant.diagnose_fault(fault_obj, telemetry=latest_tel)
                    st.session_state["active_diagnosis"] = diag
                    st.rerun()

        # Render Active Structured Diagnosis
        diag: StructuredFaultDiagnosis | None = st.session_state.get("active_diagnosis")
        if diag:
            st.divider()

            # Verification Warning Banner
            st.warning(
                f"⚠️ **STATUS: {diag.verification_status.upper()}** — "
                "Automated diagnostic findings must be physically verified by a qualified technician prior to executing mechanical repairs."
            )

            # Header Card
            with st.container(border=True):
                col_head1, col_head2 = st.columns([3, 1])
                with col_head1:
                    sev_color = "red" if diag.severity == "CRITICAL" else "orange"
                    st.markdown(f"### :{sev_color}[{diag.severity}] {diag.fault_title}")
                    st.caption(f"Target Asset: `{diag.device_id}` | Time: {str(diag.timestamp)[:19]} UTC")
                with col_head2:
                    conf = diag.qualified_confidence
                    conf_color = "green" if conf.level == "HIGH" else ("orange" if conf.level == "MEDIUM" else "red")
                    st.markdown(f"**Confidence:** :{conf_color}[**{conf.level} ({conf.score:.0%})**]")
                    st.caption(f"Engine: `{diag.engine_used}`")
                    if diag.fallback_reason:
                        st.caption(f"Fallback Reason: *{diag.fallback_reason}*")

            # Confidence Explanation
            st.info(f"💡 **Confidence Rationale:** {diag.qualified_confidence.explanation}")

            # Observations & Evidence Row
            c_obs, c_evi = st.columns(2)
            with c_obs:
                with st.container(border=True):
                    st.markdown("#### 👁️ Direct Empirical Observations")
                    for obs in diag.observations:
                        st.markdown(f"• {obs}")

            with c_evi:
                with st.container(border=True):
                    st.markdown("#### 🔬 Technical Evidence")
                    for evi in diag.evidence:
                        st.markdown(f"• {evi}")

            # Causes & Actions Row
            c_cau, c_act = st.columns(2)
            with c_cau:
                with st.container(border=True):
                    st.markdown("#### ❓ Possible Root Causes (Manual Grounded)")
                    for cause in diag.possible_causes:
                        st.markdown(f"• {cause}")

            with c_act:
                with st.container(border=True):
                    st.markdown("#### 🛠️ Recommended Corrective Actions")
                    for idx, act in enumerate(diag.recommended_actions, 1):
                        st.markdown(f"**{idx}.** {act}")

            # Document Sources Citations
            st.markdown("#### 📚 Verifiable Document Sources (PyMuPDF + TF-IDF Retrieval)")
            if diag.sources:
                for idx, src in enumerate(diag.sources, 1):
                    with st.expander(f"📄 Citation {idx}: {src.doc_name} (Page {src.page_number}) — Relevance: {src.similarity_score:.4f}"):
                        st.caption(f"Chunk ID: `{src.chunk_id}`")
                        st.text(src.excerpt)
            else:
                st.info("No matching passages in technical manual exceeded similarity threshold.")

            # Raw JSON Expander
            with st.expander("🔎 View Validated Structured JSON Payload"):
                st.json(diag.model_dump())

    # -------------------------------------------------------------
    # TAB 2: Conversational Troubleshooting Assistant
    # -------------------------------------------------------------
    with tab_chat:
        st.markdown("#### 💬 Interactive Industrial Troubleshooting Chat")
        st.caption(
            "Converse with the diagnostic assistant. Questions are matched against the technical documentation "
            "library in real time, citing exact page references without hallucination."
        )

        if "chat_history" not in st.session_state:
            st.session_state["chat_history"] = []

        # Clear chat button
        col_chat_title, col_chat_clr = st.columns([4, 1])
        with col_chat_clr:
            if st.button("🧹 Clear Chat History"):
                st.session_state["chat_history"] = []
                st.rerun()

        # Display conversation history
        for msg in st.session_state["chat_history"]:
            with st.chat_message(msg.role):
                st.markdown(msg.content)
                if msg.sources:
                    with st.expander("📚 Grounded Technical Citations"):
                        for s in msg.sources:
                            st.caption(f"• **{s.doc_name}** (Page {s.page_number}, Score: {s.similarity_score:.2f}): *{s.excerpt[:120]}...*")

        # Chat input
        user_input = st.chat_input("Ask about motor vibration, ISO 10816 limits, thermal protection, or LOTO procedures...")
        if user_input:
            # Append user message
            user_msg = ChatMessage(role="user", content=user_input)
            st.session_state["chat_history"].append(user_msg)

            # Get active fault if any
            active_faults = services.db.get_active_faults()
            curr_fault = FaultEvent(**active_faults[0]) if active_faults else None

            # Generate assistant response
            with st.spinner("Searching manuals and generating grounded response..."):
                reply = services.assistant.chat_troubleshoot(
                    user_message=user_input,
                    history=st.session_state["chat_history"][:-1],
                    active_fault=curr_fault
                )
                st.session_state["chat_history"].append(reply)
                st.rerun()
