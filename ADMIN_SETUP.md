# Admin setup

## Groq API key
Create a Groq API key and put it only in Streamlit Secrets as `GROQ_API_KEY`.

Recommended model:

```toml
GROQ_MODEL = "qwen/qwen3.8-27b"
```

The app is written so the model can be changed later without changing the code.

## What the app sends to Groq

Readable PDF/DOCX/TXT files are extracted locally first, so the normal path sends text rather than the original document file.

For scanned/image-only PDFs, the app renders pages locally and sends up to three page images per Groq request using the configured multimodal model. This keeps the app compatible with Streamlit Community Cloud while avoiding Gemini-specific file uploads.

Never put the real API key in GitHub or inside `app.py`.
