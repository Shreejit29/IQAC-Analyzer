Streamlit Deployment

1. Push the repository to GitHub

Push the complete IQAC Analyzer repository to your GitHub account.

2. Create the Streamlit Cloud app

Create a new Streamlit app and select:

Main file: app.py

Repository: your IQAC Analyzer repository

3. Add Streamlit Secrets

Open Settings → Secrets and add:

EXPLABS_API_KEY = "PASTE_YOUR_EXPERIENTIAL_LABS_API_KEY_HERE"
EXPERIENTIAL_MODEL = "deepseek-v4-flash-0731"
EXPERIENTIAL_BASE_URL = "https://api.experientiallabs.ai/v1"
INSTITUTION_NAME = "Ramsheth Thakur College of Commerce & Science, Kharghar"
MAX_FILE_MB = "50"

4. Deploy

Deploy/redeploy the application. The app will use the Experiential Labs OpenAI-compatible API endpoint for AI analysis.

5. Local testing

For local Streamlit testing, create:

.streamlit/secrets.toml

using the same keys above. Do not commit this file to GitHub when it contains a real API key.
