"""Knowledge-Driven AI Diagnostic Service and Conversational Troubleshooting Assistant.

Integrates PyMuPDF, scikit-learn TF-IDF semantic retrieval, and the official
google-genai Python SDK with robust deterministic demo fallbacks when offline or unauthenticated.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from config import AIConfig, settings
from src.database.db_manager import DatabaseManager
from src.knowledge.pdf_processor import PDFProcessor
from src.knowledge.tfidf_index import TFIDFIndex
from src.models.diagnosis import (
    ChatMessage,
    DocumentSourceReference,
    QualifiedConfidence,
    StructuredFaultDiagnosis,
)
from src.models.telemetry import FaultEvent, MotorTelemetry

logger = logging.getLogger(__name__)


class DiagnosticAssistant:
    """Enterprise RAG Diagnostic Assistant and Conversational Troubleshooting Engine."""

    def __init__(
        self,
        db_manager: Optional[DatabaseManager] = None,
        ai_config: Optional[AIConfig] = None
    ) -> None:
        self.db = db_manager or DatabaseManager()
        self.ai_config = ai_config or settings.ai
        self.pdf_processor = PDFProcessor()
        self.tfidf_index = TFIDFIndex()

        # Initialize TF-IDF index from SQLite
        self.refresh_index()

        # Bootstrap default industrial equipment manual if empty
        if self.tfidf_index.total_chunks == 0:
            self._bootstrap_default_manual()

    def refresh_index(self) -> int:
        """Reload all manual chunks from SQLite into the in-memory TF-IDF index."""
        raw_chunks = self.db.get_all_document_chunks()
        formatted = []
        for c in raw_chunks:
            meta = {}
            if c.get("metadata_json"):
                try:
                    meta = json.loads(c["metadata_json"])
                except Exception:
                    pass
            page_num = c.get("page_number") or meta.get("page", 1)
            formatted.append({
                "chunk_id": c.get("chunk_index", 0),
                "doc_name": c["doc_name"],
                "page": int(page_num),
                "content": c["content"],
                "metadata": meta
            })
        return self.tfidf_index.build_index(formatted)

    def _bootstrap_default_manual(self) -> None:
        """Create and index the default industrial motor troubleshooting standard manual."""
        manual_path = settings.manuals_dir / "sample_industrial_motor_manual.pdf"
        if not manual_path.exists():
            PDFProcessor.generate_sample_manual(manual_path)

        meta, chunks = self.pdf_processor.process_pdf_with_metadata(
            manual_path, "sample_industrial_motor_manual.pdf"
        )
        if chunks:
            self.db.store_document_with_metadata(
                doc_name="sample_industrial_motor_manual.pdf",
                file_size_bytes=meta["file_size_bytes"],
                page_count=meta["page_count"],
                sha256_hash=meta["sha256_hash"],
                chunks=chunks,
                extra_meta={"title": meta.get("title"), "author": meta.get("author")}
            )
            self.refresh_index()
            logger.info("Bootstrapped standard industrial manual (%d chunks)", len(chunks))

    def ingest_pdf_file(
        self,
        file_path_or_bytes: Path | str | bytes,
        doc_name: str
    ) -> tuple[dict[str, Any], int]:
        """Extract chunks, record metadata in SQLite, and update TF-IDF index."""
        meta, chunks = self.pdf_processor.process_pdf_with_metadata(file_path_or_bytes, doc_name)
        if not chunks:
            return meta, 0

        count = self.db.store_document_with_metadata(
            doc_name=doc_name,
            file_size_bytes=meta["file_size_bytes"],
            page_count=meta["page_count"],
            sha256_hash=meta["sha256_hash"],
            chunks=chunks,
            extra_meta={"title": meta.get("title"), "author": meta.get("author")}
        )
        self.refresh_index()
        return meta, count

    def delete_document(self, doc_name: str) -> bool:
        """Completely remove a document, its metadata, and chunks, updating TF-IDF index."""
        ok = self.db.delete_document(doc_name)
        if ok:
            self.tfidf_index.delete_document(doc_name)
            logger.info("Deleted document %s from database and TF-IDF index", doc_name)
        return ok

    # --- Structured Fault Diagnosis Service ---

    def diagnose_fault(
        self,
        fault: FaultEvent,
        telemetry: Optional[MotorTelemetry] = None
    ) -> StructuredFaultDiagnosis:
        """Generate validated, structured fault diagnosis citing genuine manual sources."""
        # 1. Retrieve verified document references using TF-IDF
        query = (
            f"Fault: {fault.fault_type} on motor {fault.device_id}. "
            f"Metric: {fault.metric_name} = {fault.metric_value} (threshold {fault.threshold_value}). "
            f"{fault.message}"
        )
        verified_sources = self.tfidf_index.search_source_references(query=query, top_k=3, min_score=0.03)

        # 2. Check Gemini API availability
        if self.ai_config.has_api_key:
            diagnosis = self._call_gemini_diagnosis(fault, telemetry, verified_sources)
            if diagnosis is not None:
                return diagnosis

        # 3. Explicit Deterministic Fallback (if no API key, quota exhausted, or call failed)
        reason = "GEMINI_API_KEY environment variable is not configured" if not self.ai_config.has_api_key else "API call failed or quota exceeded"
        return self._generate_deterministic_diagnosis(fault, telemetry, verified_sources, fallback_reason=reason)

    def _call_gemini_diagnosis(
        self,
        fault: FaultEvent,
        telemetry: Optional[MotorTelemetry],
        sources: list[DocumentSourceReference]
    ) -> Optional[StructuredFaultDiagnosis]:
        """Invoke Google Gemini API with strict structured schema validation."""
        try:
            from google import genai
            from google.genai import errors

            client = genai.Client(api_key=self.ai_config.api_key)

            # Grounding context from retrieved sources
            sources_context = "\n\n".join([
                f"[Source Document: {s.doc_name} | Page: {s.page_number} | Relevance: {s.similarity_score:.2f}]\n{s.excerpt}"
                for s in sources
            ]) if sources else "No matching equipment manual excerpts found."

            tel_info = "Not provided"
            if telemetry:
                tel_info = (
                    f"Temperature: {telemetry.temperature}°C, Vibration: {telemetry.vibration} mm/s, "
                    f"Current: {telemetry.current} A, Voltage: {telemetry.voltage} V, Speed: {telemetry.rpm} RPM, "
                    f"Acoustic Noise: {telemetry.acoustic_db} dB, Pressure: {telemetry.pressure_bar} bar"
                )

            system_instruction = (
                "You are an Industrial Reliability Engineer for electric motors (P_311). "
                "Analyze the provided equipment telemetry and manual excerpts. "
                "Return a strict JSON object matching the requested schema. "
                "CRITICAL RULES:\n"
                "1. NEVER fabricate or invent document sources. Cite ONLY from the provided manual excerpts.\n"
                "2. An algorithmic diagnosis is ALWAYS preliminary until physically confirmed by a field technician. "
                "Set is_verified to false.\n"
                "3. Ground all observations and possible causes in the empirical telemetry and cited manual text."
            )

            prompt = f"""Target Motor: {fault.device_id}
