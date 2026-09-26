from __future__ import annotations

import os
from typing import Any

import pandas as pd
import streamlit as st

from src.ai_engine import GeminiError, analyze_report, check_connection
from src.excel_exporter import build_excel_bytes
from src.record_utils import COLUMNS

st.set_page_config(
    page_title="IQAC AI Extractor",
    page_icon="📘",
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


MODEL = setting("GEMINI_MODEL", "gemini-3.8-flash")
API_KEY = setting("GEMINI_API_KEY")
INSTITUTION = setting("INSTITUTION_NAME", "Ramsheth Thakur College of Commerce & Science")
MAX_FILE_MB = int(setting("MAX_FILE_MB", "50"))

for key, default in {"records": [], "summaries": [], "analysis_done": False, "excel": None}.items():
    if key not in st.session_state:
        st.session_state[key] = default

st.markdown("""
<style>
.block-container {max-width: 1480px; padding: 1.4rem 2rem 3rem;}
.hero {padding: 1.55rem 1.8rem; border-radius: 20px; background: linear-gradient(135deg,#102a43,#163b59); border:1px solid #24557b; margin-bottom:1rem; box-shadow:0 10px 30px rgba(0,0,0,.12);}
.hero h1 {margin:0; font-size:2.25rem; letter-spacing:-.035em; color:#fff;}
.hero p {margin:.45rem 0 0; color:#c9d9e8; font-size:1rem;}
.stepbar {display:flex; gap:.65rem; flex-wrap:wrap; margin:.7rem 0 1.2rem;}
.step {padding:.48rem .8rem; border-radius:999px; background:#17212b; border:1px solid #293746; color:#c8d1db; font-size:.88rem;}
.step.active {background:#123a56; border-color:#2b82b8; color:#e6f5ff;}
.info {padding:.85rem 1rem; border-radius:13px; background:#101b26; border:1px solid #223242; color:#b9c7d5; margin:.8rem 0 1rem;}
.card {padding:1rem 1.1rem; border-radius:15px; background:#101b26; border:1px solid #263746;}
.card .label {font-size:.78rem; color:#8fa2b5; text-transform:uppercase; letter-spacing:.06em;}
.card .value {font-size:1.65rem; font-weight:700; color:#f3f7fb; margin-top:.15rem;}
.section-title {font-size:1.3rem; font-weight:700; margin-top:1.3rem; margin-bottom:.15rem;}
.section-sub {color:#8f9dac; margin-bottom:.7rem;}
.small-note {color:#8f9dac; font-size:.86rem;}
div[data-testid="stDataEditor"] {border-radius:14px; overflow:hidden; border:1px solid #293746;}
div[data-testid="stFileUploader"] {border-radius:14px;}
</style>
""", unsafe_allow_html=True)

st.markdown(
    f'<div class="hero"><h1>📘 IQAC AI Extractor</h1><p>{INSTITUTION}<br>Turn activity reports into a clean, reviewable IQAC master Excel file.</p></div>',
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="stepbar"><span class="step active">1 · Upload</span><span class="step">2 · AI Extract</span><span class="step">3 · Review</span><span class="step">4 · Download Excel</span></div>',
    unsafe_allow_html=True,
)

if not API_KEY:
    st.error("Gemini API is not configured. Add GEMINI_API_KEY to Streamlit Secrets.")
    st.stop()

ready, status = check_connection(API_KEY, MODEL)
if not ready:
    st.error(status)
    st.stop()

st.markdown('<div class="info"><b>Simple workflow:</b> Upload one or more PDF/DOCX/TXT reports. The AI identifies each activity, extracts the useful fields, maps one best-fit NAAC metric, and checks which supporting documents are actually present. Missing information is shown as <b>Not Identified</b>.</div>', unsafe_allow_html=True)

uploads = st.file_uploader(
    "Upload IQAC activity report(s)",
    type=["pdf", "docx", "txt"],
    accept_multiple_files=True,
    help=f"Maximum {MAX_FILE_MB} MB per file.",
)

c1, c2 = st.columns([4, 1])
with c1:
    analyze = st.button("🔍 Extract Activities", type="primary", width="stretch")
with c2:
    clear = st.button("Clear", width="stretch")

if clear:
    for key in ["records", "summaries", "analysis_done", "excel", "simple_editor"]:
        st.session_state.pop(key, None)
    st.rerun()

if analyze:
    if not uploads:
        st.warning("Please upload at least one report.")
        st.stop()

    records: list[dict[str, str]] = []
    summaries: list[dict[str, Any]] = []
    progress = st.progress(0, text="Starting AI extraction…")

    for idx, uploaded in enumerate(uploads, start=1):
        try:
            raw = uploaded.getvalue()
            if len(raw) > MAX_FILE_MB * 1024 * 1024:
                raise ValueError(f"File exceeds the {MAX_FILE_MB} MB limit.")
            progress.progress((idx - 1) / len(uploads), text=f"Extracting {uploaded.name}…")
            file_records, meta = analyze_report(raw, uploaded.name, MODEL, API_KEY)
            records.extend(file_records)
            summaries.append({"Report": uploaded.name, "Activities": len(file_records), "Status": "Done"})
        except GeminiError as exc:
            summaries.append({"Report": uploaded.name, "Activities": 0, "Status": f"AI Error: {exc}"})
        except Exception as exc:
            summaries.append({"Report": uploaded.name, "Activities": 0, "Status": f"Error: {exc}"})

    progress.progress(1.0, text="Extraction complete.")
    for idx, record in enumerate(records, start=1):
        record["Record ID"] = f"IQAC-{idx:04d}"
    st.session_state.records = records
    st.session_state.summaries = summaries
    st.session_state.analysis_done = True
    st.session_state.excel = build_excel_bytes(records) if records else None

if st.session_state.analysis_done:
    records = st.session_state.records
    total = len(records)
    reports_done = sum(1 for x in st.session_state.summaries if x.get("Status") == "Done")

    st.markdown('<div class="section-title">Extraction Summary</div><div class="section-sub">A compact overview of the current upload.</div>', unsafe_allow_html=True)
    a, b, c = st.columns(3)
    with a:
        st.markdown(f'<div class="card"><div class="label">Reports processed</div><div class="value">{reports_done}</div></div>', unsafe_allow_html=True)
    with b:
        st.markdown(f'<div class="card"><div class="label">Activities extracted</div><div class="value">{total}</div></div>', unsafe_allow_html=True)
    with c:
        st.markdown('<div class="card"><div class="label">Output</div><div class="value">1 Excel sheet</div></div>', unsafe_allow_html=True)

    if st.session_state.summaries:
        with st.expander("Report processing details", expanded=False):
            st.dataframe(pd.DataFrame(st.session_state.summaries), width="stretch", hide_index=True)

    if records:
        st.markdown('<div class="section-title">Review Extracted Activities</div><div class="section-sub">Edit only if a value needs correction. No blank activity rows are created.</div>', unsafe_allow_html=True)
        df = pd.DataFrame(records).reindex(columns=COLUMNS).fillna("Not Identified")
        editor_height = min(520, max(115, 46 * (len(df) + 1) + 18))
        edited = st.data_editor(
            df,
            key="simple_editor",
            width="stretch",
            height=editor_height,
            hide_index=True,
            num_rows="fixed",
            disabled=["Record ID", "Source Report", "Source Page"],
            column_config={
                "Record ID": st.column_config.TextColumn("ID", width="small"),
                "Academic Year": st.column_config.TextColumn("Academic Year", width="small"),
                "Activity Date": st.column_config.TextColumn("Date", width="small"),
                "Activity Title": st.column_config.TextColumn("Activity Title", width="large"),
                "Objective": st.column_config.TextColumn("Objective", width="large"),
                "Activity Description": st.column_config.TextColumn("Description", width="large"),
                "Outcome": st.column_config.TextColumn("Outcome", width="large"),
                "Documents Present": st.column_config.TextColumn("Documents Present", width="large"),
                "Documents Absent": st.column_config.TextColumn("Documents Absent", width="large"),
                "Source Report": st.column_config.TextColumn("Source Report", width="medium"),
                "Source Page": st.column_config.TextColumn("Page", width="small"),
            },
        )
        st.session_state.records = edited.to_dict(orient="records")
        st.session_state.excel = build_excel_bytes(st.session_state.records)

        st.markdown('<div class="section-title">Documents & NAAC Mapping</div><div class="section-sub">Simple reference information extracted from the same reports.</div>', unsafe_allow_html=True)
        status_df = pd.DataFrame([
            {
                "Activity": r.get("Activity Title", "Not Identified"),
                "✅ Present": r.get("Documents Present", "None Identified"),
                "❌ Absent": r.get("Documents Absent", "None Identified"),
                "NAAC Attribute": r.get("NAAC Attribute", "Not Identified"),
                "NAAC Metric": r.get("NAAC Metric", "Not Identified"),
            }
            for r in st.session_state.records
        ])
        st.dataframe(status_df, width="stretch", hide_index=True, height=min(430, max(100, 42 * (len(status_df) + 1))))

        d1, d2 = st.columns([1, 1])
        with d1:
            st.download_button(
                "⬇️ Download IQAC_Master_Data.xlsx",
                data=st.session_state.excel,
                file_name="IQAC_Master_Data.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
                width="stretch",
            )
        with d2:
            st.caption("The Excel file contains one clean master sheet with the extracted activities, NAAC mapping, document status and source reference.")
    else:
        st.warning("No activity was identified in the uploaded reports.")

st.caption("AI-assisted extraction. Review the extracted rows against the source report before official use.")
