# IQAC Analyzer — Final Gemini Online Edition

A production-oriented Streamlit application for extracting IQAC activities from real PDF/DOCX reports and preparing a single `IQAC_Master_Data.xlsx` file.

## Final workflow

1. Admin deploys the app on Streamlit.
2. Admin stores the Gemini API key in Streamlit Secrets.
3. Staff open the app URL.
4. Staff upload one or more complete IQAC reports.
5. Click **Analyze Reports**.
6. Gemini reads the complete report, including scanned pages, tables, photos and handwriting.
7. The app identifies every distinct activity and connects the activity summary to whatever evidence is actually present.
8. Staff review/edit the extracted rows.
9. Staff download `IQAC_Master_Data.xlsx` and share/store the latest master file through the college's normal workflow.

## Important document logic

The app does **not** require every activity to contain the same attachments. Proposal, Notice, Programme Table, Invitation, Attendance, Event Report, Photos, Feedback, News, etc. are detected individually. A missing Programme Table does not invalidate an activity.

The first 1–2 page Activity Sheet / Basic Summary is treated as the primary anchor when present, and later pages are connected as supporting evidence.

## Gemini

Default model: `gemini-3.8-flash`. The model is hidden from staff and can be changed only by the administrator through Streamlit Secrets.

The app uses the current Google GenAI Python SDK and structured JSON output. Each uploaded file is sent to Gemini for multimodal document understanding. The app attempts to delete the Gemini File after analysis.

## Deploy

See `DEPLOY_STREAMLIT.md`.
