

IQAC-Analyzer-main (3).zip
Zip Archive
go through this thoroughly and let me know instaed of gemini can we use this??

next

requirements.txt is updated and checked.

Changed
Removed:

google-genai
Added:

openai>=1.0,<2.0
Everything else is preserved.

Download updated requirements.txt

Next file: .streamlit/secrets.toml.example — we’ll replace the Gemini environment variables with the Experiential configuration.


requirements_experiential.txt
Document


next

The .streamlit/secrets.toml.example file is updated.

Now it uses
EXPLABS_API_KEY = "PASTE_YOUR_EXPERIENTIAL_LABS_API_KEY_HERE"
EXPERIENTIAL_MODEL = "deepseek-v4-flash-0731"
EXPERIENTIAL_BASE_URL = "https://api.experientiallabs.ai/v1"
Your institution name and MAX_FILE_MB settings are preserved.

Download updated secrets.toml.example

Next: README.md — we should update the documentation so nobody accidentally configures Gemini again.


next

README.md is updated for the Experiential Labs architecture.

Download updated README.md

The documentation now correctly reflects:

Experiential Labs instead of Gemini

local PDF text extraction

configurable AI model

EXPLABS_API_KEY

EXPERIENTIAL_MODEL

EXPERIENTIAL_BASE_URL

Next: DEPLOY_STREAMLIT.md.


README.md
Document


Library
/
README.md



IQAC Analyzer — Experiential Labs AI Gateway
A simple Streamlit application for extracting college IQAC activity information from PDF, DOCX and TXT reports into one editable Excel master sheet.

What it does
Upload one or more activity reports.

Experiential Labs routes the AI request to the configured model and returns structured activity data.

Genuine activities are extracted into structured fields.

Review/edit the results in Streamlit.

Download IQAC_Master_Data.xlsx.

Deliberately simple
This is IQAC Analyzer, not the IQAC Report Generator.

No Event Report generation.

No IQAC report template filling.

No photo-evidence module.

No photograph processing.

No separate evidence checklist.

One AI request per uploaded PDF/document.

PDF text is extracted locally with page markers before AI analysis.

DOCX/TXT are extracted locally before AI analysis.

The AI backend is provider-neutral through the Experiential Labs OpenAI-compatible API.

Streamlit Secrets
EXPLABS_API_KEY = "YOUR_EXPERIENTIAL_LABS_API_KEY"
EXPERIENTIAL_MODEL = "deepseek-v4-flash-0731"
EXPERIENTIAL_BASE_URL = "https://api.experientiallabs.ai/v1"
INSTITUTION_NAME = "Ramsheth Thakur College of Commerce & Science"
MAX_FILE_MB = "50"
The application uses the Experiential Labs OpenAI-compatible gateway. The model can be changed through EXPERIENTIAL_MODEL without changing the application code. Do not commit real API keys to GitHub.

Local run
pip install -r requirements.txt
streamlit run app.py
