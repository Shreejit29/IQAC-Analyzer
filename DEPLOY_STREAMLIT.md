# Streamlit deployment

## 1. Put the project on GitHub

Create a repository and upload all project files.

## 2. Create the Streamlit app

On Streamlit Community Cloud, choose the GitHub repository and set the main file to:

`app.py`

## 3. Configure Secrets

In the Streamlit app settings, open **Secrets** and add:

```toml
GROQ_API_KEY = "YOUR_REAL_GROQ_API_KEY"
GROQ_MODEL = "qwen/qwen3.8-27b"
INSTITUTION_NAME = "Ramsheth Thakur College of Commerce & Science"
MAX_FILE_MB = "50"
```

Never put the real API key in GitHub or inside `app.py`.

## 4. Requirements

Streamlit will install packages from `requirements.txt`.

## 5. Staff instructions

Give staff only the deployed app URL and `STAFF_INSTRUCTIONS.md`.

## Security / privacy

The app has no database and no permanent document-storage layer. Streamlit's runtime is temporary. Readable document text and, when needed, rendered scanned-PDF page images are sent to Groq for AI analysis. The application does not intentionally log report contents.