Fault Type: {fault.fault_type}
Severity: {fault.severity}
Triggering Metric: {fault.metric_name} = {fault.metric_value} (Limit: {fault.threshold_value})
Current Telemetry: {tel_info}
Trigger Count: {fault.occurrence_count}

Grounding Manual Excerpts:
{sources_context}

Output format must be valid JSON:
{{
  "fault_title": "Descriptive Technical Fault Name",
  "severity": "{fault.severity}",
  "device_id": "{fault.device_id}",
  "observations": ["Obs 1", "Obs 2"],
  "possible_causes": ["Cause 1 based on manual", "Cause 2"],
  "recommended_actions": ["Safety/LOTO step", "Action step", "Repair step"],
  "evidence": ["Data point 1 matching manual criterion", "Data point 2"],
  "qualified_confidence": {{
    "level": "HIGH" or "MEDIUM" or "LOW",
    "score": 0.85,
    "explanation": "Rationale for confidence based on data and manual match"
  }}
}}
"""

            response = client.models.generate_content(
                model=self.ai_config.model,
                contents=prompt,
                config={"system_instruction": system_instruction}
            )

            raw_text = response.text.strip()
            if raw_text.startswith("```json"):
                raw_text = raw_text[7:]
            if raw_text.startswith("```"):
                raw_text = raw_text[3:]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]

            parsed = json.loads(raw_text.strip())

            # Enforce that sources come strictly from verified_sources (never hallucinated by LLM)
            top_score = sources[0].similarity_score if sources else 0.5
            conf_data = parsed.get("qualified_confidence", {})
            conf_score = float(conf_data.get("score", top_score))
            conf_level = conf_data.get("level", "HIGH" if conf_score >= 0.75 else "MEDIUM")
            conf_expl = conf_data.get("explanation", f"Correlated with {len(sources)} verified manual citations.")

            return StructuredFaultDiagnosis(
                fault_title=parsed.get("fault_title", f"{fault.fault_type} on {fault.device_id}"),
                severity=fault.severity,
                device_id=fault.device_id,
                timestamp=datetime.now(timezone.utc),
                observations=parsed.get("observations", [f"Metric {fault.metric_name} reached {fault.metric_value}"]),
                possible_causes=parsed.get("possible_causes", ["Mechanical friction or electrical anomaly."]),
                recommended_actions=parsed.get("recommended_actions", ["Perform physical inspection with LOTO."]),
                evidence=parsed.get("evidence", [f"{fault.metric_name} exceeded threshold {fault.threshold_value}"]),
                sources=sources,  # Real, verified references only
                qualified_confidence=QualifiedConfidence(
                    level=conf_level,
                    score=min(1.0, max(0.0, conf_score)),
                    explanation=conf_expl
                ),
                is_verified=False,
                verification_status="Preliminary (Pending Physical Inspection)",
                engine_used=f"Google Gemini ({self.ai_config.model})"
            )

        except Exception as exc:
            reason = self._format_error_reason(exc)
            logger.warning("Gemini API call failed (%s). Activating deterministic fallback.", reason)
            return self._generate_deterministic_diagnosis(fault, telemetry, sources, fallback_reason=reason)

    def _generate_deterministic_diagnosis(
        self,
        fault: FaultEvent,
        telemetry: Optional[MotorTelemetry],
        sources: list[DocumentSourceReference],
        fallback_reason: str
    ) -> StructuredFaultDiagnosis:
        """Deterministic, grounded diagnostic synthesis engine for offline / unauthenticated operation."""
        dev_id = fault.device_id
        f_type = fault.fault_type
        metric = fault.metric_name
        val = fault.metric_value
        thresh = fault.threshold_value
        sev = fault.severity

        observations = [
            f"Observed {metric} = {val:.2f} violating engineering limit ({thresh:.2f}).",
            f"Alert status: {sev} with {fault.occurrence_count} deduplicated trigger events.",
        ]
        if telemetry:
            observations.append(
                f"Operating metrics: Temp={telemetry.temperature:.1f}°C, Vib={telemetry.vibration:.2f}mm/s, "
                f"Current={telemetry.current:.1f}A, Speed={telemetry.rpm:.0f}RPM, Acoustic={telemetry.acoustic_db:.1f}dB."
            )

        # Build condition-specific causes, actions, and evidence based on the industrial manual
        if "OVERHEAT" in f_type or metric == "temperature":
            title = f"Thermal Overheating & Insulation Degradation on {dev_id}"
            causes = [
                "Cooling fan cowl or air intake shroud obstructed by ambient debris or lint.",
                "Dried or oxidized bearing grease causing boundary friction in bearing housing.",
                "Excessive continuous load factor driving elevated I²R winding copper losses.",
                "Stator phase voltage unbalance (> 2%) inducing counter-rotational negative-sequence currents."
            ]
            actions = [
                "Apply Lockout-Tagout (LOTO) per OSHA Standard 1910.147 prior to physical contact.",
                "Inspect motor rear cowl and clean cooling fan impeller blades of dust buildup.",
                "Clear grease relief port; purge old degraded grease and replenish Polyrex EM synthetic lubricant.",
                "Measure phase voltages and currents using True-RMS meter to confirm phase balance within 2%.",
                "Reduce operational throughput until casing temperature stabilizes below 75°C."
            ]
            evidence = [
                f"Measured temperature of {val:.1f}°C violates NEMA Class F continuous limit (75.0°C).",
                "Thermal escalation matches manual Section 1.2 on ventilation blockage and grease viscosity breakdown."
            ]
            conf_score = 0.88 if sources else 0.70

        elif "BEARING" in f_type or metric == "vibration":
            title = f"Mechanical Vibration & Bearing Defect on {dev_id}"
            causes = [
                "Rolling element bearing degradation (micro-spalling on inner race BPFI or outer race BPFO).",
                "Angular or parallel shaft misalignment between motor shaft and driven load.",
                "Dynamic mechanical unbalance of rotor or cooling fan impeller.",
                "Loose foundation anchor bolts causing structural resonance."
            ]
            actions = [
                "Enforce Lockout-Tagout (LOTO) and verify zero stored energy before inspection.",
                "Perform laser shaft alignment between motor and driven unit (tolerance < 0.05 mm).",
                "Verify foundation hold-down bolts with calibrated torque wrench (tighten to 85 Nm).",
                "Collect high-frequency accelerometer spectrum to identify ball pass frequencies.",
                "Prepare replacement bearing set (SKF 6308 / 6310) if vibration remains above 7.1 mm/s."
            ]
            evidence = [
                f"Vibration velocity of {val:.2f} mm/s violates ISO 10816 Zone D threshold (7.1 mm/s).",
                "Kinematic pattern corresponds with manual Section 2 criteria for rolling element wear."
            ]
            conf_score = 0.90 if sources else 0.72

        elif "OVERLOAD" in f_type or "CURRENT" in f_type or metric == "current":
            title = f"Electrical Overcurrent & Overload Condition on {dev_id}"
            causes = [
                "Mechanical conveyor jamming or pump discharge deadheading causing rotor slip.",
                "Single-phasing or loss of phase causing remaining phases to draw excessive current.",
                "Stator winding turn-to-turn insulation breakdown.",
                "Improper MCC overload relay thermal heater calibration."
            ]
            actions = [
                "Isolate power feed via MCC breaker and lock out.",
                "Inspect conveyor belt / pump impeller for physical foreign object obstruction.",
                "Perform Megger insulation resistance test at 500V DC (minimum 100 MΩ required).",
                "Check contactor contact points for pitting or oxidation."
            ]
            evidence = [
                f"Phase current {val:.1f}A exceeds rated full-load current threshold ({thresh:.1f}A).",
                "Direct correlation with manual Section 3.1 overcurrent diagnostics."
            ]
            conf_score = 0.86 if sources else 0.68

        elif "VOLTAGE" in f_type or metric == "voltage":
            title = f"Supply Voltage Sag & Power Quality Anomaly on {dev_id}"
            causes = [
                "Facility main distribution bus sag due to heavy upstream industrial starting loads.",
                "Loose MCC busbar terminal connection or pitted contactor contacts.",
                "Distribution transformer tap setting deviation."
            ]
            actions = [
                "Check facility power quality meter for upstream utility feeder disturbances.",
                "Inspect MCC busbar bolted connections with thermal imaging camera.",
                "Verify VFD or soft-starter input line voltage."
            ]
            evidence = [
                f"Line voltage dropped to {val:.1f}V (below critical threshold {thresh:.1f}V).",
                "Matches manual Section 3.2 on induction motor torque compensation under voltage dip."
            ]
            conf_score = 0.85 if sources else 0.65

        elif "COMPOUND" in f_type:
            title = f"CRITICAL Compound Bearing Seizure Threat on {dev_id}"
            causes = [
                "Total breakdown of boundary lubrication film causing metal-on-metal friction welding.",
                "Catastrophic bearing cage collapse with violent mechanical vibration and friction heat."
            ]
            actions = [
                "IMMEDIATE EMERGENCY SHUTDOWN: Trip breaker and apply LOTO immediately.",
                "Do NOT attempt restart without complete mechanical bearing assembly overhaul.",
                "Inspect motor shaft journal for scoring, galling, or thermal blueing."
            ]
            evidence = [
                f"Simultaneous elevated vibration ({val:.2f} mm/s) and severe casing heat.",
                "Complies with manual Section 4.3 compound failure criteria."
            ]
            conf_score = 0.94 if sources else 0.75

        else:
            title = f"Equipment Anomaly on {dev_id}: {f_type}"
            causes = ["Operational deviation beyond configured baseline parameters."]
            actions = [
                "Perform physical visual and audible inspection under LOTO.",
                "Review historical telemetry trends."
            ]
            evidence = [f"{metric} reached {val:.2f} (threshold: {thresh:.2f})."]
            conf_score = 0.70

        # Adjust confidence level
        conf_level: Any = "HIGH" if conf_score >= 0.80 else ("MEDIUM" if conf_score >= 0.60 else "LOW")
        source_count = len(sources)
        expl = (
            f"Grounding correlation: {source_count} verified manual excerpts cited. "
            f"Calculated from empirical telemetry exceeding rule threshold by {abs(val - thresh):.1f} units. "
            f"Diagnosis is deterministic and unconfirmed by physical inspection."
        )

        return StructuredFaultDiagnosis(
            fault_title=title,
            severity=sev,
            device_id=dev_id,
            timestamp=datetime.now(timezone.utc),
            observations=observations,
            possible_causes=causes,
            recommended_actions=actions,
            evidence=evidence,
            sources=sources,  # Real verified sources only
            qualified_confidence=QualifiedConfidence(
                level=conf_level,
                score=round(conf_score, 2),
                explanation=expl
            ),
            is_verified=False,
            verification_status="Preliminary (Pending Physical Inspection)",
            engine_used="Deterministic Demo Fallback (Offline Mode)",
            fallback_reason=fallback_reason
        )

    # --- Conversational Troubleshooting Assistant ---

    def chat_troubleshoot(
        self,
        user_message: str,
        history: Optional[list[ChatMessage]] = None,
        active_fault: Optional[FaultEvent] = None,
        telemetry: Optional[MotorTelemetry] = None
    ) -> ChatMessage:
        """Interactive conversational troubleshooting grounded in equipment manuals."""
        # Retrieve verified passages
        query = user_message
        if active_fault:
            query = f"{user_message} {active_fault.fault_type} {active_fault.metric_name}"

        sources = self.tfidf_index.search_source_references(query=query, top_k=3, min_score=0.03)

        if self.ai_config.has_api_key:
            msg = self._call_gemini_chat(user_message, history, active_fault, telemetry, sources)
            if msg is not None:
                return msg

        # Fallback to deterministic conversational assistant
        reason = "GEMINI_API_KEY environment variable is not configured" if not self.ai_config.has_api_key else "Gemini API unavailable or quota exhausted"
        return self._generate_deterministic_chat_response(user_message, active_fault, telemetry, sources, fallback_reason=reason)

    def _call_gemini_chat(
        self,
        user_message: str,
        history: Optional[list[ChatMessage]],
        active_fault: Optional[FaultEvent],
        telemetry: Optional[MotorTelemetry],
        sources: list[DocumentSourceReference]
    ) -> Optional[ChatMessage]:
        """Invoke Gemini API for conversational troubleshooting with RAG context."""
        try:
            from google import genai

            client = genai.Client(api_key=self.ai_config.api_key)

            context_chunks = "\n\n".join([
                f"[Document: {s.doc_name} | Page: {s.page_number}]\n{s.excerpt}"
                for s in sources
            ]) if sources else "No manual passages matched this specific query."

            fault_context = "No active fault selected."
            if active_fault:
                fault_context = (
                    f"Active Fault: {active_fault.fault_type} on {active_fault.device_id} "
                    f"({active_fault.metric_name}={active_fault.metric_value}, Limit={active_fault.threshold_value})"
                )

            system_instruction = (
                "You are an Industrial Reliability Engineering Assistant (P_311). "
                "Help the operator troubleshoot industrial motor equipment. "
                "Base your response ONLY on the provided manual excerpts and physical telemetry. "
                "NEVER fabricate manual references. Cite exact document names and page numbers when mentioning rules. "
                "Always emphasize safety precautions (OSHA LOTO) before mechanical intervention."
            )

            # Build conversation context
            chat_context = ""
            if history:
                for h in history[-4:]:  # Include last 4 turns
                    chat_context += f"{h.role.upper()}: {h.content}\n"

            prompt = f"""--- EQUIPMENT CONTEXT ---
{fault_context}

