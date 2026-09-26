# Administrator Setup

## Gemini API key

Create/use the college's Gemini API key and put it only in Streamlit Secrets as `GEMINI_API_KEY`.

Recommended stable model setting for this release:

`GEMINI_MODEL = "gemini-3.8-flash"`

The model can be changed later without modifying the application code.

## What the app stores

There is no database. The application stores extracted records only in the current Streamlit session until the user clears the session or the session ends.

## What the app sends to Gemini

The uploaded PDF/DOCX/TXT is transmitted to Gemini because the application relies on multimodal document understanding. This is necessary for scanned IQAC reports containing images, handwriting, attendance sheets and photographs.

## Production checks before sharing the URL

- Test the app with the supplied RTCCS Rakhi Making Competition report.
- Test a report with no Programme Table.
- Test a report with multiple activities.
- Test a scanned/image-heavy report.
- Verify page references and participant counts.
- Verify that missing evidence is reported rather than invented.
- Download and open `IQAC_Master_Data.xlsx`.
