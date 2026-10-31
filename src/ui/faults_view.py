"""Fault Monitor & Alert Management UI view."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.services import ServiceContainer


def render_faults_view(services: ServiceContainer) -> None:
    st.subheader("🚨 Industrial Fault Monitor & Alert Management")

    active_faults = services.db.get_active_faults()

    if not active_faults:
        st.success("✅ All monitored motors are operating within safe baseline parameters. No active faults.")
    else:
        st.warning(f"⚠️ {len(active_faults)} active equipment alert(s) require operator attention.")

        for fault in active_faults:
            severity = fault["severity"]
            badge_color = "red" if severity == "CRITICAL" else "orange"

            with st.container(border=True):
                col_title, col_actions = st.columns([3, 1])

                with col_title:
                    st.markdown(
                        f"### :{badge_color}[{severity}] `{fault['device_id']}`: {fault['fault_type']}"
                    )
                    st.write(f"**Diagnostic Message:** {fault['message']}")
                    st.write(
                        f"**Trigger Metric:** `{fault['metric_name']}` = **{fault['metric_value']}** "
                        f"(Threshold: {fault['threshold_value']})"
                    )

                    c_meta1, c_meta2, c_meta3 = st.columns(3)
                    with c_meta1:
                        st.caption(f"⏱️ **First Seen:** {fault['first_detected'][:19]}")
                    with c_meta2:
                        st.caption(f"🔄 **Last Seen:** {fault['last_detected'][:19]}")
                    with c_meta3:
                        st.caption(f"📊 **Deduplicated Triggers:** {fault['occurrence_count']}x")

                with col_actions:
                    f_id = fault["fault_id"]

                    if st.button("🤖 AI Diagnosis", key=f"ai_diag_{f_id}", type="primary", use_container_width=True):
                        st.session_state["diagnose_fault_id"] = f_id
                        st.session_state["active_tab"] = "🤖 AI Assistant"
                        st.rerun()

                    if fault["status"] == "ACTIVE":
                        if st.button("👁️ Acknowledge", key=f"ack_{f_id}", use_container_width=True):
                            services.detector.acknowledge_fault(f_id)
                            st.rerun()

                    if st.button("✅ Mark Resolved", key=f"res_{f_id}", use_container_width=True):
                        services.detector.resolve_fault(f_id, "Manually cleared by operator")
                        st.success(f"Fault {f_id} marked as RESOLVED.")
                        st.rerun()

    st.divider()

    # Historical Fault Log
    st.markdown("### 📜 Fault & Alert Event History")
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        status_filter = st.selectbox("Status Filter:", ["ALL", "ACTIVE", "ACKNOWLEDGED", "RESOLVED"], index=0)
    with col_f2:
        dev_filter = st.selectbox("Motor Filter:", ["ALL"] + list(services.simulator.motors.keys()), index=0)

    db_status = None if status_filter == "ALL" else status_filter
    db_dev = None if dev_filter == "ALL" else dev_filter

    history = services.db.get_fault_history(device_id=db_dev, status=db_status, limit=100)

    if history:
        df_hist = pd.DataFrame(history)
        cols_to_show = [
            "fault_id", "device_id", "severity", "fault_type",
            "metric_name", "metric_value", "threshold_value",
            "status", "occurrence_count", "first_detected", "last_detected", "resolved_at"
        ]
        available_cols = [c for c in cols_to_show if c in df_hist.columns]
        st.dataframe(df_hist[available_cols], use_container_width=True, hide_index=True)
    else:
        st.info("No historical alerts matching filter.")
