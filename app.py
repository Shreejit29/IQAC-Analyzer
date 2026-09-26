from __future__ import annotations

import os
from typing import Any

import pandas as pd
import streamlit as st

from src.ai_engine import GeminiError, analyze_report, check_connection
from src.document_parser import basic_metadata, validate_upload
from src.excel_exporter import build_excel_bytes
from src.record_utils import COLUMNS, EVIDENCE_FIELDS, NAAC_ATTRIBUTES, deduplicate_records, session_summary

st.set_page_config(page_title="IQAC Analyzer", page_icon="📊", layout="wide", initial_sidebar_state="collapsed")


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


for key, default in {
    "records": [], "summaries": [], "analysis_done": False, "excel": None,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default


st.markdown("""
<style>
.block-container {max-width: 1500px; padding-top: 2rem;}
.iqac-title {font-size: 2.35rem; font-weight: 800; letter-spacing: -0.02em;}
.iqac-sub {font-size: 1.02rem; color: #667085; margin-bottom: 1rem;}
.info-card {padding: 1rem 1.1rem; border: 1px solid #e5e7eb; border-radius: 12px; background: #f8fafc;}
.small {font-size: .86rem; color: #667085;}
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="iqac-title">📊 IQAC Analyzer</div>', unsafe_allow_html=True)
st.markdown('<div class="iqac-sub">AI-powered IQAC activity extraction, evidence checking and Excel master-data preparation</div>', unsafe_allow_html=True)

st.caption(f"{INSTITUTION}  •  Gemini-powered  •  Human verification required before official use")

with st.expander("How this analyzer works", expanded=True):
    st.markdown("""
    **1. Upload one or more IQAC reports → 2. Gemini reads the complete document, including scanned pages, tables, photographs and handwriting → 3. It identifies every distinct activity → 4. It connects the activity summary with whatever supporting evidence is actually present → 5. You review/edit the extracted rows → 6. Download `IQAC_Master_Data.xlsx`.**

    **Important:** supporting documents are variable. A missing Programme Table, Invitation, News clipping, etc. does **not** automatically make an activity invalid. The application reports evidence gaps separately.
    """)

status_ok, status_msg = check_connection(API_KEY, MODEL) if API_KEY else (False, "Gemini API key is not configured.")

left, right = st.columns([4, 1])
with left:
    if status_ok:
        st.success("Gemini AI is ready. Staff do not need to select a model or provider.")
    else:
        st.error("AI analysis is not ready. The administrator must configure `GEMINI_API_KEY` in Streamlit Secrets.")
with right:
    st.metric("AI Engine", "Gemini")

uploads = st.file_uploader(
    "Upload IQAC Report(s)",
    type=["pdf", "docx", "txt"],
    accept_multiple_files=True,
    help=f"Upload complete activity reports. Maximum {MAX_FILE_MB} MB per file.",
)

c1, c2 = st.columns([3, 1])
with c1:
    analyze = st.button("🔍 Analyze Reports", type="primary", width='stretch', disabled=not status_ok)
with c2:
    clear = st.button("🧹 Clear Session", width='stretch')

if clear:
    for key in ["records", "summaries", "analysis_done", "excel", "editor_df"]:
        st.session_state.pop(key, None)
    st.rerun()

if analyze:
    if not uploads:
        st.warning("Please upload at least one report.")
        st.stop()

    records: list[dict[str, str]] = []
    summaries: list[dict[str, Any]] = []
    progress = st.progress(0, text="Preparing reports…")

    for idx, uploaded in enumerate(uploads, 1):
        raw = uploaded.getvalue()
        meta = basic_metadata(uploaded.name, raw)
        try:
            validate_upload(uploaded.name, raw, MAX_FILE_MB)
            progress.progress((idx - 1) / len(uploads), text=f"Analyzing {uploaded.name}…")
            file_records, report_meta = analyze_report(raw, uploaded.name, MODEL, API_KEY)
            records.extend(file_records)
            summaries.append({
                "Source Report": uploaded.name,
                "Type": report_meta.get("Document Type", "Not Identified"),
                "Academic Year": report_meta.get("Academic Year", "Not Identified"),
                "Activities Detected": len(file_records),
                "Status": "Analyzed",
            })
        except GeminiError as exc:
            summaries.append({"Source Report": uploaded.name, "Type": "—", "Academic Year": "—", "Activities Detected": 0, "Status": f"AI Error: {exc}"})
        except Exception as exc:
            summaries.append({"Source Report": uploaded.name, "Type": "—", "Academic Year": "—", "Activities Detected": 0, "Status": f"Error: {exc}"})
        progress.progress(idx / len(uploads), text=f"Finished {idx} of {len(uploads)} report(s)")

    records, duplicate_count = deduplicate_records(records)
    st.session_state.records = records
    st.session_state.summaries = summaries
    st.session_state.analysis_done = True
    st.session_state.excel = build_excel_bytes(records) if records else None
    if duplicate_count:
        st.info(f"{duplicate_count} repeated extraction record(s) were suppressed within the same source report. Please still review the final rows.")

if st.session_state.analysis_done:
    summary = session_summary(st.session_state.records)
    st.subheader("Analysis Summary")
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Reports", len(st.session_state.summaries))
    m2.metric("Activities Detected", summary["activities"])
    m3.metric("Needs Verification", summary["needs_verification"])
    m4.metric("Activities with Evidence Gaps", summary["evidence_gaps"])
    m5.metric("Possible Duplicates", summary["possible_duplicates"])

    if st.session_state.summaries:
        st.dataframe(pd.DataFrame(st.session_state.summaries), width='stretch', hide_index=True)

    if st.session_state.records:
        st.subheader("Review Extracted Activities")
        st.caption("Edit any value that needs correction. Evidence status is a checklist, not a pass/fail judgment.")
        df = pd.DataFrame(st.session_state.records).reindex(columns=COLUMNS).fillna("")
        edited = st.data_editor(
            df,
            key="editor_df",
            width='stretch',
            height=620,
            hide_index=True,
            num_rows="fixed",
            disabled=["Record ID", "Source Report", "Extraction Status"],
            column_config={
                "NAAC Attribute": st.column_config.SelectboxColumn("NAAC Attribute", options=NAAC_ATTRIBUTES, width="large"),
                "Verification Status": st.column_config.SelectboxColumn("Verification Status", options=["Needs Verification", "Verified", "Possible Duplicate"], width="medium"),
            },
        )
        st.session_state.records = edited.to_dict(orient="records")
        st.session_state.excel = build_excel_bytes(st.session_state.records)

        st.subheader("Evidence Review")
        evidence_df = pd.DataFrame(st.session_state.records)[["Record ID", "Activity Title", "Source Report"] + EVIDENCE_FIELDS + ["Evidence Gaps"]]
        st.dataframe(evidence_df, width='stretch', hide_index=True)

        st.download_button(
            "⬇️ Download IQAC_Master_Data.xlsx",
            data=st.session_state.excel,
            file_name="IQAC_Master_Data.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            width='stretch',
        )
    else:
        st.warning("No activities were extracted. Check the report type and Gemini configuration, then try again.")

st.divider()
st.markdown("**Privacy / processing:** uploaded reports are processed for the current Streamlit session. The app does not maintain its own database or permanent document archive. For Gemini processing, the report is transmitted to Google's Gemini API; uploaded Gemini Files are deleted by the app after analysis on a best-effort basis and otherwise expire automatically according to Google's Files API retention. Do not upload documents you are not authorized to send to a third-party AI service.")
st.markdown('<div class="small">The analyzer prepares data for IQAC use; it does not calculate or certify an official NAAC accreditation score.</div>', unsafe_allow_html=True)
