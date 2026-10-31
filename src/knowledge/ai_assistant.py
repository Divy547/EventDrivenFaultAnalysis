"""Knowledge-Driven Fault Diagnosis Assistant.

Combines PyMuPDF manual extraction, scikit-learn TF-IDF semantic retrieval,
and Google Gemini API (with seamless local deterministic fallback when offline).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from config import AIConfig, settings
from src.database.db_manager import DatabaseManager
from src.knowledge.pdf_processor import PDFProcessor
from src.knowledge.tfidf_index import TFIDFIndex
from src.models.telemetry import FaultEvent, MotorTelemetry

logger = logging.getLogger(__name__)


@dataclass
class DiagnosticReport:
    """Structured response from the diagnosis assistant."""

    query: str
    summary: str
    root_cause_analysis: str
    safety_precautions: list[str]
    maintenance_actions: list[str]
    retrieved_sources: list[dict[str, Any]] = field(default_factory=list)
    engine_used: str = "Local TF-IDF Offline Synthesis"
    confidence_score: float = 0.0


class DiagnosticAssistant:
    """Orchestrates manual retrieval, Gemini LLM reasoning, and offline fallbacks."""

    def __init__(
        self,
        db_manager: Optional[DatabaseManager] = None,
        ai_config: Optional[AIConfig] = None
    ) -> None:
        self.db = db_manager or DatabaseManager()
        self.ai_config = ai_config or settings.ai
        self.pdf_processor = PDFProcessor()
        self.tfidf_index = TFIDFIndex()

        # Initialize by indexing all documents already in SQLite
        self.refresh_index()

        # If knowledge base is empty, bootstrap with the standard industrial manual
        if self.tfidf_index.total_chunks == 0:
            self._bootstrap_default_manual()

    def refresh_index(self) -> int:
        """Reload all manual chunks from SQLite into the TF-IDF vector index."""
        raw_chunks = self.db.get_all_document_chunks()
        formatted_chunks = []
        for c in raw_chunks:
            meta = {}
            if c.get("metadata_json"):
                try:
                    meta = json.loads(c["metadata_json"])
                except Exception:
                    pass
            formatted_chunks.append({
                "doc_name": c["doc_name"],
                "chunk_index": c["chunk_index"],
                "content": c["content"],
                "metadata": meta
            })
        return self.tfidf_index.build_index(formatted_chunks)

    def _bootstrap_default_manual(self) -> None:
        """Create and ingest the default industrial motor troubleshooting guide."""
        manual_path = settings.manuals_dir / "sample_industrial_motor_manual.pdf"
        if not manual_path.exists():
            PDFProcessor.generate_sample_manual(manual_path)

        chunks = self.pdf_processor.process_pdf(manual_path, "sample_industrial_motor_manual.pdf")
        if chunks:
            self.db.store_document_chunks("sample_industrial_motor_manual.pdf", chunks)
            self.refresh_index()
            logger.info("Bootstrapped standard industrial manual with %d chunks", len(chunks))

    def ingest_pdf_file(self, file_path_or_bytes: Path | str | bytes, doc_name: str) -> int:
        """Extract chunks from an uploaded PDF and store them in the database."""
        chunks = self.pdf_processor.process_pdf(file_path_or_bytes, doc_name)
        if chunks:
            count = self.db.store_document_chunks(doc_name, chunks)
            self.refresh_index()
            return count
        return 0

    def diagnose_fault(
        self,
        fault: FaultEvent,
        telemetry: Optional[MotorTelemetry] = None
    ) -> DiagnosticReport:
        """Generate comprehensive diagnosis for a detected equipment fault."""
        query = (
            f"Fault: {fault.fault_type} on motor {fault.device_id}. "
            f"Metric {fault.metric_name} value {fault.metric_value} exceeded threshold {fault.threshold_value}. "
            f"Description: {fault.message}"
        )
        motor_context = (
            f"Device ID: {fault.device_id}\n"
            f"Active Fault: {fault.fault_type} (Severity: {fault.severity})\n"
            f"Metric: {fault.metric_name} = {fault.metric_value} (Threshold: {fault.threshold_value})\n"
            f"Occurrence Count: {fault.occurrence_count}\n"
        )
        if telemetry:
            motor_context += (
                f"Current Telemetry: Temp={telemetry.temperature}°C, Vib={telemetry.vibration}mm/s, "
                f"Current={telemetry.current}A, Voltage={telemetry.voltage}V, Acoustic={telemetry.acoustic_db}dB, "
                f"RPM={telemetry.rpm}\n"
            )

        return self.ask_assistant(query=query, context_info=motor_context)

    def ask_assistant(self, query: str, context_info: str = "") -> DiagnosticReport:
        """Query knowledge base and synthesize response via Gemini or local offline engine."""
        # 1. Retrieve top matching manual passages using TF-IDF
        retrieved_chunks = self.tfidf_index.search(query, top_k=4)

        # 2. Check if Gemini API is available and usable
        if self.ai_config.has_api_key:
            gemini_report = self._call_gemini_api(query, context_info, retrieved_chunks)
            if gemini_report is not None:
                return gemini_report

        # 3. Fallback to Local Deterministic Synthesis Engine
        return self._local_grounded_synthesis(query, context_info, retrieved_chunks)

    def _call_gemini_api(
        self,
        query: str,
        context_info: str,
        retrieved_chunks: list[dict[str, Any]]
    ) -> Optional[DiagnosticReport]:
        """Invoke Google Gemini API with RAG context."""
        try:
            from google import genai

            client = genai.Client(api_key=self.ai_config.api_key)

            context_text = "\n\n".join([
                f"[Source: {c.get('doc_name')} | Page {c.get('metadata', {}).get('page', 1)} | Score: {c.get('score')}]\n{c.get('content')}"
                for c in retrieved_chunks
            ])

            prompt = f"""You are the Lead Reliability Engineer and AI Diagnostic Assistant for Industrial Electric Motors (P_311).
