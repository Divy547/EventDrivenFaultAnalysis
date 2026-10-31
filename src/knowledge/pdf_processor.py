"""PyMuPDF PDF manual extraction and sample manual generation."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any, Optional
import pymupdf

logger = logging.getLogger(__name__)


class PDFProcessor:
    """Extracts, cleans, and chunks industrial PDF manuals using PyMuPDF."""

    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 80) -> None:
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def process_pdf_with_metadata(
        self,
        pdf_source: Path | str | bytes,
        doc_name: str
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Extract text chunks and complete document metadata using PyMuPDF.

        Returns:
            Tuple of (doc_metadata: dict, chunks: list[dict])
        """
        chunks: list[dict[str, Any]] = []
        doc_metadata: dict[str, Any] = {
            "doc_name": doc_name,
            "file_size_bytes": 0,
            "page_count": 0,
            "sha256_hash": "",
            "title": doc_name,
            "author": "Industrial Documentation",
        }

        try:
            if isinstance(pdf_source, (bytes, bytearray)):
                raw_bytes = bytes(pdf_source)
                doc = pymupdf.open(stream=raw_bytes, filetype="pdf")
                doc_metadata["file_size_bytes"] = len(raw_bytes)
                doc_metadata["sha256_hash"] = hashlib.sha256(raw_bytes).hexdigest()
            else:
                p = Path(pdf_source)
                raw_bytes = p.read_bytes()
                doc = pymupdf.open(str(p))
                doc_metadata["file_size_bytes"] = len(raw_bytes)
                doc_metadata["sha256_hash"] = hashlib.sha256(raw_bytes).hexdigest()

            doc_metadata["page_count"] = len(doc)
            meta = doc.metadata or {}
            if meta.get("title"):
                doc_metadata["title"] = meta["title"]
            if meta.get("author"):
                doc_metadata["author"] = meta["author"]

            chunk_id = 0
            for page_idx in range(len(doc)):
                page = doc[page_idx]
                page_num = page_idx + 1
                text = page.get_text("text").strip()
                if not text:
                    continue

                # Segment page into paragraphs or overlapping chunks
                paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

                current_chunk = ""
                for p in paragraphs:
                    if len(current_chunk) + len(p) < self.chunk_size:
                        current_chunk += ("\n" + p if current_chunk else p)
                    else:
                        if current_chunk:
                            chunks.append({
                                "chunk_id": chunk_id,
                                "doc_name": doc_name,
                                "page": page_num,
                                "content": current_chunk.strip(),
                                "metadata": {
                                    "doc_name": doc_name,
                                    "page": page_num,
                                    "chunk_id": chunk_id,
                                    "char_count": len(current_chunk.strip())
                                }
                            })
                            chunk_id += 1
                        # Start new chunk with overlap
                        current_chunk = p

                if current_chunk:
                    chunks.append({
                        "chunk_id": chunk_id,
                        "doc_name": doc_name,
                        "page": page_num,
                        "content": current_chunk.strip(),
                        "metadata": {
                            "doc_name": doc_name,
                            "page": page_num,
                            "chunk_id": chunk_id,
                            "char_count": len(current_chunk.strip())
                        }
                    })
                    chunk_id += 1

            doc.close()
            logger.info("Extracted %d chunks from %s (%d pages)", len(chunks), doc_name, doc_metadata["page_count"])
            return doc_metadata, chunks

        except Exception as exc:
            logger.error("Failed to extract PDF %s: %s", doc_name, exc)
            return doc_metadata, []

    def process_pdf(self, pdf_source: Path | str | bytes, doc_name: str) -> list[dict[str, Any]]:
        """Extract text chunks with metadata from a PDF file path or raw bytes (backwards compatible)."""
        _, chunks = self.process_pdf_with_metadata(pdf_source, doc_name)
        return chunks

    @staticmethod
    def generate_sample_manual(output_path: Path | str) -> Path:
        """Create a multi-page Industrial Motor Troubleshooting Manual PDF using PyMuPDF."""
        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        doc = pymupdf.open()

        # Page 1: Overview & Thermal Limits
        p1 = doc.new_page()
        text_p1 = (
            "HCL P_311 INDUSTRIAL MOTOR FAULT DIAGNOSIS MANUAL\n"
            "Document ID: MAN-IND-2026-V3 | Classification: Industrial Maintenance\n\n"
            "SECTION 1: EQUIPMENT OVERVIEW & THERMAL GUIDELINES\n"
            "1.1 Scope and Machinery Classes:\n"
            "This technical standard applies to Class II and Class III medium induction motors (10kW - 45kW),\n"
            "specifically Centrifugal Pump Motors (MOTOR-PUMP-01), Heavy Belt Conveyors (MOTOR-CONV-02),\n"
            "and Twin-Screw Compressors (MOTOR-COMP-03).\n\n"
            "1.2 Thermal Thresholds & Overheating Fault Mode:\n"
            "- Continuous Safe Operating Zone: 30°C to 75°C casing temperature.\n"
            "- Advisory Warning Zone: 75°C to 89°C. Causes: cooling fan shroud clogged with airborne lint/dust,\n"
            "  high ambient temperature exceeding 40°C, or grease viscosity breakdown.\n"
            "- Critical Shutdown Limit: 90°C and above. Operating above 90°C risks rapid thermal degradation\n"
            "  of Class F winding insulation (NEMA Standard MG-1) leading to turn-to-turn electrical shorts.\n"
            "Recommended Action: Immediately inspect cooling fan cowl, verify ventilation airflow, inspect grease\n"
            "relief port for dried grease blockages, and check stator RTD sensors for phase imbalance."
        )
        p1.insert_text((40, 50), text_p1, fontsize=10)

        # Page 2: Vibration & ISO 10816-3 Standards
        p2 = doc.new_page()
        text_p2 = (
            "SECTION 2: VIBRATION ANALYSIS & ISO 10816-3 CRITERIA\n\n"
            "2.1 ISO 10816-3 Severity Zones for Rigid/Flexible Mounted Motors:\n"
            "- Zone A / B (Good / Satisfactory): 0.0 - 2.8 mm/s RMS. Smooth mechanical operation.\n"
            "- Zone C (Warning): 2.8 - 4.5 mm/s RMS. Unrestricted long-term operation not permitted.\n"
            "- Zone D (Critical): Above 7.1 mm/s RMS. Machine damage imminent. Trip equipment.\n\n"
            "2.2 Diagnostic Indicators for Elevated Vibration:\n"
            "- 1X RPM Dominant Peak: Mechanical unbalance of rotor or cooling fan impeller.\n"
            "- 2X RPM Peak with High Axial Vibration: Angular or parallel shaft misalignment at coupling.\n"
            "- High-Frequency (>1000 Hz) Non-Synchronous Peaks: Rolling element bearing wear.\n"
            "  Early signs include micro-spalling on bearing inner raceway (BPFI) or ball elements (BSF).\n"
            "Recommended Action: Lockout-tagout (LOTO) motor, perform dial indicator or laser shaft alignment,\n"
            "check foundation bolt torque (tighten to 85 Nm), and replenish Polyrex EM synthetic bearing grease.\n"
            "Replace bearing assembly (SKF 6308 / 6310 deep-groove) if vibration persists above 7.1 mm/s."
        )
        p2.insert_text((40, 50), text_p2, fontsize=10)

        # Page 3: Electrical Overcurrent & Voltage Sags
        p3 = doc.new_page()
        text_p3 = (
            "SECTION 3: ELECTRICAL OVERLOAD & POWER QUALITY ANOMALIES\n\n"
            "3.1 Overcurrent Diagnostics:\n"
            "- Rated full-load amperes (FLA): MOTOR-PUMP-01 (28A), MOTOR-CONV-02 (21A), MOTOR-COMP-03 (41A).\n"
            "- Warning Threshold: Amperage > 115% FLA for > 15 seconds.\n"
            "- Critical Threshold: Amperage > 135% FLA. Risk of immediate thermal breaker trip or stator damage.\n"
            "Root Causes: Mechanical jamming on conveyor belt, discharge valve shutoff (deadheading) on pump,\n"
            "viscous slurry buildup, or single-phasing condition.\n\n"
            "3.2 Supply Voltage Sags & Bus Drops:\n"
            "- Nominal supply voltage: 230V line-to-neutral (400V line-to-line 3-phase AC).\n"
            "- Voltage Sag Warning: Supply voltage drops below 207V (-10%).\n"
            "- Voltage Sag Critical: Supply voltage drops below 195V (-15%).\n"
            "Under voltage sag, induction motors draw proportionately higher current to sustain shaft torque\n"
            "(Torque is proportional to V^2). This triggers sudden stator overheating without mechanical fault.\n"
            "Recommended Action: Check MCC contactor contacts for pitting, verify transformer tap settings,\n"
            "measure individual phase currents with clamp meter, and confirm soft-starter / VFD bus voltage."
        )
        p3.insert_text((40, 50), text_p3, fontsize=10)

        # Page 4: Acoustic Noise, Cavitation, and Compound Failures
        p4 = doc.new_page()
        text_p4 = (
            "SECTION 4: ACOUSTIC NOISE & CENTRIFUGAL PUMP CAVITATION\n\n"
            "4.1 Acoustic Decibel Limits:\n"
            "- Normal baseline: 65 dB - 76 dB.\n"
            "- Warning Limit: 85 dB (OSHA 8-hour continuous threshold).\n"
            "- Critical Limit: 95 dB. High risk of mechanical destruction or hearing hazard.\n\n"
            "4.2 Centrifugal Pump Cavitation Phenomena (MOTOR-PUMP-01):\n"
            "Cavitation occurs when suction pressure drops below liquid vapor pressure, forming vapor bubbles\n"
            "that collapse violently against the pump impeller and casing.\n"
            "Symptoms: Loud rattling / gravel noise (>88 dB), erratic discharge pressure drop below 3.0 bar,\n"
            "and localized vibration spikes.\n"
            "Remedy: Clear suction strainer, verify suction valve is 100% open, check net positive suction\n"
            "head (NPSH), and purge entrapped air pockets.\n\n"
            "4.3 Compound Bearing Failure (Vibration > 5.5 mm/s AND Temperature > 80°C):\n"
            "This combination indicates total breakdown of boundary lubrication film. Metal-to-metal contact is\n"
            "actively welding microscopic asperities, leading to rapid bearing cage disintegration and shaft seizure.\n"
            "Emergency Procedure: Immediate emergency shutdown. Do not attempt restart without bearing replacement."
        )
        p4.insert_text((40, 50), text_p4, fontsize=10)

        doc.save(str(out_path))
        doc.close()
        logger.info("Generated sample troubleshooting manual at: %s", out_path)
        return out_path
