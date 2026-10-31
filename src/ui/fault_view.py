"""Page 3: Fault Management, Acknowledgement, Resolution & Maintenance Logs."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.services import ServiceContainer


def render_fault_view(services: ServiceContainer) -> None:
    st.subheader("🚨 Industrial Fault Management & Incident Operations")

    # Fetch active faults from SQLite
    active_faults = services.db.get_active_faults()
    crits = [f for f in active_faults if f["severity"] == "CRITICAL"]
    warns = [f for f in active_faults if f["severity"] == "WARNING"]
    acks = [f for f in active_faults if f["status"] == "ACKNOWLEDGED"]
    resolved_count = len(services.db.get_fault_history(status="RESOLVED", limit=500))

    # Top KPI summary row
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.metric("Critical Alarms", len(crits), delta=f"{len(crits)} Immediate Action" if crits else "Normal", delta_color="inverse")
    with k2:
        st.metric("Advisory Warnings", len(warns), delta=f"{len(warns)} Active" if warns else "0", delta_color="inverse")
    with k3:
        st.metric("Acknowledged", len(acks))
    with k4:
        st.metric("Historical Resolved", resolved_count)

    st.write("")

    # Active Faults Operational Section
    st.markdown("### ⚡ Active Anomaly Incident Queue")

    if not active_faults:
        st.success("✅ Zero active equipment alerts. All three industrial motors are operating within safe baseline parameters.")
    else:
        for fault in active_faults:
            f_id = fault["fault_id"]
            sev = fault["severity"]
            badge_class = "badge-critical" if sev == "CRITICAL" else "badge-warning"

            with st.container(border=True):
                col_left, col_right = st.columns([3, 1])

                with col_left:
                    st.markdown(
                        f"<span class='{badge_class}'>● {sev}</span> &nbsp; "
                        f"**`{fault['device_id']}`**: **{fault['fault_type']}**",
                        unsafe_allow_html=True
                    )
                    st.write(f"**Diagnostic Message:** {fault['message']}")
                    st.write(
                        f"**Trigger Metric:** `{fault['metric_name']}` = **{fault['metric_value']:.2f}** "
                        f"(Threshold: **{fault['threshold_value']:.2f}**)"
                    )

                    c_m1, c_m2, c_m3 = st.columns(3)
                    with c_m1:
                        st.caption(f"⏱️ First Detected: `{fault['first_detected'][:19]}`")
                    with c_m2:
                        st.caption(f"🔄 Last Detected: `{fault['last_detected'][:19]}`")
                    with c_m3:
                        st.caption(f"📊 Deduplicated Triggers: **{fault['occurrence_count']}x**")

                with col_right:
                    # Action 1: Forward to AI Diagnosis
                    if st.button("🤖 AI Diagnosis", key=f"btn_ai_{f_id}", type="primary", use_container_width=True):
                        st.session_state["diagnose_fault_id"] = f_id
                        st.session_state["active_nav"] = "AI Diagnosis"
                        st.rerun()

                    # Action 2: Acknowledge
                    if fault["status"] == "ACTIVE":
                        if st.button("👁️ Acknowledge", key=f"btn_ack_{f_id}", use_container_width=True):
                            services.detector.acknowledge_fault(f_id)
                            st.success(f"Acknowledged alert {f_id}")
                            st.rerun()

                # Resolution Expander with Technician Notes
                with st.expander(f"🛠️ Resolve Incident `{f_id}` & Record Maintenance Note"):
                    res_col1, res_col2 = st.columns([1, 2])
                    with res_col1:
                        tech_name = st.text_input("Technician Name:", value="Lead Reliability Tech", key=f"tech_{f_id}")
                    with res_col2:
                        tech_note = st.text_input("Action Taken / Notes:", value="Cleaned fan cowl and lubricated bearings per manual", key=f"note_{f_id}")

                    if st.button("Mark Resolved & File Maintenance Record", key=f"btn_res_{f_id}", type="secondary"):
                        services.detector.resolve_fault(
                            fault_id=f_id,
                            technician_note=tech_note,
                            technician_name=tech_name
                        )
                        st.success(f"Incident `{f_id}` resolved and maintenance log created.")
                        st.rerun()

    st.divider()

    # Historical Logs Tabs
    tab_hist, tab_maint = st.tabs(["📜 Historical Incident Log", "🛠️ Technician Maintenance Records"])

    with tab_hist:
        col_flt1, col_flt2 = st.columns(2)
        with col_flt1:
            stat_filter = st.selectbox("Status Filter:", ["ALL", "ACTIVE", "ACKNOWLEDGED", "RESOLVED"], index=0, key="hist_stat_filt")
        with col_flt2:
            dev_filter = st.selectbox("Equipment Filter:", ["ALL"] + list(services.simulator.motors.keys()), index=0, key="hist_dev_filt")

        f_stat = None if stat_filter == "ALL" else stat_filter
        f_dev = None if dev_filter == "ALL" else dev_filter

        hist_records = services.db.get_fault_history(device_id=f_dev, status=f_stat, limit=100)

        if hist_records:
            df_h = pd.DataFrame(hist_records)
            cols_show = [
                "fault_id", "device_id", "severity", "fault_type",
                "metric_name", "metric_value", "threshold_value",
                "status", "occurrence_count", "first_detected", "last_detected", "resolved_at"
            ]
            avail = [c for c in cols_show if c in df_h.columns]
            st.dataframe(df_h[avail], use_container_width=True, hide_index=True)
        else:
            st.info("No historical alerts matching selected filter.")

    with tab_maint:
        maint_logs = services.db.get_maintenance_logs(limit=50)
        if maint_logs:
            df_m = pd.DataFrame(maint_logs)
            st.dataframe(df_m, use_container_width=True, hide_index=True)
        else:
            st.info("No maintenance interventions logged yet.")
