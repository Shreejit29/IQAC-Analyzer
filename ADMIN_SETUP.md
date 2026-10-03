Admin Setup

Configure the IQAC Analyzer to use the Experiential Labs OpenAI-compatible gateway.

Streamlit Cloud Secrets

Add the following values under Settings → Secrets:

EXPLABS_API_KEY = "PASTE_YOUR_EXPERIENTIAL_LABS_API_KEY_HERE"
EXPERIENTIAL_MODEL = "deepseek-v4-flash-0731"
EXPERIENTIAL_BASE_URL = "https://api.experientiallabs.ai/v1"

The application reads these settings at startup.

Local installation

Create:

.streamlit/secrets.toml

with the same settings.

Never commit the real API key to GitHub.

Other settings

INSTITUTION_NAME and MAX_FILE_MB can also be configured in Streamlit secrets when required.

No separate photo-evidence configuration is required. The application handles document evidence during analysis.
