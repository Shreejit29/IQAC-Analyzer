# IQAC Analyzer — Groq Streamlit Edition

A production-oriented Streamlit application for extracting IQAC activities from real PDF/DOCX reports and preparing a single `IQAC_Master_Data.xlsx` file.

## Final workflow

1. Admin deploys the app on Streamlit.
2. Admin stores the Groq API key in Streamlit Secrets.
3. Staff open the app URL.
4. Staff upload one or more complete IQAC reports.
5. Click **Extract activities**.
6. Readable documents are extracted locally first; scanned PDFs use Groq vision page analysis when necessary.
7. The app identifies every distinct activity and connects the activity summary to whatever evidence is actually present.
8. Staff review/edit the extracted rows.
9. Staff download `IQAC_Master_Data.xlsx`.

## Important document logic

The app does **not** require every activity to contain the same attachments. Proposal, Notice, Programme Table, Invitation, Attendance, Event Report, Photos, Feedback, News, etc. are detected individually. A missing Programme Table does not invalidate an activity.

## Groq

Default model: `qwen/qwen3.8-27b`.

The application uses Groq's structured-output JSON schema interface. Readable documents are sent as text. Scanned PDFs are rendered locally into page images and sent to the multimodal model in small image batches because Groq's vision API accepts image inputs rather than Gemini-style uploaded PDF files.

## Deploy

See `DEPLOY_STREAMLIT.md`.