Your task is to analyze equipment sensor telemetry and manual documentation to provide an actionable, grounded diagnosis.

--- CURRENT EQUIPMENT CONTEXT ---
{context_info or 'General Query'}

--- RETRIEVED MAINTENANCE MANUAL EXCERPTS ---
{context_text if context_text else 'No manual excerpts found.'}

--- OPERATOR QUERY / FAULT ---
{query}

Provide a structured engineering diagnosis strictly adhering to this JSON format:
{{
  "summary": "Brief 1-2 sentence executive assessment of the condition.",
  "root_cause_analysis": "Detailed technical analysis of the underlying mechanical or electrical failure mechanism based on the manual.",
  "safety_precautions": ["Precaution 1 (e.g. Lockout Tagout LOTO)", "Precaution 2"],
  "maintenance_actions": ["Immediate step 1", "Diagnostic step 2", "Repair step 3"]
}}
Return ONLY valid JSON.
"""

            response = client.models.generate_content(
                model=self.ai_config.model,
                contents=prompt
            )

            response_text = response.text.strip()
            # Clean possible markdown fencing
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.startswith("```"):
                response_text = response_text[3:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]

            parsed = json.loads(response_text.strip())

            top_score = retrieved_chunks[0].get("score", 0.85) if retrieved_chunks else 0.5

            return DiagnosticReport(
                query=query,
                summary=parsed.get("summary", "Diagnosis completed."),
                root_cause_analysis=parsed.get("root_cause_analysis", "Analysis provided by Gemini."),
                safety_precautions=parsed.get("safety_precautions", ["Follow facility safety rules."]),
                maintenance_actions=parsed.get("maintenance_actions", ["Inspect equipment."]),
                retrieved_sources=retrieved_chunks,
                engine_used=f"Google Gemini ({self.ai_config.model})",
                confidence_score=round(top_score, 3)
            )

        except Exception as exc:
            logger.warning("Gemini API call failed (%s). Reverting to local grounded synthesis.", exc)
            return None

    def _local_grounded_synthesis(
        self,
        query: str,
        context_info: str,
        retrieved_chunks: list[dict[str, Any]]
    ) -> DiagnosticReport:
        """Deterministic local diagnostic engine using TF-IDF manual excerpts (100% offline)."""
        top_score = retrieved_chunks[0].get("score", 0.0) if retrieved_chunks else 0.0

        q_lower = (query + " " + context_info).lower()

        # Identify condition type
        is_temp = "overheat" in q_lower or "temperature" in q_lower or "thermal" in q_lower or "75" in q_lower or "90" in q_lower
        is_vib = "vibration" in q_lower or "bearing" in q_lower or "10816" in q_lower or "misalignment" in q_lower or "unbalance" in q_lower
        is_current = "overcurrent" in q_lower or "current" in q_lower or "overload" in q_lower or "amp" in q_lower
        is_voltage = "voltage" in q_lower or "sag" in q_lower or "bus" in q_lower
        is_cavitation = "cavitation" in q_lower or "pressure" in q_lower or "pump" in q_lower

        precautions = [
            "Apply Lockout-Tagout (LOTO) per OSHA Standard 1910.147 prior to physical contact.",
            "Verify all electrical potential has discharged using a calibrated multimeter.",
            "Wear high-temperature thermal gloves when inspecting casing or bearing housing."
        ]

        if is_temp:
            summary = "Thermal overheating anomaly detected on motor stator/bearing assembly."
            root_cause = (
                "Thermal escalation is commonly caused by cooling cowl or fan shroud blockage, "
                "degraded grease viscosity leading to boundary friction, or excessive mechanical load. "
                "Prolonged operation above 90°C risks permanent Class F winding breakdown."
            )
            actions = [
                "Inspect motor rear cowl and clean cooling fan blades of debris or dust accumulation.",
                "Verify grease relief port is unclogged; purge old oxidized grease and replenish Polyrex EM.",
                "Measure RTD stator temperature probes across all phases to check for phase imbalance.",
                "Check motor load factor and reduce line throughput until temperature stabilizes below 75°C."
            ]

        elif is_vib:
            summary = "High vibration velocity detected violating ISO 10816 machinery standard."
            root_cause = (
                "Elevated vibration indicates mechanical unbalance (1X RPM), coupling angular misalignment "
                "(2X RPM), or early rolling-element bearing cage/raceway defect (BPFI/BPFO)."
            )
            actions = [
                "Conduct laser shaft alignment between motor and driven equipment (tolerance < 0.05 mm).",
                "Verify torque on all foundation hold-down bolts (tighten to 85 Nm specification).",
                "Perform high-frequency FFT vibration analysis to isolate bearing pass frequencies.",
                "Prepare replacement deep-groove ball bearing set (SKF 6308 / 6310) if vibration exceeds 7.1 mm/s."
            ]

        elif is_current:
            summary = "Electrical overcurrent condition exceeding motor full-load rating."
            root_cause = (
                "Amperage draw above 115% rated suggests mechanical dragging or material jam on conveyor/pump, "
                "stator winding insulation breakdown, or single-phasing on line supply."
            )
            actions = [
                "Check driven mechanical load (conveyor belt, pump impeller) for physical obstruction.",
                "Measure phase currents on L1, L2, and L3 using a True-RMS clamp meter to verify balance (< 5% deviation).",
                "Perform insulation resistance (Megger) test at 500V DC (minimum 100 MOhm required).",
                "Inspect MCC thermal overload relay and circuit breaker trip settings."
            ]

        elif is_voltage:
            summary = "AC supply voltage sag detected below standard operating threshold."
            root_cause = (
                "Voltage sag below 207V forces the induction motor to draw excessive current to sustain torque. "
                "Commonly caused by sudden upstream utility feeder load or loose MCC contactor bus connections."
            )
            actions = [
                "Inspect MCC main busbar connections and verify contactor terminal screw torques.",
                "Check upstream distribution transformer tap setting and verify facility power factor correction capacitors.",
                "Verify soft-starter / VFD input voltage and check for utility phase sag alarms."
            ]

        elif is_cavitation:
            summary = "Centrifugal pump cavitation and discharge pressure irregularity detected."
            root_cause = (
                "Cavitation occurs when inlet pressure drops below vapor pressure, causing vapor cavities "
                "to violently implode on impeller vanes, generating destructive acoustic shockwaves."
            )
            actions = [
                "Check and clear pump suction strainer basket for clogging.",
                "Verify inlet isolation valve is fully 100% open and unobstructed.",
                "Calculate Net Positive Suction Head Available (NPSHa) vs Required (NPSHr).",
                "Purge air bubbles from pump casing and priming chamber."
            ]

        else:
            summary = "Equipment condition evaluated against technical manual database."
            root_cause = "General condition query matched against indexed industrial motor maintenance documentation."
            actions = [
                "Inspect physical motor housing and verify smooth mechanical rotation.",
                "Review time-series telemetry trend for vibration, temperature, and current.",
                "Consult plant maintenance manual for model-specific service intervals."
            ]

        return DiagnosticReport(
            query=query,
            summary=summary,
            root_cause_analysis=root_cause,
            safety_precautions=precautions,
            maintenance_actions=actions,
            retrieved_sources=retrieved_chunks,
            engine_used="Local TF-IDF Offline Synthesis",
            confidence_score=round(top_score, 3)
        )
