"""Industrial Dark Theme styling and Plotly chart configuration for P_311."""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

INDUSTRIAL_CSS = """
<style>
    /* Dark Industrial Theme Overrides */
    .stApp {
        background-color: #0b0e14;
        color: #e6edf3;
    }
    
    /* Top metric cards */
    [data-testid="stMetric"] {
        background-color: #151b23;
        border: 1px solid #30363d;
        border-radius: 8px;
        padding: 12px 16px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.3);
    }
    [data-testid="stMetricLabel"] {
        color: #8b949e !important;
        font-size: 0.82rem !important;
        font-weight: 600 !important;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    [data-testid="stMetricValue"] {
        color: #f0f6fc !important;
        font-weight: 700 !important;
    }

    /* Streamlit Containers / Cards */
    [data-testid="stVerticalBlockBorderWrapper"] {
        background-color: #12171f;
        border: 1px solid #21262d;
        border-radius: 8px;
    }

    /* Status Badges */
    .badge-critical {
        background-color: #ff383822;
        color: #ff4d4f;
        border: 1px solid #ff4d4f66;
        padding: 2px 8px;
        border-radius: 4px;
        font-weight: 700;
        font-size: 0.78rem;
    }
    .badge-warning {
        background-color: #faad1422;
        color: #e6a100;
        border: 1px solid #e6a10066;
        padding: 2px 8px;
        border-radius: 4px;
        font-weight: 700;
        font-size: 0.78rem;
    }
    .badge-operational {
        background-color: #52c41a22;
        color: #389e0d;
        border: 1px solid #389e0d66;
        padding: 2px 8px;
        border-radius: 4px;
        font-weight: 700;
        font-size: 0.78rem;
    }

    /* Buttons */
    .stButton > button {
        border-radius: 6px;
        font-weight: 600;
        transition: all 0.2s ease-in-out;
    }
    
    /* Code and Pre */
    pre, code {
        background-color: #161b22 !important;
        border: 1px solid #30363d !important;
        border-radius: 6px !important;
    }
</style>
"""


def apply_industrial_theme() -> None:
    """Inject global CSS overrides for consistent industrial aesthetics."""
    st.markdown(INDUSTRIAL_CSS, unsafe_allow_html=True)


def format_plotly_chart(
    fig: go.Figure,
    y_title: str,
    x_title: str = "Time (UTC)",
    height: int = 340
) -> go.Figure:
    """Apply consistent dark industrial styling to Plotly figures."""
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#12171f",
        plot_bgcolor="#0d1117",
        height=height,
        margin=dict(l=20, r=20, t=35, b=25),
        font=dict(family="Inter, Roboto, sans-serif", color="#8b949e", size=11),
        xaxis=dict(
            title=x_title,
            showgrid=True,
            gridcolor="#21262d",
            zeroline=False,
            color="#8b949e"
        ),
        yaxis=dict(
            title=y_title,
            showgrid=True,
            gridcolor="#21262d",
            zeroline=False,
            color="#8b949e"
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            bgcolor="rgba(0,0,0,0)",
            font=dict(size=10)
        )
    )
    return fig
