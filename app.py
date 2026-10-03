from __future__ import annotations

import os
import runpy
from pathlib import Path

import streamlit as st

st.set_page_config(
    page_title="IQAC Analyzer",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="collapsed",
)


def setting(name: str, default: str = "") -> str:
    try:
        value = st.secrets.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    except Exception:
        pass
    return os.getenv(name, default)


MODEL = setting("GEMINI_MODEL", "gemini-3.5-flash-lite")
API_KEY = setting("GEMINI_API_KEY")
try:
    MAX_FILE_MB = max(1, int(setting("MAX_FILE_MB", "50")))
except ValueError:
    MAX_FILE_MB = 50

st.markdown(
    """
    <style>
    .facility-bar { padding: .25rem 0 .8rem; }
    .facility-title { font-size: .75rem; font-weight: 800; text-transform: uppercase; letter-spacing: .08em; color: #176b87; margin-bottom: .25rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown("<div class='facility-bar'><div class='facility-title'>IQAC Analyzer · Select Facility</div></div>", unsafe_allow_html=True)
mode = st.radio(
    "Facility",
    ["📋 Activity Report Analyzer", "📄 General Document Extractor"],
    horizontal=True,
    label_visibility="collapsed",
)

if mode.startswith("📋"):
    # The existing activity application is kept in a separate module so its
    # extraction schema and UI remain unchanged. Only this router is shared.
    runpy.run_path(str(Path(__file__).with_name("activity_app.py")), run_name="__main__")
else:
    from general_extractor.ui import render

    st.markdown(
        """
        <div style='padding:.7rem 0 .4rem;color:#667085;font-size:.78rem'>
        General extraction is independent from the Activity Report Analyzer. It creates document-specific fields and separate Excel output.
        </div>
        """,
        unsafe_allow_html=True,
    )
    uploads = st.file_uploader(
        "Upload documents",
        type=["pdf", "docx", "txt"],
        accept_multiple_files=True,
        help=f"Maximum {MAX_FILE_MB} MB per file.",
    )
    render(uploads or [], MODEL, API_KEY, MAX_FILE_MB)
