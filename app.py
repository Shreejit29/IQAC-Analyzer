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
/* =========================================================
   IQAC Analyzer — Theme-safe UI
   Uses Streamlit's theme variables so light AND dark mode work.
   ========================================================= */

:root {
    --iqac-primary: #2F75B5;
    --iqac-primary-strong: #1F5A8A;
    --iqac-accent: #00A6A6;
    --iqac-success: #16835B;
    --iqac-warning: #B7791F;
    --iqac-danger: #C53D3D;
    --iqac-radius: 14px;
}

/* Main application */
[data-testid="stAppViewContainer"] {
    background: var(--background-color);
}

[data-testid="stHeader"] {
    background: transparent;
}

[data-testid="stToolbar"] {
    background: transparent;
}

.block-container {
    max-width: 1500px;
    padding-top: 1.25rem;
    padding-bottom: 3rem;
}

/* ---------- Hero ---------- */
.iqac-hero {
    position: relative;
    overflow: hidden;
    border: 1px solid var(--secondary-background-color);
    border-radius: 20px;
    padding: 1.45rem 1.65rem 1.35rem;
    margin-bottom: 1rem;
    background:
        linear-gradient(135deg,
            color-mix(in srgb, var(--iqac-primary) 13%, var(--background-color)),
            color-mix(in srgb, var(--iqac-accent) 8%, var(--background-color)));
    box-shadow: 0 8px 28px rgba(0,0,0,.08);
}

.iqac-hero::after {
    content: "";
    position: absolute;
    width: 180px;
    height: 180px;
    right: -55px;
    top: -80px;
    border-radius: 50%;
    background: color-mix(in srgb, var(--iqac-primary) 12%, transparent);
}

.iqac-kicker {
    font-size: .78rem;
    font-weight: 800;
    letter-spacing: .12em;
    text-transform: uppercase;
    color: var(--iqac-primary);
    margin-bottom: .25rem;
}

.iqac-title {
    font-size: clamp(2rem, 4vw, 3rem);
    line-height: 1.05;
    font-weight: 850;
    letter-spacing: -.045em;
    color: var(--text-color);
    margin: 0;
}

.iqac-sub {
    font-size: 1rem;
    line-height: 1.55;
    color: var(--text-color);
    opacity: .72;
    margin-top: .55rem;
    max-width: 900px;
}

.iqac-pills {
    display: flex;
    flex-wrap: wrap;
    gap: .45rem;
    margin-top: .9rem;
}

.iqac-pill {
    display: inline-flex;
    align-items: center;
    padding: .35rem .65rem;
    border-radius: 999px;
    background: var(--secondary-background-color);
    border: 1px solid color-mix(in srgb, var(--text-color) 12%, transparent);
    color: var(--text-color);
    font-size: .78rem;
    font-weight: 650;
}

/* ---------- Section headers ---------- */
.iqac-section {
    display: flex;
    align-items: center;
    gap: .6rem;
    margin: 1.25rem 0 .65rem;
}

.iqac-section-bar {
    width: 5px;
    height: 28px;
    border-radius: 99px;
    background: linear-gradient(180deg, var(--iqac-primary), var(--iqac-accent));
}

.iqac-section-title {
    font-size: 1.28rem;
    font-weight: 780;
    color: var(--text-color);
}

.iqac-section-sub {
    font-size: .86rem;
    color: var(--text-color);
    opacity: .62;
}

/* ---------- Upload zone ---------- */
[data-testid="stFileUploaderDropzone"] {
    border: 1.5px dashed color-mix(in srgb, var(--iqac-primary) 48%, var(--text-color) 10%) !important;
    border-radius: 16px !important;
    background: color-mix(in srgb, var(--iqac-primary) 5%, var(--secondary-background-color)) !important;
    transition: border-color .2s ease, transform .2s ease;
}

[data-testid="stFileUploaderDropzone"]:hover {
    border-color: var(--iqac-primary) !important;
    transform: translateY(-1px);
}

/* ---------- Metric cards ---------- */
[data-testid="stMetric"] {
    background: var(--secondary-background-color);
    border: 1px solid color-mix(in srgb, var(--text-color) 10%, transparent);
    border-radius: 14px;
    padding: .85rem 1rem;
    box-shadow: 0 4px 14px rgba(0,0,0,.045);
}

