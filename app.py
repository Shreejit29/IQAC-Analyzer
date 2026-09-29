from __future__ import annotations

import os
from typing import Any

import pandas as pd
import streamlit as st

from src.ai_engine import GeminiError, analyze_report
from src.excel_exporter import build_excel_bytes
from src.record_utils import COLUMNS

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


MODEL = setting("GEMINI_MODEL", "gemini-3.5-flash-lite")
API_KEY = setting("GEMINI_API_KEY")
INSTITUTION = setting("INSTITUTION_NAME", "Ramsheth Thakur College of Commerce & Science")
try:
    MAX_FILE_MB = max(1, int(setting("MAX_FILE_MB", "50")))
except ValueError:
    MAX_FILE_MB = 50

DEFAULT_STATE = {
    "records": [],
    "summaries": [],
    "analysis_done": False,
    "excel": None,
}
for key, value in DEFAULT_STATE.items():
    if key not in st.session_state:
        st.session_state[key] = value


st.markdown(
    """
<style>
.block-container { max-width: 1500px; padding: 1.1rem clamp(.9rem, 3vw, 3rem) 2.5rem; }
.hero { padding: 1.35rem 1.45rem; border: 1px solid rgba(24,127,143,.25); border-radius: 22px; margin-bottom: 1rem; background: linear-gradient(135deg, rgba(24,127,143,.08), rgba(36,95,192,.05)); }
.hero-row { display:flex; justify-content:space-between; align-items:flex-start; gap:1rem; }
.kicker { color:#187f8f; font-size:.72rem; font-weight:800; letter-spacing:.11em; text-transform:uppercase; }
.title { margin:.15rem 0 0; font-size:clamp(1.8rem,4vw,2.5rem); font-weight:850; letter-spacing:-.04em; }
.subtitle { margin:.45rem 0 0; max-width:920px; opacity:.68; line-height:1.5; }
.badge { padding:.4rem .62rem; border-radius:999px; border:1px solid rgba(24,127,143,.2); background:rgba(24,127,143,.07); font-size:.74rem; font-weight:750; white-space:nowrap; }
.workflow { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:.55rem; margin:1rem 0 1.15rem; }
.step { display:flex; align-items:center; gap:.55rem; padding:.6rem .7rem; border:1px solid rgba(127,127,127,.14); border-radius:12px; opacity:.55; }
.step.active { opacity:1; border-color:rgba(24,127,143,.28); background:rgba(24,127,143,.05); }
.step-num { width:26px; height:26px; display:grid; place-items:center; border-radius:50%; border:1px solid rgba(127,127,127,.18); font-size:.75rem; font-weight:800; flex:0 0 auto; }
.step.active .step-num { color:#fff; background:#187f8f; border-color:#187f8f; }
.step-text b { font-size:.8rem; }.step-text span { display:block; margin-top:.06rem; font-size:.68rem; opacity:.55; }
.section-title { font-size:1.08rem; font-weight:820; }.section-sub { margin-top:.15rem; margin-bottom:.7rem; opacity:.62; font-size:.82rem; }
.upload-note { display:flex; gap:.7rem; align-items:center; padding:.7rem .8rem; margin-bottom:.7rem; border:1px dashed rgba(24,127,143,.3); border-radius:12px; background:rgba(24,127,143,.04); font-size:.82rem; }
.upload-icon { width:34px; height:34px; display:grid; place-items:center; border-radius:9px; background:rgba(24,127,143,.1); flex:0 0 auto; }
.chips { display:flex; flex-wrap:wrap; gap:.4rem; margin-top:.55rem; }.chip { display:inline-flex; gap:.35rem; align-items:center; padding:.35rem .5rem; border:1px solid rgba(127,127,127,.14); border-radius:9px; font-size:.73rem; background:rgba(127,127,127,.03); }.chip span { opacity:.5; }
.surface { padding:1rem; border:1px solid rgba(127,127,127,.14); border-radius:15px; background:rgba(127,127,127,.025); }
.footer { margin-top:1.5rem; padding-top:.7rem; border-top:1px solid rgba(127,127,127,.12); text-align:center; opacity:.48; font-size:.7rem; }
@media (max-width:900px){ .workflow{grid-template-columns:repeat(2,minmax(0,1fr));}.hero-row{flex-direction:column;} }
@media (max-width:560px){ .workflow{grid-template-columns:1fr;} }
</style>
""",
    unsafe_allow_html=True,
)


def reset_app() -> None:
    for key, value in DEFAULT_STATE.items():
        st.session_state[key] = value


