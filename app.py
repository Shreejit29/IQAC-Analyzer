from __future__ import annotations

import os
from typing import Any

import pandas as pd
import streamlit as st

from src.ai_engine import GeminiError, analyze_report
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

DEFAULT_STATE = {
    "records": [],
    "summaries": [],
    "analysis_done": False,
    "excel": None,
}
for key, default in DEFAULT_STATE.items():
    if key not in st.session_state:
        st.session_state[key] = default


# Theme-friendly CSS: color accents are fixed, surfaces inherit Streamlit theme.
st.markdown(
    r"""
<style>
:root { --accent:#187f8f; --accent2:#245fc0; }
.block-container { max-width:1500px; padding:1.1rem clamp(.9rem,3vw,3rem) 2.5rem; }

.hero {
  position:relative; overflow:hidden; margin-bottom:1rem; padding:1.45rem 1.55rem;
  border:1px solid rgba(24,127,143,.24); border-radius:24px;
  background:
    radial-gradient(circle at 92% 20%, rgba(36,95,192,.14), transparent 34%),
    radial-gradient(circle at 8% 110%, rgba(24,127,143,.12), transparent 38%),
    linear-gradient(135deg, rgba(24,127,143,.075), rgba(36,95,192,.045));
  box-shadow:0 14px 40px rgba(0,0,0,.07);
}
.hero::after { content:""; position:absolute; width:170px; height:170px; right:-70px; top:-85px; border:1px solid rgba(24,127,143,.14); border-radius:50%; }
.hero-row { display:flex; align-items:center; justify-content:space-between; gap:1rem; position:relative; z-index:1; }
.brand { display:flex; align-items:flex-start; gap:.9rem; min-width:0; }
.brand-icon { width:52px; height:52px; display:grid; place-items:center; border-radius:15px; flex:0 0 auto; color:white; font-size:1.45rem; background:linear-gradient(135deg,#187f8f,#245fc0); box-shadow:0 10px 24px rgba(36,95,192,.2); }
.kicker { margin:0 0 .15rem; color:var(--accent); font-size:.72rem; font-weight:850; letter-spacing:.12em; text-transform:uppercase; }
.title { margin:0; font-size:clamp(1.7rem,4vw,2.55rem); line-height:1.05; letter-spacing:-.045em; font-weight:850; }
.subtitle { margin:.45rem 0 0; max-width:900px; opacity:.68; line-height:1.5; font-size:.94rem; }
.badge { padding:.45rem .65rem; border-radius:999px; border:1px solid rgba(24,127,143,.2); background:rgba(24,127,143,.07); font-size:.75rem; font-weight:750; white-space:nowrap; }

.workflow { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:.6rem; margin-bottom:1.15rem; }
.step { display:flex; align-items:center; gap:.6rem; padding:.62rem .72rem; border:1px solid rgba(127,127,127,.15); border-radius:14px; background:rgba(127,127,127,.035); opacity:.58; }
.step.active { opacity:1; border-color:rgba(24,127,143,.3); background:rgba(24,127,143,.06); }
.step-num { width:27px; height:27px; display:grid; place-items:center; border-radius:50%; border:1px solid rgba(127,127,127,.18); font-size:.76rem; font-weight:850; flex:0 0 auto; }
.step.active .step-num { color:#fff; border-color:transparent; background:linear-gradient(135deg,#187f8f,#245fc0); }
.step-text b { font-size:.83rem; } .step-text span { display:block; margin-top:.08rem; font-size:.69rem; opacity:.55; }

.section { margin-top:1rem; } .section-title { font-size:1.1rem; font-weight:820; letter-spacing:-.02em; } .section-sub { margin-top:.15rem; margin-bottom:.65rem; opacity:.62; font-size:.82rem; }
.card-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:.7rem; }
.card { padding:1rem; border:1px solid rgba(127,127,127,.15); border-radius:17px; background:rgba(127,127,127,.03); }
.card-label { font-size:.68rem; text-transform:uppercase; letter-spacing:.07em; opacity:.55; font-weight:800; }
.card-value { margin-top:.18rem; font-size:1.55rem; font-weight:850; letter-spacing:-.04em; }
.card-note { margin-top:.18rem; font-size:.74rem; opacity:.55; }

.upload-note { display:flex; align-items:center; gap:.75rem; padding:.72rem .82rem; margin-bottom:.75rem; border:1px dashed rgba(24,127,143,.3); border-radius:13px; background:rgba(24,127,143,.045); font-size:.82rem; }
.upload-icon { width:34px; height:34px; display:grid; place-items:center; border-radius:10px; background:rgba(24,127,143,.10); flex:0 0 auto; }
.chips { display:flex; flex-wrap:wrap; gap:.45rem; margin-top:.55rem; }
.chip { display:inline-flex; gap:.4rem; align-items:center; padding:.38rem .55rem; border:1px solid rgba(127,127,127,.14); border-radius:10px; background:rgba(127,127,127,.035); font-size:.75rem; }
.chip span { opacity:.5; }

.surface { padding:1rem; border:1px solid rgba(127,127,127,.15); border-radius:17px; background:rgba(127,127,127,.03); }
.stButton>button,.stDownloadButton>button { min-height:2.6rem; border-radius:11px; font-weight:780; }
div[data-testid="stDataEditor"], div[data-testid="stDataFrame"] { border-radius:15px; overflow:hidden; border:1px solid rgba(127,127,127,.15); }
.stTabs [data-baseweb="tab-list"] { gap:.25rem; border-bottom:1px solid rgba(127,127,127,.13); }
.stTabs [data-baseweb="tab"] { padding:.6rem .75rem; border-radius:10px 10px 0 0; }
.footer { margin-top:1.7rem; padding-top:.75rem; border-top:1px solid rgba(127,127,127,.12); text-align:center; opacity:.48; font-size:.72rem; }
@media (max-width:900px){ .workflow{grid-template-columns:repeat(2,minmax(0,1fr));} .card-grid{grid-template-columns:1fr;} .hero-row{align-items:flex-start; flex-direction:column;} }
@media (max-width:560px){ .workflow{grid-template-columns:1fr;} .block-container{padding-left:.7rem;padding-right:.7rem;} }
</style>
""",
    unsafe_allow_html=True,
)


