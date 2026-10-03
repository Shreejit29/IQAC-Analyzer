from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import pandas as pd
import streamlit as st

from .engine import GeneralExtractorError, analyze_document
from .excel_exporter import build_excel_bytes


def render(uploads: list[Any], model: str, api_key: str, max_file_mb: int) -> None:
    if "general_results" not in st.session_state:
        st.session_state.general_results = []
    if "general_excel" not in st.session_state:
        st.session_state.general_excel = None

    st.markdown("# 📄 General Document Extractor")
    st.caption("Upload institutional documents of different types. The extractor identifies the document structure and creates fields from the content instead of forcing every file into an activity-report template.")

    if uploads:
        st.info(f"{len(uploads)} document(s) selected. One extraction request may be used per document.")

    col1, col2 = st.columns([1, 1])
    with col1:
        extract = st.button("🔍 Extract Information", type="primary", width="stretch")
    with col2:
        clear = st.button("↺ Clear General Extractor", width="stretch")
    if clear:
        st.session_state.general_results = []
        st.session_state.general_excel = None
        st.rerun()

    if extract:
        if not uploads:
            st.warning("Please upload at least one document.")
            return

        jobs = []
        for uploaded in uploads:
            raw = uploaded.getvalue()
            if len(raw) > max_file_mb * 1024 * 1024:
                st.warning(f"Skipped {uploaded.name}: file is larger than {max_file_mb} MB.")
                continue
            jobs.append((uploaded.name, raw))

        results = []
        progress = st.progress(0, text="Extracting documents…")
        total = len(jobs)
        with ThreadPoolExecutor(max_workers=min(3, max(1, total))) as pool:
            futures = {pool.submit(analyze_document, raw, name, model, api_key): (idx, name) for idx, (name, raw) in enumerate(jobs)}
            completed = 0
            for future in as_completed(futures):
                idx, name = futures[future]
                try:
                    result, warning = future.result()
                except Exception as exc:
                    result, warning = analyze_document(b"", name, model, "")
                    warning = f"Extraction failed: {exc}"
                results.append({"filename": name, "result": result, "warning": warning})
                completed += 1
                progress.progress(completed / total, text=f"Processed {completed}/{total}: {name}")
        results.sort(key=lambda x: x["filename"].lower())
        st.session_state.general_results = results
        st.session_state.general_excel = build_excel_bytes(results)
        progress.empty()

    results = st.session_state.general_results
    if not results:
        st.markdown("### What this can handle")
        st.write("Activity reports, notices, circulars, committee lists, placement documents, certificates, attendance sheets, meeting minutes, workshop/seminar reports, proposals, MoUs, student achievements, research/publication records and unknown document types.")
        return

    st.markdown("### Document overview")
    overview = []
    for item in results:
        r = item["result"]
        overview.append({
            "File": item["filename"],
            "Document Type": r.document_type,
            "Title": r.document_title,
            "Date": r.document_date,
            "Academic Year": r.academic_year,
            "Fields": len(r.fields),
            "Tables": len(r.tables),
            "Status": "Fallback / warning" if item.get("warning") else "Extracted",
        })
    st.dataframe(pd.DataFrame(overview), hide_index=True, width="stretch")

    for item in results:
        r = item["result"]
        with st.expander(f"{r.document_type} — {item['filename']}", expanded=False):
            a, b, c, d = st.columns(4)
            a.metric("Type", r.document_type)
            b.metric("Fields", len(r.fields))
            c.metric("Tables", len(r.tables))
            d.metric("Entities", len(r.key_entities))
            st.write(f"**Title:** {r.document_title}")
            st.write(f"**Summary:** {r.short_summary}")
            if item.get("warning"):
                st.warning(item["warning"])
            if r.fields:
                df = pd.DataFrame([f.model_dump() for f in r.fields])
                st.dataframe(df, hide_index=True, width="stretch")
            if r.tables:
                for table in r.tables:
                    st.markdown(f"**Table: {table.title}** · Page: {table.source_page}")
                    headers = table.headers or None
                    st.dataframe(pd.DataFrame(table.rows, columns=headers), hide_index=True, width="stretch")

    st.markdown("### Export")
    if st.session_state.general_excel:
        st.download_button(
            "⬇️ Download General_Document_Extraction.xlsx",
            data=st.session_state.general_excel,
            file_name="General_Document_Extraction.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            width="stretch",
        )