--- TECHNICAL MANUAL REFERENCES ---
{context_chunks}

--- CONVERSATION HISTORY ---
{chat_context}
USER: {user_message}
ASSISTANT:"""

            response = client.models.generate_content(
                model=self.ai_config.model,
                contents=prompt,
                config={"system_instruction": system_instruction}
            )

            return ChatMessage(
                role="assistant",
                content=response.text.strip(),
                timestamp=datetime.now(timezone.utc),
                sources=sources,
                engine_used=f"Google Gemini ({self.ai_config.model})"
            )

        except Exception as exc:
            reason = self._format_error_reason(exc)
            logger.warning("Gemini chat call failed (%s). Reverting to deterministic assistant.", reason)
            return None

    def _generate_deterministic_chat_response(
        self,
        user_message: str,
        active_fault: Optional[FaultEvent],
        telemetry: Optional[MotorTelemetry],
        sources: list[DocumentSourceReference],
        fallback_reason: str
    ) -> ChatMessage:
        """Deterministic conversational responses citing verified manual excerpts without pretending to be Gemini."""
        q = user_message.lower()

        # Build response based on matched manual topics
        response_parts = []
        response_parts.append(f"**[Operating in Offline Deterministic Mode]** *({fallback_reason})*\n")

        if "vibration" in q or "iso" in q or "10816" in q or "bearing" in q:
            response_parts.append(
                "### ISO 10816 Vibration Diagnostics\n"
                "According to **Section 2 of the Industrial Motor Diagnosis Manual**:\n"
                "- **Zone A / B (0.0 – 2.8 mm/s RMS):** Satisfactory baseline condition.\n"
                "- **Zone C (2.8 – 4.5 mm/s RMS):** Warning zone. Long-term unrestricted operation not advised.\n"
                "- **Zone D (> 7.1 mm/s RMS):** Critical zone. Machinery damage is imminent; trip equipment immediately.\n\n"
                "**Action Plan:** Perform laser alignment (coupling tolerance < 0.05 mm), check foundation bolts (torque to 85 Nm), "
                "and inspect deep-groove ball bearings (SKF 6308 / 6310) for raceway spalling."
            )
        elif "overheat" in q or "temp" in q or "thermal" in q:
            response_parts.append(
                "### Thermal Overheating Troubleshooting\n"
                "According to **Section 1.2 of the Technical Guidelines**:\n"
                "- Safe continuous limit: **30°C – 75°C** casing temperature.\n"
                "- Warning range: **75°C – 89°C**. Causes: Cowl blockage, high ambient temp, or dried grease.\n"
                "- Critical threshold: **≥ 90°C**. Operating above 90°C risks rapid thermal degradation of Class F winding insulation.\n\n"
                "**Action Plan:** Lock out motor (OSHA LOTO), clear the rear cowl of dust, purge oxidized grease, "
                "and replenish Polyrex EM lubricant."
            )
        elif "current" in q or "amp" in q or "overload" in q:
            response_parts.append(
                "### Overcurrent & Overload Procedures\n"
                "According to **Section 3.1**:\n"
                "- Warning limit is **115% of rated full-load amperes (FLA)**.\n"
                "- Critical threshold is **135% FLA**.\n\n"
                "**Action Plan:** Check driven mechanical equipment for jamming or debris, measure three-phase balance "
                "(< 2% variation), and conduct a Megger 500V DC insulation test."
            )
        elif "cavitation" in q or "pump" in q:
            response_parts.append(
                "### Centrifugal Pump Cavitation Guidelines\n"
                "According to **Section 4.2**:\n"
                "Cavitation creates loud gravel-like acoustic emissions (>88 dB) and erratic discharge pressure drops (< 3.0 bar).\n\n"
                "**Action Plan:** Inspect suction strainer, verify suction valve is 100% open, check Net Positive Suction Head Available (NPSHa), and purge air pockets."
            )
        else:
            response_parts.append(
                "### Equipment Health Guidance\n"
                "I analyzed your question against the technical maintenance manual library. "
                "Please ensure all physical inspections are performed under strict OSHA Lockout-Tagout (LOTO) protocols."
            )

        if sources:
            response_parts.append("\n**Grounded Technical Manual Passages:**")
            for s in sources:
                response_parts.append(f"- **{s.doc_name}** (Page {s.page_number}): *\"{s.excerpt[:160]}...\"*")

        return ChatMessage(
            role="assistant",
            content="\n".join(response_parts),
            timestamp=datetime.now(timezone.utc),
            sources=sources,
            engine_used="Deterministic Demo Fallback (Offline Mode)",
            fallback_reason=fallback_reason
        )

    def _format_error_reason(self, exc: Exception) -> str:
        """Format clean error reason string without leaking credentials."""
        err_str = str(exc).lower()
        if "429" in err_str or "quota" in err_str or "resource_exhausted" in err_str:
            return "Quota exhausted: HTTP 429 ResourceExhausted"
        elif "403" in err_str or "api_key_invalid" in err_str or "invalid api key" in err_str:
            return "Invalid or unauthorized API key"
        elif "timeout" in err_str or "connection" in err_str:
            return f"Network connectivity timeout: {type(exc).__name__}"
        return f"Gemini API Exception: {type(exc).__name__}"
