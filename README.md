# IQAC Analyzer

A Streamlit application with **two independent facilities** in one app:

1. **Activity Report Analyzer** — the existing activity-report workflow and schema are preserved in `activity_app.py` and the original `src/` modules.
2. **General Document Extractor** — a separate module under `general_extractor/` that identifies the document type and creates document-specific fields dynamically.

## General Document Extractor

The extractor is designed for mixed institutional records such as activity reports, notices, circulars, committee documents, placement records, certificates, attendance, meeting minutes, workshop/seminar reports, proposals, MoUs, achievements, research/publication records and unknown document types.

It produces:

- Document index
- Dynamic extracted fields
- Extracted table content
- Source-page information where available
- Confidence level
- Warning/fallback status
- Excel export with three worksheets

If Gemini is unavailable or a request fails, the general extractor keeps a local extraction fallback instead of crashing the entire app.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Streamlit Cloud

Use this repository as the Streamlit app source and keep the existing `GEMINI_API_KEY` and optional `GEMINI_MODEL` / `MAX_FILE_MB` secrets.

The two facilities share only the top-level `app.py` router. Their extraction engines and output formats are separate.
