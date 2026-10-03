# IQAC Analyzer — Gemini 3.5 Flash-Lite

A simple Streamlit application for extracting college IQAC activity information from PDF, DOCX and TXT reports into one editable Excel master sheet.

## What it does
1. Upload one or more activity reports.
2. Gemini 3.5 Flash-Lite analyzes each document.
3. Genuine activities are extracted into structured fields.
4. Review/edit the results in Streamlit.
5. Download `IQAC_Master_Data.xlsx`.

## Deliberately simple
- This is **IQAC Analyzer**, not the IQAC Report Generator.
- No Event Report generation.
- No IQAC report template filling.
- No photo-evidence module.
- No photograph processing.
- No separate evidence checklist.
- One AI request per uploaded PDF/document.
- PDFs are sent directly to Gemini instead of being rendered page-by-page.
- DOCX/TXT are extracted locally before Gemini analysis.

## Streamlit Secrets

```toml
GEMINI_API_KEY = "YOUR_GEMINI_API_KEY"
GEMINI_MODEL = "gemini-3.5-flash-lite"
INSTITUTION_NAME = "Ramsheth Thakur College of Commerce & Science"
MAX_FILE_MB = "50"
```

## Local run

```bash
pip install -r requirements.txt
streamlit run app.py
```
