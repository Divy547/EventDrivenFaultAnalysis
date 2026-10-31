"""Unit tests for PyMuPDF extraction, TF-IDF indexing, document metadata, deletion, and AI diagnosis."""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from config import AIConfig
from src.database.db_manager import DatabaseManager
from src.knowledge.ai_assistant import DiagnosticAssistant
from src.knowledge.pdf_processor import PDFProcessor
from src.knowledge.tfidf_index import TFIDFIndex
from src.models.diagnosis import ChatMessage, StructuredFaultDiagnosis
from src.models.telemetry import FaultEvent, MotorTelemetry


def test_pdf_processor_metadata_and_sha256(tmp_path):
    pdf_path = tmp_path / "test_manual.pdf"
    PDFProcessor.generate_sample_manual(pdf_path)
    assert pdf_path.exists()

    processor = PDFProcessor()
    meta, chunks = processor.process_pdf_with_metadata(pdf_path, "test_manual.pdf")

    assert meta["doc_name"] == "test_manual.pdf"
    assert meta["page_count"] == 4
    assert meta["file_size_bytes"] > 0
    assert len(meta["sha256_hash"]) == 64  # valid sha256 hex
    assert len(chunks) >= 4

    # Verify chunk structure
    first_chunk = chunks[0]
    assert "chunk_id" in first_chunk
    assert "page" in first_chunk
    assert "content" in first_chunk
    assert first_chunk["page"] >= 1


def test_tfidf_indexing_and_source_references():
    index = TFIDFIndex()
    sample_chunks = [
        {
            "chunk_id": 0,
            "doc_name": "manual_1.pdf",
            "page": 2,
            "content": "ISO 10816 vibration severity standards for industrial electric motors. Zone D exceeds 7.1 mm/s.",
            "metadata": {"page": 2, "chunk_id": 0}
        },
        {
            "chunk_id": 1,
            "doc_name": "manual_2.pdf",
            "page": 1,
            "content": "Overheating troubleshooting: clean cooling fan cowl and inspect bearing grease ports.",
            "metadata": {"page": 1, "chunk_id": 1}
        },
        {
            "chunk_id": 2,
            "doc_name": "manual_3.pdf",
            "page": 4,
            "content": "Centrifugal pump cavitation symptoms include crackling acoustic noise and sudden pressure drop.",
            "metadata": {"page": 4, "chunk_id": 2}
        }
    ]
    count = index.build_index(sample_chunks)
    assert count == 3

    sources = index.search_source_references("ISO 10816 Zone D vibration limit", top_k=1)
    assert len(sources) == 1
    ref = sources[0]
    assert ref.doc_name == "manual_1.pdf"
    assert ref.page_number == 2
    assert "Zone D" in ref.excerpt
    assert ref.similarity_score > 0.05


def test_document_lifecycle_upload_and_deletion(tmp_path):
    db = DatabaseManager(db_path=tmp_path / "lifecycle_test.db")
    ai_cfg = AIConfig(api_key=None)
    assistant = DiagnosticAssistant(db_manager=db, ai_config=ai_cfg)

    # Ingest a custom dummy PDF
    pdf_path = tmp_path / "custom_manual.pdf"
    PDFProcessor.generate_sample_manual(pdf_path)

    meta, count = assistant.ingest_pdf_file(pdf_path, "custom_manual.pdf")
    assert count >= 4

    # Check persistence in SQLite
    docs = db.list_indexed_documents()
    doc_names = [d["doc_name"] for d in docs]
    assert "custom_manual.pdf" in doc_names

    # Check metadata
    meta_recs = db.get_document_metadata("custom_manual.pdf")
    assert len(meta_recs) == 1
    assert meta_recs[0]["page_count"] == 4
    assert meta_recs[0]["chunk_count"] == count

    # Delete document
    deleted = assistant.delete_document("custom_manual.pdf")
    assert deleted is True

    # Verify removed from SQLite
    docs_after = db.list_indexed_documents()
    doc_names_after = [d["doc_name"] for d in docs_after]
    assert "custom_manual.pdf" not in doc_names_after
    assert len(db.get_chunks_for_document("custom_manual.pdf")) == 0


