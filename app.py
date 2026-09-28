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
INSTITUTION = setting(
    "INSTITUTION_NAME",
    "Ramsheth Thakur College of Commerce & Science",
)
MAX_FILE_MB = int(setting("MAX_FILE_MB", "50"))

for key, default in {
    "records": [],
    "summaries": [],
    "analysis_done": False,
    "excel": None,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default


# Theme-aware styling: avoid hard-coded dark-only cards so Streamlit's
# Light/Dark theme remains readable.
st.markdown(
    """
<style>
:root {
    --iqac-primary: #2f75b5;
    --iqac-primary-dark: #1f5f95;
    --iqac-border: rgba(128, 128, 128, .22);
    --iqac-soft: rgba(128, 128, 128, .07);
    --iqac-soft-strong: rgba(128, 128, 128, .12);
    --iqac-text-muted: rgba(128, 128, 128, .95);
    --iqac-success-bg: rgba(34, 139, 78, .12);
    --iqac-danger-bg: rgba(210, 70, 70, .11);
}

.block-container {
    max-width: 1500px;
    padding: 1.15rem 2rem 3rem;
}

.hero {
    padding: 1.45rem 1.65rem;
    border-radius: 20px;
    margin-bottom: 1rem;
    background:
        radial-gradient(circle at 92% 15%, rgba(79, 172, 254, .24), transparent 28%),
        linear-gradient(135deg, #123b5d 0%, #1d638d 100%);
    border: 1px solid rgba(80, 170, 220, .38);
    box-shadow: 0 12px 34px rgba(0, 0, 0, .10);
}
.hero h1 {
    margin: 0;
    color: #fff;
    font-size: clamp(1.75rem, 3vw, 2.35rem);
    letter-spacing: -.035em;
}
.hero p {
    margin: .45rem 0 0;
    color: #e7f4fb;
    font-size: 1rem;
    line-height: 1.55;
}

.workflow {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: .65rem;
    margin: .75rem 0 1.15rem;
}
.workflow-item {
    padding: .65rem .8rem;
    border: 1px solid var(--iqac-border);
    border-radius: 12px;
    background: var(--iqac-soft);
    text-align: center;
    font-size: .86rem;
}
.workflow-item.active {
    border-color: rgba(47,117,181,.55);
    background: rgba(47,117,181,.10);
    font-weight: 700;
}

.section-head {
    display: flex;
    align-items: end;
    justify-content: space-between;
    gap: 1rem;
    margin: 1.25rem 0 .65rem;
}
.section-title {
    font-size: 1.25rem;
    font-weight: 750;
    letter-spacing: -.015em;
}
.section-sub {
    color: var(--iqac-text-muted);
    font-size: .9rem;
    margin-top: .12rem;
}

.info-card {
    padding: .95rem 1.05rem;
    border-radius: 14px;
    border: 1px solid var(--iqac-border);
    background: var(--iqac-soft);
    line-height: 1.55;
}

.metric-card {
    padding: 1rem 1.05rem;
    border: 1px solid var(--iqac-border);
    border-radius: 16px;
    background: var(--iqac-soft);
    min-height: 92px;
}
.metric-label {
    color: var(--iqac-text-muted);
    font-size: .76rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: .055em;
}
.metric-value {
    margin-top: .22rem;
    font-size: 1.65rem;
    font-weight: 800;
}

.upload-note {
    color: var(--iqac-text-muted);
    font-size: .84rem;
    margin-top: .35rem;
}

.status-card {
    border: 1px solid var(--iqac-border);
    border-radius: 15px;
    padding: .95rem 1rem;
    background: var(--iqac-soft);
    min-height: 100%;
}
.status-card h4 {
    margin: 0 0 .5rem;
    font-size: 1rem;
}
.status-card p {
    margin: 0;
    line-height: 1.55;
    font-size: .9rem;
}

.download-card {
    padding: 1.05rem;
    border-radius: 16px;
    border: 1px solid rgba(47,117,181,.35);
    background: rgba(47,117,181,.08);
}

div[data-testid="stFileUploader"] {
    border: 1px solid var(--iqac-border);
    border-radius: 15px;
    padding: .2rem;
}

div[data-testid="stDataEditor"] {
    border: 1px solid var(--iqac-border);
    border-radius: 14px;
    overflow: hidden;
}

div[data-testid="stDataFrame"] {
    border: 1px solid var(--iqac-border);
    border-radius: 14px;
    overflow: hidden;
}

@media (max-width: 800px) {
    .block-container { padding: .8rem 1rem 2rem; }
    .workflow { grid-template-columns: repeat(2, 1fr); }
}
</style>
""",
    unsafe_allow_html=True,
)

st.markdown(
    f"""
<div class="hero">
    <h1>📘 IQAC AI Extractor</h1>
    <p><b>{INSTITUTION}</b><br>
    Convert IQAC activity reports into a clean, editable master record and Excel file.</p>
</div>
""",
    unsafe_allow_html=True,
)

current_step = 1 if not st.session_state.analysis_done else 3
workflow = [
    (1, "Upload"),
    (2, "AI Extract"),
    (3, "Review"),
    (4, "Download"),
]
workflow_html = "".join(
    f'<div class="workflow-item {"active" if n <= current_step else ""}">'
    f'<b>{n}</b>&nbsp; {label}</div>'
    for n, label in workflow
)
st.markdown(f'<div class="workflow">{workflow_html}</div>', unsafe_allow_html=True)

if not API_KEY:
    st.error("Gemini API is not configured. Add GEMINI_API_KEY to Streamlit Secrets.")
    st.stop()

ready, status = check_connection(API_KEY, MODEL)
if not ready:
    st.error(status)
    st.stop()

st.markdown(
    """
<div class="info-card">
<b>How it works:</b> Upload one or more activity reports. The AI reads the complete
report, identifies genuine activities, extracts the useful information, maps a best-fit
NAAC Attribute/Metric, checks the supporting documents, and prepares one clean master sheet.
You can correct any extracted value before downloading.
</div>
""",
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="section-head"><div><div class="section-title">📂 Upload Reports</div>'
    '<div class="section-sub">PDF, DOCX or TXT • one or multiple files</div></div></div>',
    unsafe_allow_html=True,
)

uploads = st.file_uploader(
    "Choose IQAC report files",
    type=["pdf", "docx", "txt"],
    accept_multiple_files=True,
    help=f"Maximum {MAX_FILE_MB} MB per file.",
    label_visibility="collapsed",
)

if uploads:
    file_cols = st.columns(min(3, len(uploads)))
    for i, uploaded in enumerate(uploads):
        with file_cols[i % len(file_cols)]:
            size_mb = len(uploaded.getvalue()) / (1024 * 1024)
            st.caption(f"📄 **{uploaded.name}**  •  {size_mb:.1f} MB")

a, b = st.columns([4, 1], vertical_alignment="center")
with a:
    analyze = st.button(
        "🔍  Extract Activities",
        type="primary",
        width="stretch",
        disabled=not bool(uploads),
    )
with b:
    clear = st.button("↺  Clear", width="stretch")

if clear:
    for key in ["records", "summaries", "analysis_done", "excel", "simple_editor"]:
        st.session_state.pop(key, None)
    st.rerun()

if analyze:
    records: list[dict[str, str]] = []
    summaries: list[dict[str, Any]] = []
    progress = st.progress(0, text="Preparing extraction…")

    for idx, uploaded in enumerate(uploads, start=1):
        try:
            raw = uploaded.getvalue()
            if len(raw) > MAX_FILE_MB * 1024 * 1024:
                raise ValueError(f"File exceeds the {MAX_FILE_MB} MB limit.")
            progress.progress(
                (idx - 1) / len(uploads),
                text=f"Reading {uploaded.name}…",
            )
            file_records, meta = analyze_report(
                raw, uploaded.name, MODEL, API_KEY
            )
            records.extend(file_records)
            summaries.append(
                {
                    "Report": uploaded.name,
                    "Activities": len(file_records),
                    "Status": "Completed",
                }
            )
        except GeminiError as exc:
            summaries.append(
                {
                    "Report": uploaded.name,
                    "Activities": 0,
                    "Status": f"AI Error: {exc}",
                }
            )
        except Exception as exc:
            summaries.append(
                {
                    "Report": uploaded.name,
                    "Activities": 0,
                    "Status": f"Error: {exc}",
                }
            )

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
    reports_done = sum(
        1 for x in st.session_state.summaries
        if x.get("Status") == "Completed"
    )
    reports_total = len(st.session_state.summaries)

    st.markdown(
        '<div class="section-head"><div><div class="section-title">📊 Extraction Summary</div>'
        '<div class="section-sub">Review the AI output before creating the master file.</div></div></div>',
        unsafe_allow_html=True,
    )

    m1, m2, m3 = st.columns(3)
    metrics = [
        ("Reports processed", f"{reports_done}/{reports_total}"),
        ("Activities extracted", str(total)),
        ("Output", "1 master sheet"),
    ]
    for col, (label, value) in zip((m1, m2, m3), metrics):
        with col:
            st.markdown(
                f'<div class="metric-card"><div class="metric-label">{label}</div>'
                f'<div class="metric-value">{value}</div></div>',
                unsafe_allow_html=True,
            )

    if st.session_state.summaries:
        with st.expander("📋 Report processing details", expanded=False):
            st.dataframe(
                pd.DataFrame(st.session_state.summaries),
                width="stretch",
                hide_index=True,
            )

    if records:
        review_tab, docs_tab, download_tab = st.tabs(
            ["✏️ Review Activities", "📑 Documents & NAAC", "⬇️ Download"]
        )

        with review_tab:
            st.markdown(
                '<div class="section-head"><div><div class="section-title">Review Activities</div>'
                '<div class="section-sub">Correct any AI-extracted value before export. '
                'Rows are fixed to the activities actually detected.</div></div></div>',
                unsafe_allow_html=True,
            )

            df = pd.DataFrame(records).reindex(columns=COLUMNS).fillna("Not Identified")
            editor_height = min(560, max(145, 48 * (len(df) + 1) + 20))

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
                    "Activity Type": st.column_config.TextColumn("Activity Type", width="medium"),
                    "Category": st.column_config.TextColumn("Category", width="medium"),
                    "Organizing Department / Committee": st.column_config.TextColumn("Organizing Department / Committee", width="large"),
                    "Collaborating Agency": st.column_config.TextColumn("Collaborating Agency", width="large"),
                    "Resource Person": st.column_config.TextColumn("Resource Person", width="large"),
                    "Venue": st.column_config.TextColumn("Venue", width="medium"),
                    "Participants": st.column_config.TextColumn("Participants", width="large"),
                    "Objective": st.column_config.TextColumn("Objective", width="large"),
                    "Activity Description": st.column_config.TextColumn("Description", width="large"),
                    "Outcome": st.column_config.TextColumn("Outcome", width="large"),
                    "Follow-up Action": st.column_config.TextColumn("Follow-up Action", width="large"),
                    "Feedback": st.column_config.TextColumn("Feedback", width="large"),
                    "NAAC Attribute": st.column_config.TextColumn("NAAC Attribute", width="medium"),
                    "NAAC Metric": st.column_config.TextColumn("NAAC Metric", width="medium"),
                    "Documents Present": st.column_config.TextColumn("Documents Present", width="large"),
                    "Documents Absent": st.column_config.TextColumn("Documents Absent", width="large"),
                    "Source Report": st.column_config.TextColumn("Source Report", width="medium"),
                    "Source Page": st.column_config.TextColumn("Page", width="small"),
                },
            )

            st.session_state.records = edited.to_dict(orient="records")
            st.session_state.excel = build_excel_bytes(st.session_state.records)

        with docs_tab:
            st.markdown(
                '<div class="section-head"><div><div class="section-title">📑 Documents & NAAC Mapping</div>'
                '<div class="section-sub">Simple reference information from the same extracted activity records.</div></div></div>',
                unsafe_allow_html=True,
            )

            status_df = pd.DataFrame(
                [
                    {
                        "Activity": r.get("Activity Title", "Not Identified"),
                        "✅ Present": r.get("Documents Present", "None Identified"),
                        "❌ Absent": r.get("Documents Absent", "None Identified"),
                        "NAAC Attribute": r.get("NAAC Attribute", "Not Identified"),
                        "NAAC Metric": r.get("NAAC Metric", "Not Identified"),
                    }
                    for r in st.session_state.records
                ]
            )
            st.dataframe(
                status_df,
                width="stretch",
                hide_index=True,
                height=min(460, max(110, 44 * (len(status_df) + 1))),
                column_config={
                    "Activity": st.column_config.TextColumn("Activity", width="large"),
                    "✅ Present": st.column_config.TextColumn("Present", width="large"),
                    "❌ Absent": st.column_config.TextColumn("Absent", width="large"),
                    "NAAC Attribute": st.column_config.TextColumn("NAAC Attribute", width="medium"),
                    "NAAC Metric": st.column_config.TextColumn("NAAC Metric", width="small"),
                },
            )

        with download_tab:
            st.markdown(
                '<div class="section-head"><div><div class="section-title">⬇️ Download Master Excel</div>'
                '<div class="section-sub">One professional, filterable IQAC master sheet with only actual activity rows.</div></div></div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<div class="download-card"><b>{total} activity record(s)</b><br>'
                'The workbook includes the extracted activity fields, NAAC mapping, '
                'document status and source reference.</div>',
                unsafe_allow_html=True,
            )
            st.write("")
            st.download_button(
                "⬇️  Download IQAC_Master_Data.xlsx",
                data=st.session_state.excel,
                file_name="IQAC_Master_Data.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
                width="stretch",
            )
    else:
        st.warning(
            "No activity was identified in the uploaded reports. "
            "Try another report or check the AI error details above."
        )

st.markdown(
    '<div class="small-note">AI-assisted extraction. Please review the extracted rows '
    'against the source report before official IQAC use.</div>',
    unsafe_allow_html=True,
)