def render_workflow(active_step: int) -> None:
    steps = [
        (1, "Upload", "Add documents"),
        (2, "Analyze", "Extract activity data"),
        (3, "Review", "Correct values"),
        (4, "Export", "Download master Excel"),
    ]
    parts = ["<div class='workflow'>"]
    for number, label, helper in steps:
        active = " active" if number <= active_step else ""
        parts.append(
            f"<div class='step{active}'><div class='step-num'>{number}</div>"
            f"<div class='step-text'><b>{label}</b><span>{helper}</span></div></div>"
        )
    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)


def render_file_chips(files: list[Any]) -> None:
    if not files:
        return
    bits = ["<div class='chips'>"]
    for item in files:
        size_mb = getattr(item, "size", 0) / (1024 * 1024)
        ext = item.name.rsplit(".", 1)[-1].upper() if "." in item.name else "FILE"
        bits.append(
            f"<div class='chip'><b>{ext}</b> {item.name}"
            f"<span>{size_mb:.1f} MB</span></div>"
        )
    bits.append("</div>")
    st.markdown("".join(bits), unsafe_allow_html=True)


st.markdown(
    f"""
<div class='hero'>
  <div class='hero-row'>
    <div>
      <div class='kicker'>Institutional Quality Assurance</div>
      <h1 class='title'>IQAC Analyzer</h1>
      <div class='subtitle'>Analyze activity documents and produce one clean, reviewable IQAC Master Data table. The analyzer extracts activity details, conservative NAAC mapping, document presence/absence, and source pages.</div>
    </div>
    <div class='badge'>Gemini 3.5 Flash-Lite</div>
  </div>
  <div style='margin-top:.65rem;opacity:.55;font-size:.75rem;'>{INSTITUTION}</div>
</div>
""",
    unsafe_allow_html=True,
)

render_workflow(3 if st.session_state.analysis_done else 1)

if not API_KEY:
    st.error("Gemini API is not configured. Add GEMINI_API_KEY to Streamlit Secrets.")
    st.stop()

st.markdown(
    """
<div class='section-title'>Upload activity documents</div>
<div class='section-sub'>Supported: PDF, DOCX and TXT. No separate photo-evidence upload is required. The AI checks the uploaded document itself for documentary evidence.</div>
""",
    unsafe_allow_html=True,
)

with st.container(border=True):
    st.markdown(
        "<div class='upload-note'><div class='upload-icon'>⬆</div><div><b>Drop IQAC documents here</b><br><span style='opacity:.58'>Use one complete activity file when possible. Missing information is kept as Not Identified instead of being invented.</span></div></div>",
        unsafe_allow_html=True,
    )
    uploads = st.file_uploader(
        "IQAC documents",
        type=["pdf", "docx", "txt"],
        accept_multiple_files=True,
        label_visibility="collapsed",
        help=f"Maximum {MAX_FILE_MB} MB per file.",
    )
    render_file_chips(uploads or [])

    left, right = st.columns([3, 1])
    with left:
        st.caption("Excel output matches the IQAC Master Data structure, including Documents Present, Documents Absent, Source Report and Source Page.")
    with right:
        if st.button("↺ Clear", width="stretch"):
            reset_app()
            st.rerun()

st.markdown("<div style='height:.35rem'></div>", unsafe_allow_html=True)

left, right = st.columns([2, 4])
with left:
    analyze = st.button("✨ Analyze documents", type="primary", width="stretch")
with right:
    st.caption("One AI analysis request per uploaded document. PDFs go directly to Gemini; DOCX/TXT are extracted locally first.")

if analyze:
    if not uploads:
        st.warning("Please upload at least one document.")
        st.stop()

    all_records: list[dict[str, str]] = []
    summaries: list[dict[str, Any]] = []
    progress = st.progress(0, text="Starting analysis…")

    total = len(uploads)
    for index, uploaded in enumerate(uploads, start=1):
        try:
            raw = uploaded.getvalue()
            if len(raw) > MAX_FILE_MB * 1024 * 1024:
                raise GeminiError(
                    f"{uploaded.name} exceeds the {MAX_FILE_MB} MB file limit."
                )

            progress.progress(
                (index - 1) / total,
                text=f"Analyzing {uploaded.name} ({index}/{total})…",
            )
            records, summary = analyze_report(
                raw=raw,
                filename=uploaded.name,
                model=MODEL,
                api_key=API_KEY,
            )
            start_index = len(all_records) + 1
            for offset, record in enumerate(records):
                record["Record ID"] = f"IQAC-{start_index + offset:04d}"
                all_records.append(record)
            summary["File"] = uploaded.name
            summaries.append(summary)
        except GeminiError as exc:
            st.error(str(exc))
        except Exception as exc:
            st.error(f"Unexpected error while analyzing {uploaded.name}: {exc}")

    progress.progress(1.0, text="Analysis complete")
    st.session_state.records = all_records
    st.session_state.summaries = summaries
    st.session_state.analysis_done = True
    st.session_state.excel = build_excel_bytes(all_records) if all_records else None

