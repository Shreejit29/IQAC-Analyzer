from __future__ import annotations

import os
from typing import Any

import pandas as pd
import streamlit as st

from src.ai_engine import GeminiError, analyze_report, check_connection
from src.document_parser import basic_metadata, validate_upload
from src.excel_exporter import build_excel_bytes
from src.record_utils import (
    COLUMNS, EVIDENCE_FIELDS, NAAC_ATTRIBUTES, deduplicate_records,
    normalize_record, session_summary,
)
from src.validation_engine import validate_cross_document, validation_summary

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
    "records": [], "summaries": [], "analysis_done": False, "excel": None, "validation_issues": [],
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
    for key in ["records", "summaries", "analysis_done", "excel", "validation_issues", "editor_df"]:
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

    # Run conservative validation after extraction/deduplication. Validation never
    # deletes records or invents facts; it only adds review flags and issue notes.
    records, validation_issues = validate_cross_document(records)

    st.session_state.records = records
    st.session_state.validation_issues = validation_issues
    st.session_state.summaries = summaries
    st.session_state.analysis_done = True
    st.session_state.excel = build_excel_bytes(records) if records else None
    if duplicate_count:
        st.info(f"{duplicate_count} possible duplicate extraction record(s) were retained and flagged for review.")

    vsummary = validation_summary(records, validation_issues)
    if vsummary["records_with_issues"]:
        st.warning(
            f"Validation found {vsummary['records_with_issues']} record(s) with data-quality issues "
            f"and {len(validation_issues)} cross-document issue(s). Review them before official use."
        )

