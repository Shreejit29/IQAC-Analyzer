from __future__ import annotations

import os
from typing import Any

import pandas as pd
import streamlit as st

from src.ai_engine import GeminiError, analyze_report, check_connection
from src.document_parser import basic_metadata, validate_upload
from src.excel_exporter import build_excel_bytes
from src.record_utils import (
    COLUMNS,
    EVIDENCE_FIELDS,
    NAAC_ATTRIBUTES,
    deduplicate_records,
    session_summary,
)

st.set_page_config(
    page_title="IQAC Analyzer",
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


# ---------------------------------------------------------------------------
# Premium, lightweight UI
# ---------------------------------------------------------------------------
st.markdown(
    """
<style>
:root {
    --iqac-navy: #17324d;
    --iqac-blue: #2563eb;
    --iqac-sky: #eff6ff;
    --iqac-green: #15803d;
    --iqac-amber: #b45309;
    --iqac-red: #b91c1c;
    --iqac-border: #e5e7eb;
    --iqac-muted: #667085;
}

.block-container {
    max-width: 1480px;
    padding-top: 1.25rem;
    padding-bottom: 3rem;
}

header[data-testid="stHeader"] {
    background: transparent;
}

.iqac-hero {
    border: 1px solid #dbe5f0;
    border-radius: 22px;
    padding: 1.65rem 1.8rem;
    margin-bottom: 1.2rem;
    background:
        radial-gradient(circle at 90% 15%, rgba(37,99,235,.10), transparent 28%),
        linear-gradient(135deg, #ffffff 0%, #f7faff 55%, #eef5ff 100%);
    box-shadow: 0 8px 28px rgba(23,50,77,.07);
}

.iqac-brand {
    color: var(--iqac-blue);
    font-size: .82rem;
    font-weight: 800;
    letter-spacing: .12em;
    text-transform: uppercase;
    margin-bottom: .3rem;
}

.iqac-title {
    color: var(--iqac-navy);
    font-size: clamp(2rem, 4vw, 3rem);
    line-height: 1.08;
    font-weight: 850;
    letter-spacing: -.035em;
    margin: 0;
}

.iqac-subtitle {
    color: #526071;
    font-size: 1.02rem;
    margin-top: .65rem;
    max-width: 900px;
    line-height: 1.6;
}

.iqac-pill-row {
    display: flex;
    flex-wrap: wrap;
    gap: .55rem;
    margin-top: 1rem;
}

.iqac-pill {
    display: inline-flex;
    align-items: center;
    gap: .35rem;
    border: 1px solid #d9e4f2;
    background: rgba(255,255,255,.85);
    border-radius: 999px;
    padding: .38rem .72rem;
    color: #334155;
    font-size: .82rem;
    font-weight: 650;
}

.section-title {
    color: var(--iqac-navy);
    font-size: 1.35rem;
    font-weight: 800;
    margin: 1.2rem 0 .55rem;
}

.section-caption {
    color: var(--iqac-muted);
    margin-bottom: .75rem;
}

.metric-card {
    border: 1px solid var(--iqac-border);
    border-radius: 16px;
    padding: 1rem 1.05rem;
    background: #fff;
    box-shadow: 0 4px 16px rgba(15,23,42,.045);
    min-height: 108px;
}

.metric-label {
    color: #667085;
    font-size: .78rem;
    font-weight: 750;
    text-transform: uppercase;
    letter-spacing: .055em;
}

.metric-value {
    color: var(--iqac-navy);
    font-size: 1.8rem;
    font-weight: 850;
    line-height: 1.1;
    margin-top: .35rem;
}

.metric-help {
    color: #98a2b3;
    font-size: .78rem;
    margin-top: .3rem;
}

.status-card {
    border-radius: 16px;
    padding: .9rem 1rem;
    border: 1px solid #dbe5f0;
    background: #f8fbff;
}

.status-dot {
    display: inline-block;
    width: 9px;
    height: 9px;
    border-radius: 50%;
    margin-right: .45rem;
    background: #16a34a;
}

.upload-card {
    border: 1px dashed #a9bdd5;
    border-radius: 18px;
    padding: .8rem;
    background: #fbfdff;
}

.footer-note {
    color: #98a2b3;
    font-size: .78rem;
    line-height: 1.55;
}

div[data-testid="stFileUploader"] {
    border-radius: 14px;
}

div[data-testid="stDataEditor"] {
    border: 1px solid #e5e7eb;
    border-radius: 14px;
    overflow: hidden;
}

div[data-testid="stDataFrame"] {
    border-radius: 14px;
}

.stButton > button, .stDownloadButton > button {
    border-radius: 10px;
    font-weight: 700;
}

button[kind="primary"] {
    box-shadow: 0 5px 14px rgba(37,99,235,.20);
}

div[data-testid="stExpander"] {
    border-radius: 14px;
}

.iqac-empty {
    text-align: center;
    padding: 2.4rem 1rem;
    border: 1px dashed #d0d5dd;
    border-radius: 16px;
    background: #fafafa;
    color: #667085;
}

.small-muted {
    color: #667085;
    font-size: .86rem;
}
</style>
""",
    unsafe_allow_html=True,
)


def metric_card(label: str, value: str | int, help_text: str = "") -> None:
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-label">{label}</div>
            <div class="metric-value">{value}</div>
            <div class="metric-help">{help_text}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def status_label(status: str) -> str:
    value = str(status)
    if value == "Analyzed":
        return "✅ Analyzed"
    if value.startswith("AI Error"):
        return "⚠️ AI Error"
    if value.startswith("Error"):
        return "❌ Error"
    return value


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.markdown(
    f"""
    <div class="iqac-hero">
        <div class="iqac-brand">IQAC • QUALITY DATA WORKSPACE</div>
        <h1 class="iqac-title">IQAC Analyzer</h1>
        <div class="iqac-subtitle">
            Convert activity reports into structured, traceable IQAC master data
            with AI-assisted extraction, evidence review and NAAC reference mapping.
        </div>
        <div class="iqac-pill-row">
            <span class="iqac-pill">🤖 Gemini AI</span>
            <span class="iqac-pill">📄 PDF / DOCX / TXT</span>
            <span class="iqac-pill">🔎 Evidence-aware</span>
            <span class="iqac-pill">🧑‍💼 Human verification</span>
            <span class="iqac-pill">📊 Excel export</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    f"""
    <div class="small-muted">
        <b>{INSTITUTION}</b> &nbsp;•&nbsp; Current session processing
        &nbsp;•&nbsp; Official NAAC scoring is not calculated by this application.
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Connection + instructions
# ---------------------------------------------------------------------------
status_ok, status_msg = (
    check_connection(API_KEY, MODEL)
    if API_KEY
    else (False, "Gemini API key is not configured.")
)

st.markdown('<div class="section-title">🚀 Start a new analysis</div>', unsafe_allow_html=True)

connection_col, info_col = st.columns([1, 2])
with connection_col:
    if status_ok:
        st.markdown(
            '<div class="status-card"><span class="status-dot"></span>'
            '<b>AI engine ready</b><br><span class="small-muted">'
            'Gemini is connected and ready for analysis.</span></div>',
            unsafe_allow_html=True,
        )
    else:
        st.error(
            "Gemini AI is not ready. The administrator must configure "
            "`GEMINI_API_KEY` in Streamlit Secrets."
        )

with info_col:
    with st.expander("ℹ️ How it works", expanded=False):
        st.markdown(
            """
            **1. Upload reports** → **2. AI reads the complete document** →
            **3. Distinct activities are identified** → **4. Structured fields,
            evidence and NAAC reference mapping are extracted** →
            **5. You review/edit the results** → **6. Download the IQAC workbook.**

            Missing information is reported as missing; the application should
            not invent facts that are absent from the source.
            """
        )

st.markdown('<div class="upload-card">', unsafe_allow_html=True)
uploads = st.file_uploader(
    "📁 Upload IQAC report(s)",
    type=["pdf", "docx", "txt"],
    accept_multiple_files=True,
    help=f"Upload complete activity reports. Maximum {MAX_FILE_MB} MB per file.",
)
st.markdown("</div>", unsafe_allow_html=True)

if uploads:
    total_mb = sum(len(x.getvalue()) for x in uploads) / (1024 * 1024)
    st.caption(
        f"📎 {len(uploads)} file(s) selected  •  "
        f"{total_mb:.1f} MB total  •  Maximum {MAX_FILE_MB} MB per file"
    )

action_col, clear_col = st.columns([3, 1])
with action_col:
    analyze = st.button(
        "🔍 Analyze Reports",
        type="primary",
        width="stretch",
        disabled=not status_ok,
    )
with clear_col:
    clear = st.button("🧹 Clear Session", width="stretch")

if clear:
    for key in ["records", "summaries", "analysis_done", "excel", "editor_df"]:
        st.session_state.pop(key, None)
    st.rerun()

# ---------------------------------------------------------------------------
# Processing
# ---------------------------------------------------------------------------
if analyze:
    if not uploads:
        st.warning("Please upload at least one report.")
        st.stop()

    records: list[dict[str, str]] = []
    summaries: list[dict[str, Any]] = []
    progress = st.progress(0, text="Preparing reports…")

    for idx, uploaded in enumerate(uploads, 1):
        raw = uploaded.getvalue()
        # Keep metadata available for future diagnostics without displaying
        # implementation details to staff.
        _ = basic_metadata(uploaded.name, raw)

        try:
            validate_upload(uploaded.name, raw, MAX_FILE_MB)
            progress.progress(
                (idx - 1) / len(uploads),
                text=f"Analyzing {uploaded.name}…",
            )

            file_records, report_meta = analyze_report(
                raw,
                uploaded.name,
                MODEL,
                API_KEY,
            )
            records.extend(file_records)

            summaries.append(
                {
                    "Source Report": uploaded.name,
                    "Type": report_meta.get("Document Type", "Not Identified"),
                    "Academic Year": report_meta.get(
                        "Academic Year", "Not Identified"
                    ),
                    "Activities Detected": len(file_records),
                    "Status": "Analyzed",
                }
            )

        except GeminiError as exc:
            summaries.append(
                {
                    "Source Report": uploaded.name,
                    "Type": "—",
                    "Academic Year": "—",
                    "Activities Detected": 0,
                    "Status": f"AI Error: {exc}",
                }
            )
        except Exception as exc:
            summaries.append(
                {
                    "Source Report": uploaded.name,
                    "Type": "—",
                    "Academic Year": "—",
                    "Activities Detected": 0,
                    "Status": f"Error: {exc}",
                }
            )

        progress.progress(
            idx / len(uploads),
            text=f"Finished {idx} of {len(uploads)} report(s)",
        )

    records, duplicate_count = deduplicate_records(records)

    st.session_state.records = records
    st.session_state.summaries = summaries
    st.session_state.analysis_done = True
    st.session_state.excel = (
        build_excel_bytes(records) if records else None
    )

    if duplicate_count:
        st.info(
            f"{duplicate_count} repeated extraction record(s) were suppressed "
            "within the same source report. Please still review the final rows."
        )

    st.success(
        f"Analysis complete — {len(records)} activity record(s) extracted "
        f"from {len(uploads)} report(s)."
    )

# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------
if st.session_state.analysis_done:
    records = st.session_state.records
    summary = session_summary(records)

    st.markdown('<div class="section-title">📊 Analysis overview</div>', unsafe_allow_html=True)

    cols = st.columns(5)
    with cols[0]:
        metric_card("Reports", len(st.session_state.summaries), "Files processed")
    with cols[1]:
        metric_card("Activities", summary["activities"], "Activity records extracted")
    with cols[2]:
        metric_card("Verification", summary["needs_verification"], "Records still requiring review")
    with cols[3]:
        metric_card("Evidence gaps", summary["evidence_gaps"], "Records with evidence gaps")
    with cols[4]:
        metric_card("Duplicates", summary["possible_duplicates"], "Possible duplicate records")

    tab_overview, tab_review, tab_evidence, tab_export = st.tabs(
        ["📋 Reports", "📝 Review Activities", "🧾 Evidence", "📥 Export"]
    )

    with tab_overview:
        st.markdown("### Processing status")
        if st.session_state.summaries:
            display_summary = pd.DataFrame(st.session_state.summaries).copy()
            if "Status" in display_summary:
                display_summary["Status"] = display_summary["Status"].map(
                    status_label
                )
            st.dataframe(
                display_summary,
                width="stretch",
                hide_index=True,
                column_config={
                    "Source Report": st.column_config.TextColumn(
                        "Report", width="large"
                    ),
                    "Activities Detected": st.column_config.NumberColumn(
                        "Activities", format="%d"
                    ),
                },
            )

        if not records:
            st.markdown(
                """
                <div class="iqac-empty">
                    <div style="font-size:2rem;">📄</div>
                    <b>No activity records were extracted.</b><br>
                    <span>Check the report type, AI configuration and processing status above.</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

    if records:
        with tab_review:
            st.markdown("### Review extracted activities")
            st.caption(
                "Review AI-extracted information before using the workbook as an official IQAC record."
            )

            df = (
                pd.DataFrame(records)
                .reindex(columns=COLUMNS)
                .fillna("")
            )

            edited = st.data_editor(
                df,
                key="editor_df",
                width="stretch",
                height=640,
                hide_index=True,
                num_rows="fixed",
                disabled=[
                    "Record ID",
                    "Source Report",
                    "Extraction Status",
                ],
                column_config={
                    "Activity Title": st.column_config.TextColumn(
                        "Activity Title", width="large"
                    ),
                    "Activity Type": st.column_config.TextColumn(
                        "Activity Type", width="medium"
                    ),
                    "Organizing Department": st.column_config.TextColumn(
                        "Department", width="medium"
                    ),
                    "NAAC Attribute": st.column_config.SelectboxColumn(
                        "NAAC Attribute",
                        options=NAAC_ATTRIBUTES,
                        width="large",
                    ),
                    "Verification Status": st.column_config.SelectboxColumn(
                        "Verification Status",
                        options=[
                            "Needs Verification",
                            "Verified",
                            "Possible Duplicate",
                        ],
                        width="medium",
                    ),
                    "Extraction Confidence": st.column_config.TextColumn(
                        "Confidence", width="medium"
                    ),
                },
            )

            st.session_state.records = edited.to_dict(orient="records")
            st.session_state.excel = build_excel_bytes(
                st.session_state.records
            )

            st.success(
                "Review changes are applied to the current session and will be included in the downloaded workbook."
            )

        with tab_evidence:
            st.markdown("### Evidence register")
            st.caption(
                "Evidence availability is informational. A missing item is not automatically a failed activity."
            )

            evidence_columns = (
                ["Record ID", "Activity Title", "Source Report"]
                + EVIDENCE_FIELDS
                + ["Evidence Gaps"]
            )
            evidence_df = (
                pd.DataFrame(st.session_state.records)
                .reindex(columns=evidence_columns)
                .fillna("")
            )

            st.dataframe(
                evidence_df,
                width="stretch",
                hide_index=True,
            )

        with tab_export:
            st.markdown("### Download your IQAC workbook")
            st.caption(
                "The workbook contains the structured records generated by the current session."
            )

            export_col, note_col = st.columns([2, 3])
            with export_col:
                st.download_button(
                    "⬇️ Download IQAC_Master_Data.xlsx",
                    data=st.session_state.excel,
                    file_name="IQAC_Master_Data.xlsx",
                    mime=(
                        "application/vnd.openxmlformats-officedocument."
                        "spreadsheetml.sheet"
                    ),
                    type="primary",
                    width="stretch",
                )
            with note_col:
                st.markdown(
                    """
                    <div class="status-card">
                        <b>Before official use</b><br>
                        <span class="small-muted">
                        Review extracted records, evidence gaps and NAAC reference
                        mappings. AI output should be verified by the responsible IQAC team.
                        </span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.divider()
st.markdown(
    f"""
    <div class="footer-note">
        <b>{INSTITUTION}</b> • IQAC Analyzer<br>
        Uploaded reports are processed for the current Streamlit session.
        The application does not maintain its own permanent document archive.
        For Gemini processing, the report is transmitted to Google's Gemini API;
        uploaded Gemini Files are deleted by the app on a best-effort basis and
        otherwise expire according to Google's Files API retention.
        Do not upload documents you are not authorized to send to a third-party AI service.
        <br><br>
        <b>Important:</b> This application prepares IQAC data and provides reference
        mappings. It does not calculate or certify an official NAAC accreditation score.
    </div>
    """,
    unsafe_allow_html=True,
)