[data-testid="stMetricLabel"] {
    color: var(--text-color) !important;
    opacity: .65;
    font-weight: 650;
}

[data-testid="stMetricValue"] {
    color: var(--text-color) !important;
    font-weight: 800;
}

/* ---------- Cards / information blocks ---------- */
.iqac-card {
    background: var(--secondary-background-color);
    color: var(--text-color);
    border: 1px solid color-mix(in srgb, var(--text-color) 10%, transparent);
    border-radius: var(--iqac-radius);
    padding: 1rem 1.1rem;
    box-shadow: 0 5px 18px rgba(0,0,0,.045);
}

.iqac-card-title {
    font-weight: 760;
    font-size: .98rem;
    margin-bottom: .25rem;
}

.iqac-card-text {
    font-size: .86rem;
    line-height: 1.55;
    opacity: .72;
}

/* ---------- Buttons ---------- */
.stButton > button,
.stDownloadButton > button {
    border-radius: 10px !important;
    min-height: 2.65rem;
    font-weight: 700 !important;
    transition: transform .15s ease, box-shadow .15s ease;
}

.stButton > button:hover,
.stDownloadButton > button:hover {
    transform: translateY(-1px);
    box-shadow: 0 5px 16px rgba(0,0,0,.12);
}

/* ---------- Tabs ---------- */
.stTabs [data-baseweb="tab-list"] {
    gap: .35rem;
    border-bottom: 1px solid color-mix(in srgb, var(--text-color) 10%, transparent);
}

.stTabs [data-baseweb="tab"] {
    color: var(--text-color);
    opacity: .68;
    font-weight: 650;
    border-radius: 8px 8px 0 0;
    padding-left: .85rem;
    padding-right: .85rem;
}

.stTabs [aria-selected="true"] {
    color: var(--iqac-primary) !important;
    opacity: 1 !important;
}

/* ---------- Expanders ---------- */
[data-testid="stExpander"] {
    border: 1px solid color-mix(in srgb, var(--text-color) 10%, transparent) !important;
    border-radius: 14px !important;
    background: var(--secondary-background-color) !important;
}

/* ---------- Dataframes / editors ---------- */
[data-testid="stDataFrame"],
[data-testid="stDataEditor"] {
    border: 1px solid color-mix(in srgb, var(--text-color) 10%, transparent);
    border-radius: 12px;
    overflow: hidden;
}

/* ---------- Alerts ---------- */
[data-testid="stAlert"] {
    border-radius: 12px;
}

/* ---------- Caption / helper text ---------- */
.iqac-muted {
    color: var(--text-color);
    opacity: .62;
    font-size: .84rem;
}

.iqac-footer {
    margin-top: 2rem;
    padding: 1rem 0 .25rem;
    border-top: 1px solid color-mix(in srgb, var(--text-color) 10%, transparent);
    color: var(--text-color);
    opacity: .58;
    font-size: .78rem;
    line-height: 1.5;
}

/* ---------- Explicit dark-mode safety ----------
   Some Streamlit versions don't expose all theme variables
   consistently to nested widgets, so force readable text on
   common dark-theme selectors too.
   ---------- */
html[data-theme="dark"] .iqac-title,
html[data-theme="dark"] .iqac-sub,
html[data-theme="dark"] .iqac-section-title,
html[data-theme="dark"] .iqac-section-sub,
html[data-theme="dark"] .iqac-card,
html[data-theme="dark"] .iqac-card-text,
html[data-theme="dark"] .iqac-muted,
html[data-theme="dark"] label,
html[data-theme="dark"] [data-testid="stWidgetLabel"] {
    color: var(--text-color) !important;
}

[data-theme="dark"] .iqac-title,
[data-theme="dark"] .iqac-sub,
[data-theme="dark"] .iqac-section-title,
[data-theme="dark"] .iqac-section-sub,
[data-theme="dark"] .iqac-card,
[data-theme="dark"] .iqac-card-text,
[data-theme="dark"] .iqac-muted {
    color: var(--text-color) !important;
}

/* Fallback for browser-level dark preference */
@media (prefers-color-scheme: dark) {
    .iqac-hero,
    .iqac-card {
        box-shadow: 0 7px 22px rgba(0,0,0,.22);
    }
}

