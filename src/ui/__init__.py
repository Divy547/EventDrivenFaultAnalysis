"""UI components package."""
from src.ui.dashboard_view import render_dashboard_view
from src.ui.faults_view import render_faults_view
from src.ui.simulator_view import render_simulator_view
from src.ui.assistant_view import render_assistant_view
from src.ui.knowledge_view import render_knowledge_view
from src.ui.settings_view import render_settings_view

__all__ = [
    "render_dashboard_view",
    "render_faults_view",
    "render_simulator_view",
    "render_assistant_view",
    "render_knowledge_view",
    "render_settings_view",
]
