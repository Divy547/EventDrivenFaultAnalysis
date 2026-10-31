"""UI components package for P_311."""

from src.ui.diagnosis_view import render_diagnosis_view
from src.ui.fault_view import render_fault_view
from src.ui.knowledge_view import render_knowledge_view
from src.ui.monitoring_view import render_monitoring_view
from src.ui.overview_view import render_overview_view
from src.ui.theme import apply_industrial_theme

__all__ = [
    "render_overview_view",
    "render_monitoring_view",
    "render_fault_view",
    "render_diagnosis_view",
    "render_knowledge_view",
    "apply_industrial_theme",
]