def reset_app() -> None:
    for key in DEFAULT_STATE:
        st.session_state.pop(key, None)
    for key, value in DEFAULT_STATE.items():
        st.session_state[key] = value


def render_workflow(active_step: int) -> None:
    steps = [(1,"Upload","Add reports"),(2,"AI Extract","Create rows"),(3,"Review","Check output"),(4,"Export","Download Excel")]
    html = ["<div class='workflow'>"]
    for n, label, helper in steps:
        active = " active" if n <= active_step else ""
        html.append(f"<div class='step{active}'><div class='step-num'>{n}</div><div class='step-text'><b>{label}</b><span>{helper}</span></div></div>")
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)


def render_file_chips(files: list[Any]) -> None:
    if not files:
        return
    bits = ["<div class='chips'>"]
    for item in files:
        size_mb = len(item.getvalue()) / (1024 * 1024)
        ext = item.name.rsplit('.',1)[-1].upper() if '.' in item.name else 'FILE'
        bits.append(f"<div class='chip'><b>{ext}</b> {item.name}<span>{size_mb:.1f} MB</span></div>")
    bits.append("</div>")
    st.markdown("".join(bits), unsafe_allow_html=True)


st.markdown(
    f"""
<div class='hero'>
  <div class='hero-row'>
    <div class='brand'>
      <div class='brand-icon'>📘</div>
      <div>
        <div class='kicker'>Institutional Quality Assurance</div>
        <h1 class='title'>IQAC AI Extractor</h1>
        <div class='subtitle'>Convert activity reports into a clean, reviewable IQAC master dataset. Upload reports, review the extracted activities, and download one polished Excel file.</div>
      </div>
    </div>
    <div class='badge'>✦ Fast AI workflow</div>
  </div>
  <div style='margin-top:.7rem;opacity:.55;font-size:.75rem;'>{INSTITUTION}</div>
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
<div class='section'>
  <div class='section-title'>Upload your reports</div>
  <div class='section-sub'>PDF, DOCX and TXT are supported. Multiple reports can be processed together, and each distinct activity becomes one row.</div>
</div>
""",
    unsafe_allow_html=True,
)

with st.container(border=True):
    st.markdown("<div class='upload-note'><div class='upload-icon'>⬆</div><div><b>Drop your IQAC reports here</b><br><span style='opacity:.58'>The AI reads the complete report and keeps missing facts as Not Identified rather than inventing them.</span></div></div>", unsafe_allow_html=True)
    uploads = st.file_uploader("Reports", type=["pdf","docx","txt"], accept_multiple_files=True, label_visibility="collapsed", help=f"Maximum {MAX_FILE_MB} MB per file.")
    render_file_chips(uploads or [])

    b1,b2 = st.columns([3,1])
    with b1:
        st.caption("No master Excel template is required. The output contains one clean sheet for all extracted activities.")
    with b2:
        if st.button("↺ Clear", width="stretch"):
            reset_app(); st.rerun()

x1,x2 = st.columns([2,4])
with x1:
    analyze = st.button("✨ Extract activities", type="primary", width="stretch")
with x2:
    st.caption("Fast path: readable PDF/DOCX/TXT text is extracted locally before Gemini is called. Scanned PDFs use Gemini document analysis only when necessary.")