/* Mobile */
@media (max-width: 768px) {
    .block-container {
        padding-top: .75rem;
        padding-left: .8rem;
        padding-right: .8rem;
    }

    .iqac-hero {
        padding: 1.1rem;
        border-radius: 16px;
    }

    .iqac-title {
        font-size: 2rem;
    }
}
</style>
""", unsafe_allow_html=True)

st.markdown(f"""
<div class="iqac-hero">
    <div class="iqac-kicker">Institutional Quality Assurance</div>
    <div class="iqac-title">📊 IQAC Analyzer</div>
    <div class="iqac-sub">
        AI-powered extraction, evidence review, validation and master-data preparation
        for IQAC activity reports.
    </div>
    <div class="iqac-pills">
        <span class="iqac-pill">🏛️ {INSTITUTION}</span>
        <span class="iqac-pill">✨ Gemini-powered</span>
        <span class="iqac-pill">🔎 Human verification</span>
        <span class="iqac-pill">📥 Excel-ready</span>
    </div>
</div>
""", unsafe_allow_html=True)

st.markdown("""
<div class="iqac-section">
    <div class="iqac-section-bar"></div>
    <div>
        <div class="iqac-section-title">Getting Started</div>
        <div class="iqac-section-sub">Upload reports, analyze activities, review the extracted data, and export.</div>
    </div>
</div>
""", unsafe_allow_html=True)

with st.expander("How this analyzer works", expanded=False):
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

st.markdown("""
<div class="iqac-card" style="margin-bottom:.65rem;">
    <div class="iqac-card-title">📁 Upload IQAC Reports</div>
    <div class="iqac-card-text">
        Upload one or multiple PDF, DOCX or TXT reports. The system extracts distinct
        activities, evidence, outcomes and reference NAAC mappings for review.
    </div>
