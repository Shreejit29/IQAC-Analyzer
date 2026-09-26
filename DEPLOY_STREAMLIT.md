# Streamlit deployment

## 1. Put the project on GitHub

Create a repository and upload all project files.

## 2. Create the Streamlit app

On Streamlit Community Cloud, choose the GitHub repository and set the main file to:

`app.py`

## 3. Configure Secrets

In the Streamlit app settings, open **Secrets** and add:

```toml
GEMINI_API_KEY = "YOUR_REAL_GEMINI_API_KEY"
GEMINI_MODEL = "gemini-3.8-flash"
INSTITUTION_NAME = "Ramsheth Thakur College of Commerce & Science"
MAX_FILE_MB = "50"
```

Never put the real API key in GitHub or inside `app.py`.

## 4. Requirements

Streamlit will install packages from `requirements.txt`.

## 5. Staff instructions

Give staff only the deployed app URL and `STAFF_INSTRUCTIONS.md`.

## Security / privacy

The app has no database and no permanent document-storage layer. Streamlit's runtime is temporary, but uploaded report contents are transmitted to Gemini for analysis. The application does not intentionally log report contents. Gemini Files are deleted after analysis when possible and otherwise expire automatically according to Google's API retention behavior.
