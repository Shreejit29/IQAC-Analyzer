from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import pandas as pd
import streamlit as st

from src.ai_engine import AIEngineError, analyze_report
from src.excel_exporter import build_excel_bytes
from src.record_utils import COLUMNS

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


MODEL = setting("EXPERIENTIAL_MODEL", "deepseek-v4-flash-0731")
API_KEY = setting("EXPLABS_API_KEY")
BASE_URL = setting("EXPERIENTIAL_BASE_URL", "https://api.experientiallabs.ai/v1")
INSTITUTION = setting(
    "INSTITUTION_NAME", "Ramsheth Thakur College of Commerce & Science"
)
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


# -----------------------------------------------------------------------------
# UI ONLY: styling and presentation. Backend logic remains unchanged.
# -----------------------------------------------------------------------------
st.markdown(
    """
<style>
:root {
    --iqac-primary: #176b87;
    --iqac-primary-soft: #e8f4f7;
    --iqac-accent: #7c4dff;
    --iqac-text: #14212b;
    --iqac-muted: #6b7780;
    --iqac-border: rgba(20, 33, 43, 0.10);
    --iqac-surface: rgba(255,255,255,.72);
}

.block-container {
    max-width: 1480px;
    padding: 1rem clamp(.85rem, 2.5vw, 2.6rem) 2.25rem;
}

/* Hide Streamlit chrome that adds visual noise. */
#MainMenu, footer { visibility: hidden; }

.hero {
    position: relative;
    overflow: hidden;
    padding: 1.45rem 1.5rem 1.35rem;
    border: 1px solid rgba(23, 107, 135, 0.16);
    border-radius: 24px;
    background:
        radial-gradient(circle at 93% 8%, rgba(124,77,255,.12), transparent 28%),
        radial-gradient(circle at 8% 95%, rgba(23,107,135,.10), transparent 30%),
        linear-gradient(145deg, rgba(23,107,135,.075), rgba(255,255,255,.55));
    box-shadow: 0 12px 32px rgba(20,33,43,.06);
}

.hero::after {
    content: "";
    position: absolute;
    width: 180px;
    height: 180px;
    right: -65px;
    top: -72px;
    border-radius: 50%;
    border: 1px solid rgba(124,77,255,.16);
}

.hero-row {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 1rem;
}

.brand-row {
    display: flex;
    align-items: center;
    gap: .8rem;
}

.brand-mark {
    width: 48px;
    height: 48px;
    display: grid;
    place-items: center;
    border-radius: 14px;
    background: linear-gradient(145deg, var(--iqac-primary), #2b8ea5);
    color: #fff;
    font-size: 1.35rem;
    box-shadow: 0 8px 18px rgba(23,107,135,.24);
}

.kicker {
    color: var(--iqac-primary);
    font-size: .69rem;
    font-weight: 850;
    letter-spacing: .12em;
    text-transform: uppercase;
}

.title {
    margin: .1rem 0 0;
    font-size: clamp(1.8rem, 4vw, 2.65rem);
    line-height: 1.05;
    font-weight: 900;
    letter-spacing: -.045em;
    color: var(--iqac-text);
}

.subtitle {
    margin: .55rem 0 0;
    max-width: 880px;
    color: var(--iqac-muted);
    line-height: 1.55;
    font-size: .91rem;
}

.model-badge {
    display: inline-flex;
    align-items: center;
    gap: .42rem;
    padding: .48rem .72rem;
    border-radius: 999px;
    border: 1px solid rgba(23,107,135,.16);
    background: rgba(255,255,255,.74);
    color: #28586a;
    font-size: .72rem;
    font-weight: 800;
    white-space: nowrap;
}

.model-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: #28a745;
    box-shadow: 0 0 0 4px rgba(40,167,69,.11);
}

.institution-line {
    margin-top: .8rem;
    color: rgba(20,33,43,.60);
    font-size: .76rem;
    font-weight: 650;
}

.workflow {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: .65rem;
    margin: 1rem 0 1.2rem;
}

.step {
    position: relative;
    display: flex;
    align-items: center;
    gap: .62rem;
    padding: .72rem .76rem;
    border: 1px solid var(--iqac-border);
    border-radius: 14px;
    background: rgba(255,255,255,.55);
}

.step.active {
    border-color: rgba(23,107,135,.18);
    background: linear-gradient(135deg, rgba(23,107,135,.08), rgba(255,255,255,.6));
    box-shadow: 0 6px 16px rgba(20,33,43,.035);
}

.step.done .step-num {
    background: var(--iqac-primary);
    color: white;
    border-color: var(--iqac-primary);
}

.step-num {
    width: 29px;
    height: 29px;
    display: grid;
    place-items: center;
    flex: 0 0 auto;
    border-radius: 50%;
    border: 1px solid rgba(20,33,43,.12);
    color: #65727b;
    font-size: .73rem;
    font-weight: 850;
    background: rgba(255,255,255,.72);
}

.step-text b { font-size: .79rem; color: var(--iqac-text); }
.step-text span { display: block; margin-top: .08rem; font-size: .68rem; color: #7a858d; }

.section-head {
    display: flex;
    justify-content: space-between;
    align-items: end;
    gap: 1rem;
    margin-bottom: .65rem;
}

.section-title {
    font-size: 1.07rem;
    font-weight: 850;
    letter-spacing: -.015em;
    color: var(--iqac-text);
}

.section-sub {
    margin-top: .16rem;
    color: #748089;
    font-size: .8rem;
    line-height: 1.4;
}

.upload-card {
    padding: 1rem;
    border: 1px solid var(--iqac-border);
    border-radius: 18px;
    background: var(--iqac-surface);
    box-shadow: 0 8px 24px rgba(20,33,43,.045);
}

.upload-banner {
    display: flex;
    align-items: center;
    gap: .75rem;
    padding: .74rem .82rem;
    margin-bottom: .72rem;
    border: 1px dashed rgba(23,107,135,.24);
    border-radius: 14px;
    background: rgba(23,107,135,.035);
}

.upload-icon {
    width: 38px;
    height: 38px;
    display: grid;
    place-items: center;
    border-radius: 11px;
    background: rgba(23,107,135,.10);
    color: var(--iqac-primary);
    font-size: 1.05rem;
    flex: 0 0 auto;
}

.upload-title { font-size: .82rem; font-weight: 820; }
.upload-help { margin-top: .1rem; font-size: .72rem; color: #758089; line-height: 1.45; }

.file-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(235px, 1fr));
    gap: .48rem;
    margin-top: .72rem;
}

.file-chip {
    display: flex;
    align-items: center;
    gap: .55rem;
    min-width: 0;
    padding: .48rem .58rem;
    border: 1px solid rgba(20,33,43,.08);
    border-radius: 11px;
    background: rgba(127,127,127,.025);
}

.file-type {
    width: 31px;
    height: 31px;
    display: grid;
    place-items: center;
    flex: 0 0 auto;
    border-radius: 8px;
    background: rgba(23,107,135,.09);
    color: var(--iqac-primary);
    font-size: .63rem;
    font-weight: 900;
}

.file-name {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: .72rem;
    font-weight: 650;
}

.file-size { margin-left: auto; flex: 0 0 auto; color: #879199; font-size: .66rem; }

.stat-row { margin: .95rem 0 .9rem; }

.status-card {
    padding: .78rem .9rem;
    border: 1px solid var(--iqac-border);
    border-radius: 14px;
    background: rgba(255,255,255,.55);
}

.status-label { color: #78848c; font-size: .66rem; text-transform: uppercase; letter-spacing: .08em; font-weight: 800; }
.status-value { margin-top: .18rem; font-size: 1.1rem; font-weight: 900; letter-spacing: -.02em; }
.status-note { margin-top: .08rem; color: #8b959c; font-size: .67rem; }

.info-strip {
    display: flex;
    align-items: center;
    gap: .55rem;
    padding: .62rem .78rem;
    margin-top: .7rem;
    border: 1px solid rgba(23,107,135,.10);
    border-radius: 11px;
    background: rgba(23,107,135,.035);
    color: #62717a;
    font-size: .72rem;
}

.info-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--iqac-primary);
    flex: 0 0 auto;
}

.result-head {
    padding: 1rem 1.05rem .82rem;
    border: 1px solid var(--iqac-border);
    border-radius: 16px 16px 0 0;
    background: rgba(255,255,255,.55);
}

.export-card {
    padding: 1.05rem;
    border: 1px solid var(--iqac-border);
    border-radius: 16px;
    background: linear-gradient(135deg, rgba(23,107,135,.05), rgba(124,77,255,.035));
}

.export-file {
    display: flex;
    align-items: center;
    gap: .7rem;
    margin-bottom: .7rem;
}

.export-icon {
    width: 43px;
    height: 43px;
    display: grid;
    place-items: center;
    border-radius: 12px;
    background: rgba(23,107,135,.11);
    color: var(--iqac-primary);
    font-size: 1.15rem;
}

.export-title { font-weight: 850; font-size: .9rem; }
.export-sub { margin-top: .1rem; font-size: .73rem; color: #738089; line-height: 1.45; }

.footer {
    margin-top: 1.5rem;
    padding-top: .75rem;
    border-top: 1px solid rgba(20,33,43,.08);
    text-align: center;
    color: #879198;
    font-size: .67rem;
}

/* Make Streamlit controls feel more consistent without changing behavior. */
div[data-testid="stFileUploader"] section {
    border-radius: 14px !important;
}

button[kind="primary"] {
    border-radius: 11px !important;
    font-weight: 800 !important;
}

@media (max-width: 900px) {
    .workflow { grid-template-columns: repeat(2, minmax(0,1fr)); }
    .hero-row { flex-direction: column; }
}

@media (max-width: 560px) {
    .workflow { grid-template-columns: 1fr; }
    .hero { padding: 1.1rem; }
}
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
        done = " done" if number < active_step else ""
        parts.append(
            f"<div class='step{active}{done}'><div class='step-num'>{number}</div>"
            f"<div class='step-text'><b>{label}</b><span>{helper}</span></div></div>"
        )
    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)


def render_file_chips(files: list[Any]) -> None:
    if not files:
        return
    bits = ["<div class='file-grid'>"]
    for item in files:
        size_mb = getattr(item, "size", 0) / (1024 * 1024)
        ext = item.name.rsplit(".", 1)[-1].upper() if "." in item.name else "FILE"
        bits.append(
            f"<div class='file-chip'><div class='file-type'>{ext[:4]}</div>"
            f"<div class='file-name' title='{item.name}'>{item.name}</div>"
            f"<div class='file-size'>{size_mb:.1f} MB</div></div>"
        )
    bits.append("</div>")
    st.markdown("".join(bits), unsafe_allow_html=True)


def render_stats(file_count: int, activity_count: int, analyzed: bool) -> None:
    stat1, stat2, stat3 = st.columns(3)
    with stat1:
        st.markdown(
            f"<div class='status-card'><div class='status-label'>Documents</div>"
            f"<div class='status-value'>{file_count}</div>"
            f"<div class='status-note'>Files selected</div></div>",
            unsafe_allow_html=True,
        )
    with stat2:
        st.markdown(
            f"<div class='status-card'><div class='status-label'>Activities</div>"
            f"<div class='status-value'>{activity_count}</div>"
            f"<div class='status-note'>{'Extracted records' if analyzed else 'Waiting for analysis'}</div></div>",
            unsafe_allow_html=True,
        )
    with stat3:
        status = "Ready" if API_KEY else "Not configured"
        note = "Experiential gateway configured" if API_KEY else "Add EXPLABS_API_KEY"
        st.markdown(
            f"<div class='status-card'><div class='status-label'>AI Status</div>"
            f"<div class='status-value'>{status}</div>"
            f"<div class='status-note'>{note}</div></div>",
            unsafe_allow_html=True,
        )


# Header
st.markdown(
    f"""
<div class='hero'>
  <div class='hero-row'>
    <div>
      <div class='brand-row'>
        <div class='brand-mark'>📚</div>
        <div>
          <div class='kicker'>Institutional Quality Assurance</div>
          <h1 class='title'>IQAC Analyzer</h1>
        </div>
      </div>
      <div class='subtitle'>Analyze activity documents and build one clean, reviewable IQAC Master Data table with activity details, conservative NAAC mapping, document presence/absence, and source-page traceability.</div>
      <div class='institution-line'>{INSTITUTION}</div>
    </div>
    <div class='model-badge'><span class='model-dot'></span> Experiential · {MODEL}</div>
  </div>
</div>
""",
    unsafe_allow_html=True,
)

render_workflow(4 if st.session_state.analysis_done and st.session_state.records else (3 if st.session_state.analysis_done else 1))

if not API_KEY:
    st.error("Experiential Labs API is not configured. Add EXPLABS_API_KEY to Streamlit Secrets.")
    st.stop()

st.markdown(
    """
<div class='section-head'>
  <div>
    <div class='section-title'>Start with your activity documents</div>
    <div class='section-sub'>Upload PDF, DOCX or TXT files. No separate photo-evidence upload is required; the analyzer checks the uploaded document itself.</div>
  </div>
</div>
""",
    unsafe_allow_html=True,
)

with st.container(border=True):
    st.markdown(
        """
<div class='upload-card'>
  <div class='upload-banner'>
    <div class='upload-icon'>⬆</div>
    <div>
      <div class='upload-title'>Drop your IQAC documents here</div>
      <div class='upload-help'>For the cleanest result, upload one complete activity document when possible. Missing information is retained as <b>Not Identified</b> instead of being invented.</div>
    </div>
  </div>
</div>
""",
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

    if uploads:
        st.markdown(
            f"<div class='info-strip'><span class='info-dot'></span><span><b>{len(uploads)} document(s)</b> selected · one AI analysis request per uploaded document</span></div>",
            unsafe_allow_html=True,
        )

    c1, c2 = st.columns([1, 1], gap="small")
    with c1:
        analyze = st.button(
            "✨ Analyze documents",
            type="primary",
            width="stretch",
        )
    with c2:
        if st.button("↺ Clear", width="stretch"):
            reset_app()
            st.rerun()

render_stats(
    file_count=len(uploads or []),
    activity_count=len(st.session_state.records),
    analyzed=st.session_state.analysis_done,
)

if analyze:
    if not uploads:
        st.warning("Please upload at least one document.")
        st.stop()

    all_records: list[dict[str, str]] = []
    summaries: list[dict[str, Any]] = []
    progress = st.progress(0, text="Starting analysis…")

    total = len(uploads)

    # Performance optimization: analyze a few documents concurrently instead of
    # waiting for every AI request to finish before starting the next one.
    # Three workers keeps the app responsive without flooding the provider gateway.
    max_workers = min(3, total)
    jobs: list[tuple[int, str, bytes]] = []
    for idx, uploaded in enumerate(uploads):
        raw = uploaded.getvalue()
        if len(raw) > MAX_FILE_MB * 1024 * 1024:
            st.error(f"{uploaded.name} exceeds the {MAX_FILE_MB} MB file limit.")
            continue
        jobs.append((idx, uploaded.name, raw))

    completed = 0
    results: dict[int, tuple[str, list[dict[str, str]], dict[str, Any]]] = {}

    def run_one(job: tuple[int, str, bytes]):
        idx, filename, raw = job
        records, summary = analyze_report(
            raw=raw,
            filename=filename,
            model=MODEL,
            api_key=API_KEY,
            base_url=BASE_URL,
        )
        return idx, filename, records, summary

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {executor.submit(run_one, job): job for job in jobs}

        for future in as_completed(future_map):
            completed += 1
            job = future_map[future]
            try:
                idx, filename, records, summary = future.result()
                results[idx] = (filename, records, summary)
            except AIEngineError as exc:
                idx, filename, _ = job
                results[idx] = (filename, [], {"error": str(exc)})
            except Exception as exc:
                idx, filename, _ = job
                results[idx] = (filename, [], {"error": f"Unexpected error while analyzing {filename}: {exc}"})

            progress.progress(
                completed / max(1, len(jobs)),
                text=f"Analyzed {completed}/{len(jobs)} documents…",
            )

    # Restore upload order so the exported master data remains deterministic.
    next_record_id = 1
    for idx in sorted(results):
        filename, records, summary = results[idx]
        if "error" in summary:
            st.error(summary["error"])
            continue
        for record in records:
            record["Record ID"] = f"IQAC-{next_record_id:04d}"
            next_record_id += 1
            all_records.append(record)
        summary["File"] = filename
        summaries.append(summary)

    # Show completion once all concurrent tasks have finished.
    progress.progress(1.0, text="Analysis complete")
    st.session_state.records = all_records
    st.session_state.summaries = summaries
    st.session_state.analysis_done = True
    st.session_state.excel = build_excel_bytes(all_records) if all_records else None

if st.session_state.analysis_done:
    records = st.session_state.records

    st.markdown("<div style='height:.35rem'></div>", unsafe_allow_html=True)

    if records:
        tab_review, tab_export = st.tabs(["📋 Review data", "⬇️ Export"])

        with tab_review:
            st.markdown(
                """
<div class='result-head'>
  <div class='section-title'>Review extracted activities</div>
  <div class='section-sub'>Edit the values before exporting. Record ID, Source Report and Source Page remain locked for traceability.</div>
</div>
""",
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
                """
<div class='export-card'>
  <div class='export-file'>
    <div class='export-icon'>📊</div>
    <div>
      <div class='export-title'>IQAC_Master_Data.xlsx</div>
      <div class='export-sub'>One master worksheet with activity details, Documents Present, Documents Absent, source report and source-page traceability.</div>
    </div>
  </div>
</div>
""",
                unsafe_allow_html=True,
            )
            st.markdown("<div style='height:.65rem'></div>", unsafe_allow_html=True)
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
