from __future__ import annotations

import os
from typing import Any

import pandas as pd
import streamlit as st

from src.ai_engine import GeminiError, analyze_report
from src.excel_exporter import build_excel_bytes
from src.record_utils import COLUMNS

st.set_page_config(page_title="IQAC Analyzer", page_icon="📘", layout="wide")


def setting(name: str, default: str = "") -> str:
    try:
        value = st.secrets.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    except Exception:
        pass
    return os.getenv(name, default)


API_KEY = setting("GEMINI_API_KEY")
MODEL = setting("GEMINI_MODEL", "gemini-3.5-flash-lite")
INSTITUTION = setting(
    "INSTITUTION_NAME",
    "Ramsheth Thakur College of Commerce & Science",
)
MAX_FILE_MB = int(setting("MAX_FILE_MB", "50"))

st.title("📘 IQAC Analyzer")
st.caption("Simple and fast AI extraction of college activity reports into a reviewable Excel master sheet.")
st.info(
    f"AI model: **{MODEL}**  •  PDF files are analyzed directly by Gemini. "
    "No photo-evidence module is used."
)

if not API_KEY:
    st.error("Gemini API is not configured. Add GEMINI_API_KEY to Streamlit Secrets.")
    st.stop()

uploads = st.file_uploader(
    "Upload IQAC activity reports",
    type=["pdf", "docx", "txt"],
    accept_multiple_files=True,
    help=f"Maximum {MAX_FILE_MB} MB per file.",
)

if uploads:
    st.caption(f"{len(uploads)} file(s) selected.")
    for f in uploads:
        st.write(f"• {f.name} — {f.size / (1024*1024):.1f} MB")

col1, col2 = st.columns([3, 1])
with col1:
    analyze = st.button("✨ Analyze Documents", type="primary", use_container_width=True)
with col2:
    clear = st.button("Clear", use_container_width=True)

if clear:
    for key in ("records", "results", "excel"):
        st.session_state.pop(key, None)
    st.rerun()

if analyze:
    if not uploads:
        st.warning("Please upload at least one PDF, DOCX or TXT file.")
        st.stop()

    records: list[dict[str, str]] = []
    results: list[dict[str, Any]] = []
    progress = st.progress(0)
    status = st.empty()

    for i, uploaded in enumerate(uploads, start=1):
        status.write(f"Analyzing {i}/{len(uploads)}: **{uploaded.name}**")
        try:
            raw = uploaded.getvalue()
            if len(raw) > MAX_FILE_MB * 1024 * 1024:
                raise ValueError(f"File exceeds {MAX_FILE_MB} MB.")

            file_records, meta = analyze_report(raw, uploaded.name, MODEL, API_KEY)
            records.extend(file_records)
            results.append({
                "File": uploaded.name,
                "Activities": len(file_records),
                "Status": "Completed",
            })
        except GeminiError as exc:
            results.append({
                "File": uploaded.name,
                "Activities": 0,
                "Status": f"AI Error: {exc}",
            })
        except Exception as exc:
            results.append({
                "File": uploaded.name,
                "Activities": 0,
                "Status": f"Error: {exc}",
            })

        progress.progress(i / len(uploads))

    for i, record in enumerate(records, start=1):
        record["Record ID"] = f"IQAC-{i:04d}"

    st.session_state.records = records
    st.session_state.results = results
    st.session_state.excel = build_excel_bytes(records) if records else None
    status.success("Analysis complete.")

if "results" in st.session_state:
    results = st.session_state.results
    records = st.session_state.records

    c1, c2, c3 = st.columns(3)
    c1.metric("Documents", len(results))
    c2.metric("Activities", len(records))
    c3.metric("Completed", sum(r["Status"] == "Completed" for r in results))

    st.subheader("Processing Status")
    st.dataframe(pd.DataFrame(results), use_container_width=True, hide_index=True)

    if records:
        st.subheader("Review Activities")
        df = pd.DataFrame(records).reindex(columns=COLUMNS).fillna("Not Identified")
        edited = st.data_editor(
            df,
            use_container_width=True,
            hide_index=True,
            num_rows="fixed",
            height=min(650, max(180, 42 * (len(df) + 1))),
            disabled=["Record ID", "Source Report", "Source Page"],
        )
        edited_records = edited.to_dict(orient="records")
        if edited_records != st.session_state.records:
            st.session_state.records = edited_records
            st.session_state.excel = build_excel_bytes(edited_records)

        st.download_button(
            "⬇️ Download IQAC Master Data.xlsx",
            data=st.session_state.excel,
            file_name="IQAC_Master_Data.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            use_container_width=True,
        )
    else:
        st.warning("No genuine activity was identified in the uploaded documents.")

st.divider()
st.caption(f"{INSTITUTION} • AI-assisted extraction. Always verify extracted data against the original document.")