</div>
""", unsafe_allow_html=True)

uploads = st.file_uploader(
    "Choose report files",
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
    st.markdown("""
    <div class="iqac-section">
        <div class="iqac-section-bar"></div>
        <div>
            <div class="iqac-section-title">Analysis Dashboard</div>
            <div class="iqac-section-sub">A quick view of extraction and verification status.</div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Reports", len(st.session_state.summaries))
    m2.metric("Activities Detected", summary["activities"])
    m3.metric("Needs Verification", summary["needs_verification"])
    m4.metric("Activities with Evidence Gaps", summary["evidence_gaps"])
    m5.metric("Possible Duplicates", summary["possible_duplicates"])

    if st.session_state.summaries:
        st.dataframe(pd.DataFrame(st.session_state.summaries), width='stretch', hide_index=True)

    if st.session_state.records:
        st.markdown("""
        <div class="iqac-section">
            <div class="iqac-section-bar"></div>
            <div>
                <div class="iqac-section-title">Review Extracted Activities</div>
                <div class="iqac-section-sub">Correct AI-extracted values before exporting the master workbook.</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
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

        st.markdown("""
        <div class="iqac-section">
            <div class="iqac-section-bar"></div>
            <div>
                <div class="iqac-section-title">🔎 Source Traceability</div>
                <div class="iqac-section-sub">Inspect where extracted fields came from and how confidently they were extracted.</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        trace_records = st.session_state.records
        if trace_records:
            trace_labels = []
            for i, rec in enumerate(trace_records):
                title = str(rec.get("Activity Title", "")).strip() or "Untitled Activity"
                rid = str(rec.get("Record ID", "")).strip()
                trace_labels.append(f"{rid} — {title}" if rid else title)

            selected_trace = st.selectbox(
                "Select an activity to inspect",
                options=list(range(len(trace_records))),
                format_func=lambda i: trace_labels[i],
                key="traceability_selector",
            )
            selected = trace_records[selected_trace]

            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**📄 Source**")
                st.info(
                    f"**Report:** {selected.get('Source Report', 'Not Identified')}\n\n"
                    f"**Source page(s):** {selected.get('Source Page', 'Not Identified')}\n\n"
                    f"**Activity summary page(s):** {selected.get('Activity Summary Pages', 'Not Identified')}"
                )
            with c2:
                st.markdown("**🎯 Extraction quality**")
                st.info(
                    f"**Overall confidence:** {selected.get('Extraction Confidence', 'Not Identified')}\n\n"
                    f"**Verification:** {selected.get('Verification Status', 'Needs Verification')}\n\n"
                    f"**Missing information:** {selected.get('Missing Information', 'None identified')}"
                )

            fs = str(selected.get("Field Sources", "")).strip()
            fc = str(selected.get("Field Confidence", "")).strip()

            if fs and fs.lower() != "not identified":
                source_rows = []
                for part in fs.split(" | "):
                    if ":" in part:
                        field, page = part.split(":", 1)
                        source_rows.append({"Field": field.strip(), "Source Page(s)": page.strip()})
                    else:
                        source_rows.append({"Field": part.strip(), "Source Page(s)": "Not Identified"})
                st.dataframe(pd.DataFrame(source_rows), width="stretch", hide_index=True)
            else:
                st.warning("Field-level source pages were not identified for this activity.")

            if fc and fc.lower() != "not identified":
                confidence_rows = []
                for part in fc.split(" | "):
                    if ":" in part:
                        field, score = part.split(":", 1)
                        confidence_rows.append({"Field": field.strip(), "Confidence": score.strip()})
                    else:
                        confidence_rows.append({"Field": part.strip(), "Confidence": "Not Identified"})
                st.dataframe(pd.DataFrame(confidence_rows), width="stretch", hide_index=True)
            else:
                st.warning("Field-level confidence was not identified for this activity.")

        # Evidence Intelligence
        st.markdown("""
        <div class="iqac-section">
            <div class="iqac-section-bar"></div>
            <div>
                <div class="iqac-section-title">🧾 Evidence Intelligence</div>
                <div class="iqac-section-sub">Evidence categories identified directly from the uploaded report.</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        selected_evidence = selected if trace_records else {}
        details = selected_evidence.get("Evidence Trace Details") or []
        if isinstance(details, str):
            try:
                import json
                details = json.loads(details)
            except Exception:
                details = []

        if details:
            present = [x for x in details if str(x.get("Status", "")).strip().lower() == "present"]
            identified = len(details)
            readiness = round((len(present) / identified) * 100) if identified else 0

            ec1, ec2, ec3 = st.columns(3)
            ec1.metric("Evidence Present", len(present))
            ec2.metric("Evidence Categories", identified)
            ec3.metric("Evidence Readiness", f"{readiness}%")

            evidence_rows = []
            for item in details:
                status = str(item.get("Status", "Not Identified"))
                icon = "✅" if status == "Present" else ("➖" if status == "Not Applicable" else "⚠️")
                evidence_rows.append({
                    "": icon,
                    "Evidence": item.get("Evidence Type", ""),
                    "Status": status,
                    "Source Page": item.get("Source Page", "Not Identified"),
                    "Notes": item.get("Notes", ""),
                })
            st.dataframe(pd.DataFrame(evidence_rows), width="stretch", hide_index=True)

            missing_evidence = [
                str(x.get("Evidence Type", ""))
                for x in details
                if str(x.get("Status", "")).strip().lower() == "not identified"
            ]
            if missing_evidence:
                st.warning(
                    "Evidence not identified: " + ", ".join(missing_evidence)
                )
        else:
            st.info(
                "No structured evidence trace is available for this record. "
                "The general evidence fields below are still shown."
            )

        st.markdown("""
        <div class="iqac-section">
            <div class="iqac-section-bar"></div>
            <div>
                <div class="iqac-section-title">Evidence Review</div>
                <div class="iqac-section-sub">Check the supporting evidence reported by the source documents.</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
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

st.markdown("""
<div class="iqac-footer">
    <strong>Privacy / processing:</strong> Uploaded reports are processed for the current
    Streamlit session. The app does not maintain its own database or permanent document archive.
    For Gemini processing, the report is transmitted to Google's Gemini API; uploaded Gemini Files
    are deleted by the app after analysis on a best-effort basis and otherwise expire automatically
    according to Google's Files API retention. Do not upload documents you are not authorized to
    send to a third-party AI service.
    <br><br>
    The analyzer prepares data for IQAC use; it does not calculate or certify an official NAAC accreditation score.
</div>
""", unsafe_allow_html=True)

st.stop() if False else None

# End of application** uploaded reports are processed for the current Streamlit session. The app does not maintain its own database or permanent document archive. For Gemini processing, the report is transmitted to Google's Gemini API; uploaded Gemini Files are deleted by the app after analysis on a best-effort basis and otherwise expire automatically according to Google's Files API retention. Do not upload documents you are not authorized to send to a third-party AI service.")
