"""Unit tests for PyMuPDF extraction, TF-IDF indexing, and offline diagnosis."""

import tempfile
from pathlib import Path
import pytest

from config import AIConfig
from src.database.db_manager import DatabaseManager
from src.knowledge.ai_assistant import DiagnosticAssistant
from src.knowledge.pdf_processor import PDFProcessor
from src.knowledge.tfidf_index import TFIDFIndex
from src.models.telemetry import FaultEvent


def test_pdf_processor_and_sample_manual(tmp_path):
    pdf_path = tmp_path / "test_manual.pdf"
    PDFProcessor.generate_sample_manual(pdf_path)
    assert pdf_path.exists()

    processor = PDFProcessor()
    chunks = processor.process_pdf(pdf_path, "test_manual.pdf")
    assert len(chunks) >= 4
    assert any("ISO 10816" in c["content"] for c in chunks)


def test_tfidf_search():
    index = TFIDFIndex()
    sample_chunks = [
        {"content": "ISO 10816 vibration severity standards for industrial electric motors. Zone D exceeds 7.1 mm/s.", "doc_name": "manual_1.pdf", "metadata": {"page": 2}},
        {"content": "Overheating troubleshooting: clean cooling fan shroud and inspect bearing grease ports.", "doc_name": "manual_2.pdf", "metadata": {"page": 1}},
        {"content": "Centrifugal pump cavitation symptoms include crackling acoustic noise and sudden pressure drop.", "doc_name": "manual_3.pdf", "metadata": {"page": 4}}
    ]
    count = index.build_index(sample_chunks)
    assert count == 3

    results = index.search("vibration ISO 10816 Zone D", top_k=1)
    assert len(results) == 1
    assert "Zone D" in results[0]["content"]


def test_diagnostic_assistant_offline_mode(tmp_path):
    db = DatabaseManager(db_path=tmp_path / "diag_test.db")
    # No API key = Offline deterministic TF-IDF synthesis
    ai_cfg = AIConfig(api_key=None)
    assistant = DiagnosticAssistant(db_manager=db, ai_config=ai_cfg)

    fault = FaultEvent(
        fault_id="MOTOR-PUMP-01_OVERHEATING",
        device_id="MOTOR-PUMP-01",
        fault_type="OVERHEATING",
        severity="CRITICAL",
        metric_name="temperature",
        metric_value=93.2,
        threshold_value=90.0,
        message="Temperature 93.2 exceeds critical 90.0 threshold"
    )

    report = assistant.diagnose_fault(fault)
    assert "Local TF-IDF Offline Synthesis" in report.engine_used
    assert len(report.safety_precautions) > 0
    assert len(report.maintenance_actions) > 0
    assert len(report.retrieved_sources) > 0