def test_structured_fault_diagnosis_validation(tmp_path):
    db = DatabaseManager(db_path=tmp_path / "diag_test.db")
    # No API key = Must trigger deterministic demo fallback
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
    telemetry = MotorTelemetry(
        device_id="MOTOR-PUMP-01",
        temperature=93.2,
        vibration=2.1,
        current=27.5,
        voltage=228.0,
        rpm=1445.0,
        acoustic_db=72.0
    )

    diag: StructuredFaultDiagnosis = assistant.diagnose_fault(fault, telemetry=telemetry)

    # Validate schema compliance
    assert isinstance(diag, StructuredFaultDiagnosis)
    assert diag.device_id == "MOTOR-PUMP-01"
    assert diag.severity == "CRITICAL"
    assert len(diag.observations) >= 2
    assert len(diag.possible_causes) >= 2
    assert len(diag.recommended_actions) >= 2
    assert len(diag.evidence) >= 1
    assert len(diag.sources) >= 1

    # Check source reference integrity
    for src in diag.sources:
        assert src.doc_name.endswith(".pdf")
        assert src.page_number >= 1
        assert len(src.excerpt) > 10

    # Strict compliance: never claim an unverified diagnosis is confirmed
    assert diag.is_verified is False
    assert "Preliminary" in diag.verification_status

    # Must explicitly state deterministic fallback without pretending to be Gemini
    assert diag.engine_used == "Deterministic Demo Fallback (Offline Mode)"
    assert diag.fallback_reason is not None
    assert "GEMINI_API_KEY" in diag.fallback_reason


def test_conversational_troubleshooting_assistant(tmp_path):
    db = DatabaseManager(db_path=tmp_path / "chat_test.db")
    ai_cfg = AIConfig(api_key=None)
    assistant = DiagnosticAssistant(db_manager=db, ai_config=ai_cfg)

    user_query = "What is the ISO 10816 Zone D critical vibration threshold and how do I fix it?"
    reply: ChatMessage = assistant.chat_troubleshoot(user_message=user_query)

    assert isinstance(reply, ChatMessage)
    assert reply.role == "assistant"
    assert "ISO 10816" in reply.content
    assert len(reply.sources) >= 1
    assert reply.engine_used == "Deterministic Demo Fallback (Offline Mode)"
    assert "GEMINI_API_KEY" in reply.fallback_reason


def test_gemini_error_handling_fallback(tmp_path):
    db = DatabaseManager(db_path=tmp_path / "gemini_error_test.db")
    # Provide an API key so it attempts Gemini, but mock Client to raise quota error
    ai_cfg = AIConfig(api_key="mock_invalid_key")
    assistant = DiagnosticAssistant(db_manager=db, ai_config=ai_cfg)

    fault = FaultEvent(
        fault_id="MOTOR-CONV-02_BEARING",
        device_id="MOTOR-CONV-02",
        fault_type="BEARING_WEAR",
        severity="CRITICAL",
        metric_name="vibration",
        metric_value=7.8,
        threshold_value=7.1,
        message="Vibration 7.8 exceeds ISO Zone D limit"
    )

    with patch("google.genai.Client") as mock_client_cls:
        mock_instance = MagicMock()
        mock_instance.models.generate_content.side_effect = Exception("HTTP 429: Resource Exhausted. Quota exceeded.")
        mock_client_cls.return_value = mock_instance

        diag = assistant.diagnose_fault(fault)

        # Fallback must be engaged cleanly
        assert isinstance(diag, StructuredFaultDiagnosis)
        assert diag.engine_used == "Deterministic Demo Fallback (Offline Mode)"
        assert "Quota exhausted" in diag.fallback_reason
        assert diag.is_verified is False