if st.session_state.analysis_done:
    records = st.session_state.records
    if records:
        tab_review, tab_export = st.tabs(["Review data", "Export"])

        with tab_review:
            st.markdown(
                "<div class='section-title'>Review extracted activities</div><div class='section-sub'>You can edit the values before exporting. Record ID, Source Report and Source Page are locked to preserve traceability.</div>",
                unsafe_allow_html=True,
            )
            df = pd.DataFrame(records).reindex(columns=COLUMNS).fillna("Not Identified")
            row_height = min(650, max(150, 42 * (len(df) + 1) + 24))
            edited = st.data_editor(
                df,
                key="activity_editor",
                width="stretch",
                height=row_height,
                hide_index=True,
                num_rows="fixed",
                disabled=["Record ID", "Source Report", "Source Page"],
                column_config={
                    "Record ID": st.column_config.TextColumn("ID", width="small"),
                    "Academic Year": st.column_config.TextColumn("Academic Year", width="small"),
                    "Activity Date": st.column_config.TextColumn("Date", width="small"),
                    "Activity Title": st.column_config.TextColumn("Activity Title", width="large"),
                    "Activity Type": st.column_config.TextColumn("Type", width="medium"),
                    "Category": st.column_config.TextColumn("Category", width="medium"),
                    "Organizing Department / Committee": st.column_config.TextColumn("Organizing Department / Committee", width="medium"),
                    "Collaborating Agency": st.column_config.TextColumn("Collaborating Agency", width="medium"),
                    "Resource Person": st.column_config.TextColumn("Resource Person", width="medium"),
                    "Venue": st.column_config.TextColumn("Venue", width="medium"),
                    "Participants": st.column_config.TextColumn("Participants", width="small"),
                    "Objective": st.column_config.TextColumn("Objective", width="large"),
                    "Activity Description": st.column_config.TextColumn("Activity Description", width="large"),
                    "Outcome": st.column_config.TextColumn("Outcome", width="large"),
                    "Follow-up Action": st.column_config.TextColumn("Follow-up Action", width="medium"),
                    "Feedback": st.column_config.TextColumn("Feedback", width="medium"),
                    "NAAC Attribute": st.column_config.TextColumn("NAAC Attribute", width="medium"),
                    "NAAC Metric": st.column_config.TextColumn("NAAC Metric", width="small"),
                    "Documents Present": st.column_config.TextColumn("Documents Present", width="large"),
                    "Documents Absent": st.column_config.TextColumn("Documents Absent", width="large"),
                    "Source Report": st.column_config.TextColumn("Source Report", width="medium"),
                    "Source Page": st.column_config.TextColumn("Page", width="small"),
                },
            )
            new_records = edited.to_dict(orient="records")
            if new_records != st.session_state.records:
                st.session_state.records = new_records
                st.session_state.excel = build_excel_bytes(new_records)

        with tab_export:
            st.markdown(
                "<div class='section-title'>Download master data</div><div class='section-sub'>One worksheet: IQAC Master Data. Filters, frozen panes and print-ready formatting are included.</div>",
                unsafe_allow_html=True,
            )
            st.markdown(
                "<div class='surface'><b>📊 IQAC_Master_Data.xlsx</b><br><span style='opacity:.62;font-size:.82rem'>Master activity dataset with document presence/absence and source traceability.</span></div>",
                unsafe_allow_html=True,
            )
            st.markdown("<div style='height:.55rem'></div>", unsafe_allow_html=True)
            if st.session_state.excel:
                st.download_button(
                    "⬇️ Download IQAC_Master_Data.xlsx",
                    data=st.session_state.excel,
                    file_name="IQAC_Master_Data.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    type="primary",
                    width="stretch",
                )
    else:
        st.warning("No activity was identified in the uploaded documents.")

st.markdown(
    f"<div class='footer'>AI-assisted extraction · {INSTITUTION} · Always verify extracted values against the original document before official use.</div>",
    unsafe_allow_html=True,
)