if st.session_state.analysis_done:
    summary = session_summary(st.session_state.records)
    st.subheader("Analysis Summary")
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Reports", len(st.session_state.summaries))
    m2.metric("Activities Detected", summary["activities"])
    m3.metric("Needs Verification", summary["needs_verification"])
    m4.metric("Activities with Evidence Gaps", summary["evidence_gaps"])
    m5.metric("Possible Duplicates", summary["possible_duplicates"])
    m6.metric("Validation Issues", len(st.session_state.get("validation_issues", [])))

    if st.session_state.summaries:
        st.dataframe(pd.DataFrame(st.session_state.summaries), width="stretch", hide_index=True)

    if st.session_state.records:
        st.subheader("🔎 Verification Center")
        st.caption(
            "Review the extracted records before using them as official IQAC data. "
            "AI extraction is not treated as final approval."
        )

        records_df = pd.DataFrame(st.session_state.records).reindex(columns=COLUMNS).fillna("")

        vf1, vf2, vf3 = st.columns([1.4, 1.4, 2.2])
        with vf1:
            verification_filter = st.selectbox(
                "Verification status",
                ["All", "Needs Verification", "Possible Duplicate", "Verified"],
                key="verification_filter",
            )
        with vf2:
            confidence_filter = st.selectbox(
                "Confidence",
                ["All", "High", "Medium", "Low"],
                key="confidence_filter",
            )
        with vf3:
            search_text = st.text_input(
                "Search activity / department / source",
                placeholder="e.g. tree plantation, NSS, seminar...",
                key="verification_search",
            )

        visible_mask = pd.Series(True, index=records_df.index)
        if verification_filter != "All":
            visible_mask &= records_df["Verification Status"].eq(verification_filter)
        if confidence_filter != "All":
            visible_mask &= records_df["Extraction Confidence"].str.startswith(confidence_filter, na=False)
        if search_text.strip():
            needle = search_text.strip().lower()
            search_cols = ["Activity Title", "Organizing Department", "Organizing Committee", "Source Report"]
            text_match = pd.Series(False, index=records_df.index)
            for col in search_cols:
                text_match |= records_df[col].astype(str).str.lower().str.contains(needle, regex=False, na=False)
            visible_mask &= text_match

        visible_df = records_df.loc[visible_mask].copy()

        vc1, vc2, vc3, vc4 = st.columns(4)
        vc1.metric("Records Shown", len(visible_df))
        vc2.metric("Need Verification", int((records_df["Verification Status"] == "Needs Verification").sum()))
        vc3.metric("Possible Duplicates", int((records_df["Verification Status"] == "Possible Duplicate").sum()))
        vc4.metric("Low Confidence", int(records_df["Extraction Confidence"].astype(str).str.startswith("Low", na=False).sum()))

        if not visible_df.empty:
            issue_rows = []
            for _, row in visible_df.iterrows():
                missing = str(row.get("Missing Information", ""))
                gaps = str(row.get("Evidence Gaps", ""))
                issues = []
                if missing and missing != "None identified":
                    issues.append(f"Missing: {missing}")
                if gaps and gaps != "None identified":
                    issues.append(f"Evidence: {gaps}")
                if str(row.get("Verification Status", "")) == "Possible Duplicate":
                    issues.append(f"Duplicate of: {row.get('Duplicate Of', 'Not identified')}")
                issue_rows.append({
                    "Record ID": row.get("Record ID", ""),
                    "Activity": row.get("Activity Title", ""),
                    "Confidence": row.get("Extraction Confidence", ""),
                    "Issues": " | ".join(issues) if issues else "No automatic issue detected",
                })
            st.dataframe(pd.DataFrame(issue_rows), width="stretch", hide_index=True)
        else:
            st.info("No records match the selected verification filters.")

        # Only records currently visible in the verification filter are edited.
        # This prevents an accidental bulk edit of hundreds of unrelated records.
        st.subheader("✏️ Review / Edit Records")
        st.caption(
            "Edit the visible records. After editing, missing-information, evidence-gap and "
            "confidence fields are recalculated automatically."
        )

        if not visible_df.empty:
            editor_columns = [c for c in COLUMNS if c in visible_df.columns]
            edited = st.data_editor(
                visible_df[editor_columns],
                key="verification_editor",
                width="stretch",
                height=620,
                hide_index=True,
                num_rows="fixed",
                disabled=["Record ID", "Source Report", "Extraction Status", "Extraction Confidence", "Missing Information", "Evidence Gaps"],
                column_config={
                    "NAAC Attribute": st.column_config.SelectboxColumn(
                        "NAAC Attribute", options=NAAC_ATTRIBUTES, width="large"
                    ),
                    "Verification Status": st.column_config.SelectboxColumn(
                        "Verification Status",
                        options=["Needs Verification", "Verified", "Possible Duplicate"],
                        width="medium",
                    ),
                },
            )

            if st.button("💾 Apply Review Changes", type="primary", width="stretch"):
                edited_records = edited.to_dict(orient="records")
                visible_ids = set(visible_df["Record ID"].astype(str))
                by_id = {str(r.get("Record ID")): r for r in st.session_state.records}

                for edited_record in edited_records:
                    record_id = str(edited_record.get("Record ID", ""))
                    original = by_id.get(record_id)
                    if original is None or record_id not in visible_ids:
                        continue

                    # Preserve system-generated metadata and duplicate fields.
                    old_id = original.get("Record ID", record_id)
                    old_source = original.get("Source Report", "Not Identified")
                    old_duplicate = {
                        k: original[k] for k in ("Duplicate Of", "Duplicate Similarity") if k in original
                    }
                    verification_status = edited_record.get("Verification Status", original.get("Verification Status", "Needs Verification"))

                    refreshed = normalize_record(
                        edited_record,
                        old_source,
                        1,
                        str(edited_record.get("Source Page", original.get("Source Page", "Not Identified"))),
                    )
                    refreshed["Record ID"] = old_id
                    refreshed["Source Report"] = old_source
                    refreshed["Verification Status"] = verification_status
                    refreshed.update(old_duplicate)
                    by_id[record_id] = refreshed

                reviewed_records = list(by_id.values())
                reviewed_records, reviewed_issues = validate_cross_document(reviewed_records)
                st.session_state.records = reviewed_records
                st.session_state.validation_issues = reviewed_issues
                st.session_state.excel = build_excel_bytes(st.session_state.records)
                st.success("Review changes applied and validation recalculated.")
                st.rerun()

        st.subheader("🧪 Data Quality Validation")
        validation_issues = st.session_state.get("validation_issues", [])
        if validation_issues:
            vs = validation_summary(st.session_state.records, validation_issues)
            q1, q2, q3, q4 = st.columns(4)
            q1.metric("Records with Issues", vs["records_with_issues"])
            q2.metric("High Severity", vs["high_severity_issues"])
            q3.metric("Quantitative Issues", vs["quantitative_inconsistencies"])
            q4.metric("Cross-document Issues", vs["cross_document_inconsistencies"])

            st.caption(
                "Validation is conservative: records are retained, factual conflicts are flagged, "
                "and missing information is not replaced with guesses."
            )
            st.dataframe(
                pd.DataFrame(validation_issues),
                width="stretch",
                hide_index=True,
            )
        else:
            st.success("No cross-document or quantitative inconsistencies were detected automatically.")

        st.subheader("📋 Evidence Review")
        evidence_columns = ["Record ID", "Activity Title", "Source Report"] + EVIDENCE_FIELDS + ["Evidence Gaps"]
        evidence_df = pd.DataFrame(st.session_state.records).reindex(columns=evidence_columns).fillna("")
        st.dataframe(evidence_df, width="stretch", hide_index=True)

        st.subheader("📊 Current Master Data")
        st.dataframe(
            pd.DataFrame(st.session_state.records).reindex(columns=COLUMNS).fillna(""),
            width="stretch",
            hide_index=True,
        )

        st.session_state.excel = build_excel_bytes(st.session_state.records)
        st.download_button(
            "⬇️ Download IQAC_Master_Data.xlsx",
            data=st.session_state.excel,
            file_name="IQAC_Master_Data.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            width="stretch",
        )
    else:
        st.warning("No activities were extracted. Check the report type and Gemini configuration, then try again.")

st.divider()
st.markdown("**Privacy / processing:** uploaded reports are processed for the current Streamlit session. The app does not maintain its own database or permanent document archive. For Gemini processing, the report is transmitted to Google's Gemini API; uploaded Gemini Files are deleted by the app after analysis on a best-effort basis and otherwise expire automatically according to Google's Files API retention. Do not upload documents you are not authorized to send to a third-party AI service.")
st.markdown('<div class="small">The analyzer prepares data for IQAC use; it does not calculate or certify an official NAAC accreditation score.</div>', unsafe_allow_html=True)