if analyze:
    if not uploads:
        st.warning("Please upload at least one report.")
        st.stop()
    records: list[dict[str,str]] = []
    summaries: list[dict[str,Any]] = []
    progress = st.progress(0, text="Starting extraction…")
    total_files = len(uploads)
    for idx, uploaded in enumerate(uploads, start=1):
        try:
            raw = uploaded.getvalue()
            if len(raw) > MAX_FILE_MB * 1024 * 1024:
                raise ValueError(f"File exceeds the {MAX_FILE_MB} MB limit.")
            progress.progress((idx-1)/total_files, text=f"Reading {uploaded.name}…")
            file_records, _ = analyze_report(raw, uploaded.name, MODEL, API_KEY)
            records.extend(file_records)
            summaries.append({"Report":uploaded.name,"Activities":len(file_records),"Status":"Done"})
        except GeminiError as exc:
            summaries.append({"Report":uploaded.name,"Activities":0,"Status":f"AI Error: {exc}"})
        except Exception as exc:
            summaries.append({"Report":uploaded.name,"Activities":0,"Status":f"Error: {exc}"})
    progress.progress(1.0, text="Extraction complete.")
    for idx, record in enumerate(records, start=1):
        record["Record ID"] = f"IQAC-{idx:04d}"
    st.session_state.records = records
    st.session_state.summaries = summaries
    st.session_state.analysis_done = True
    st.session_state.excel = build_excel_bytes(records) if records else None
    st.rerun()


if st.session_state.analysis_done:
    records = st.session_state.records
    summaries = st.session_state.summaries
    done = sum(1 for s in summaries if s.get("Status") == "Done")
    total_activities = len(records)

    st.markdown("<div class='section'><div class='section-title'>Results</div><div class='section-sub'>Review the AI output before downloading the master workbook.</div></div>", unsafe_allow_html=True)
    st.markdown(f"""
<div class='card-grid'>
  <div class='card'><div class='card-label'>Reports processed</div><div class='card-value'>{done}/{len(summaries)}</div><div class='card-note'>Reports completed successfully</div></div>
  <div class='card'><div class='card-label'>Activities extracted</div><div class='card-value'>{total_activities}</div><div class='card-note'>One activity = one master row</div></div>
  <div class='card'><div class='card-label'>Output</div><div class='card-value'>{'Ready' if st.session_state.excel else '—'}</div><div class='card-note'>One clean Excel workbook</div></div>
</div>
""", unsafe_allow_html=True)

    if summaries:
        with st.expander("View report processing details"):
            st.dataframe(pd.DataFrame(summaries), width="stretch", hide_index=True)

    if records:
        review_tab, docs_tab, export_tab = st.tabs(["📝 Review activities", "📎 Documents & NAAC", "⬇️ Export"])

        with review_tab:
            st.markdown("<div class='section-title' style='margin-top:.15rem;'>Review extracted activities</div><div class='section-sub'>Edit any value that needs correction. Fixed-size editing prevents empty activity rows.</div>", unsafe_allow_html=True)
            df = pd.DataFrame(records).reindex(columns=COLUMNS).fillna("Not Identified")
            height = min(560, max(120, 44*(len(df)+1)+18))
            edited = st.data_editor(
                df,
                key="activity_editor",
                width="stretch",
                height=height,
                hide_index=True,
                num_rows="fixed",
                disabled=["Record ID","Source Report","Source Page"],
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

        with docs_tab:
            st.markdown("<div class='section-title' style='margin-top:.15rem;'>Documents & NAAC mapping</div><div class='section-sub'>See which supporting documents were identified and the primary NAAC reference for each activity.</div>", unsafe_allow_html=True)
            status_df = pd.DataFrame([
                {
                    "Activity":r.get("Activity Title","Not Identified"),
                    "✅ Present":r.get("Documents Present","None Identified"),
                    "❌ Absent":r.get("Documents Absent","None Identified"),
                    "NAAC Attribute":r.get("NAAC Attribute","Not Identified"),
                    "NAAC Metric":r.get("NAAC Metric","Not Identified"),
                }
                for r in st.session_state.records
            ])
            st.dataframe(status_df, width="stretch", hide_index=True, height=min(520,max(140,44*(len(status_df)+1))))

        with export_tab:
            st.markdown("<div class='section-title' style='margin-top:.15rem;'>Download your master data</div><div class='section-sub'>The workbook contains one polished sheet with activities, NAAC mapping, document status and source references.</div>", unsafe_allow_html=True)
            st.markdown("<div class='surface'><b>📊 IQAC Master Data</b><br><span style='opacity:.62;font-size:.82rem'>Excel workbook · one sheet · filters · frozen headers · print-ready layout</span></div>", unsafe_allow_html=True)
            st.download_button("⬇️ Download IQAC_Master_Data.xlsx", data=st.session_state.excel, file_name="IQAC_Master_Data.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary", width="stretch")

    else:
        st.warning("No activity was identified in the uploaded reports.")

st.markdown(f"<div class='footer'>AI-assisted extraction · {INSTITUTION} · Review extracted values against the source report before official use.</div>", unsafe_allow_html=True)
