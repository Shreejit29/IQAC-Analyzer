from __future__ import annotations

import io
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .record_utils import normalize_record


class GeminiError(RuntimeError):
    pass


DOCUMENT_TYPES = [
    "Proposal", "Notice", "Programme/Schedule", "Invitation", "Attendance",
    "Event Report", "Photographs", "Geotagged Photographs", "Feedback",
    "Feedback Analysis", "News/Publicity", "Certificate", "Appreciation Letter",
    "Other Evidence",
]


class EvidenceItem(BaseModel):
    document: str = "Not Identified"
    status: str = "Not Identified"
    source_page: str = "Not Identified"


class Activity(BaseModel):
    academic_year: str = "Not Identified"
    activity_date: str = "Not Identified"
    activity_title: str = "Not Identified"
    activity_type: str = "Not Identified"
    category: str = "Not Identified"
    organizing_department_committee: str = "Not Identified"
    collaborating_agency: str = "Not Identified"
    resource_person: str = "Not Identified"
    venue: str = "Not Identified"
    participants: str = "Not Identified"
    objective: str = "Not Identified"
    activity_description: str = "Not Identified"
    outcome: str = "Not Identified"
    follow_up_action: str = "Not Identified"
    feedback: str = "Not Identified"
    naac_attribute: str = "Not Identified"
    naac_metric: str = "Not Identified"
    evidence: list[EvidenceItem] = Field(default_factory=list)
    source_page: str = "Not Identified"


class ReportAnalysis(BaseModel):
    academic_year: str = "Not Identified"
    activities: list[Activity] = Field(default_factory=list)


SYSTEM_PROMPT = f"""
You are an AI extractor for a college IQAC activity-report system.
Your ONLY job is to extract factual information from the supplied document.
Keep the output simple and practical. Do not score, audit, rank, predict, or invent facts.

ACTIVITY EXTRACTION
1. Identify EVERY DISTINCT activity actually described. One activity = one Activity object.
2. Use only information explicitly present in the document.
3. If a field is absent, return exactly "Not Identified".
4. Never invent an outcome, participant count, agency, date, person, or follow-up action.
5. Preserve names, dates, numbers and wording accurately.
6. Source Page must contain the PDF page number(s) where the activity is described.
7. Objective, Activity Description and Outcome must remain distinct.
8. Academic Year should be the explicitly stated academic year.
9. Do not create an activity merely because a supporting document is mentioned.

NAAC MAPPING
Select ONE best-fit Attribute and ONE best-fit Metric only, based on the activity itself.
Use the following reference catalog exactly:
1 Curriculum Design: 1.1-1.8
2 Faculty Resources: 2.1, 2.2, 2.3, 2.7
3 Infrastructure: 3.1-3.6
4 Financial Resources & Management: 4.1-4.6
5 Learning & Teaching: 5.1-5.8
6 Extended Curricular Engagements: 6.1-6.6
7 Governance and Administration: 7.1-7.10
8 Student Outcomes: 8.1-8.8
9 Research & Innovation Outcomes: 9.1-9.9
10 Sustainability Outcomes (Including Green Initiatives): 10.1-10.5
If the activity does not provide enough evidence for a defensible mapping, use "Not Identified".
This is an internal reference mapping, not an official accreditation decision.

DOCUMENT STATUS
For each of these document types, report Present only when the uploaded report actually contains or clearly identifies that evidence; otherwise report Absent.
Document types: {', '.join(DOCUMENT_TYPES)}
For Present, include a source page when identifiable. For Absent, do not guess a page.
Do not infer that a document exists just because the activity itself exists.
""".strip()

RECOVERY_PROMPT = """
The first extraction returned no activities. Re-read the supplied document and identify whether it contains a genuine college/IQAC activity report, notice, programme description, event report, or similar activity record.
If at least one genuine activity is described, return it even if many fields are missing.
Use "Not Identified" for missing fields. Do not invent anything.
""".strip()


def _client(api_key: str):
    try:
        from google import genai
        return genai.Client(api_key=api_key)
    except Exception as exc:
        raise GeminiError(f"Google GenAI SDK is not available: {exc}") from exc


def check_connection(api_key: str, model: str) -> tuple[bool, str]:
    if not api_key.strip():
        return False, "GEMINI_API_KEY is not configured."
    try:
        client = _client(api_key)
        client.models.get(model=model)
        return True, f"Gemini is ready ({model})."
    except Exception as exc:
        return False, f"Gemini connection/model check failed: {exc}"


def _is_transient(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(x in msg for x in (
        "429", "500", "502", "503", "504", "timeout", "timed out",
        "unavailable", "overloaded", "resource exhausted", "deadline exceeded",
    ))


def _extract_local_text(raw: bytes, filename: str) -> tuple[str, bool, str]:
    suffix = Path(filename).suffix.lower()
    try:
        if suffix == ".txt":
            text = raw.decode("utf-8", errors="replace").strip()
            return text, bool(text), "local-text"
        if suffix == ".docx":
            from docx import Document
            doc = Document(io.BytesIO(raw))
            chunks: list[str] = []
            for p in doc.paragraphs:
                if p.text.strip():
                    chunks.append(p.text.strip())
            for table in doc.tables:
                for row in table.rows:
                    cells = [c.text.strip() for c in row.cells]
                    if any(cells):
                        chunks.append(" | ".join(cells))
            text = "\n".join(chunks).strip()
            return text, len(text) >= 80, "local-docx"
        if suffix == ".pdf":
            import fitz
            doc = fitz.open(stream=raw, filetype="pdf")
            pages: list[str] = []
            total = 0
            useful_pages = 0
            for page_no, page in enumerate(doc, start=1):
                text = (page.get_text("text") or "").strip()
                if text:
                    useful_pages += 1
                total += len(text)
                pages.append(f"\n--- PDF PAGE {page_no} ---\n{text}")
            doc.close()
            result = "\n".join(pages).strip()
            page_count = max(1, len(pages))
            usable = total >= 500 and (useful_pages / page_count) >= 0.45
            return result, usable, "local-pdf-text" if usable else "pdf-visual-fallback"
    except Exception:
        return "", False, "extraction-failed"
    return "", False, "unsupported"


def _mime(filename: str) -> str:
    return {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".txt": "text/plain",
    }.get(Path(filename).suffix.lower(), "application/octet-stream")


def _generate(client: Any, model: str, contents: list[Any]) -> ReportAnalysis:
    try:
        response = client.models.generate_content(
            model=model,
            contents=contents,
            config={
                "temperature": 0.0,
                "response_mime_type": "application/json",
                "response_schema": ReportAnalysis,
            },
        )
    except Exception as exc:
        raise GeminiError(str(exc)) from exc
    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, ReportAnalysis):
        return parsed
    text = getattr(response, "text", "") or ""
    if not text:
        raise GeminiError("Gemini returned an empty response.")
    try:
        return ReportAnalysis.model_validate_json(text)
    except Exception as exc:
        raise GeminiError(f"Gemini returned invalid structured data: {exc}") from exc


def _analyze_once(raw: bytes, filename: str, model: str, api_key: str) -> ReportAnalysis:
    client = _client(api_key)
    text, usable, method = _extract_local_text(raw, filename)
    prompt = SYSTEM_PROMPT + f"\n\nSOURCE FILE: {filename}\nPROCESSING MODE: {method}"
    if usable:
        if len(text) > 160_000:
            text = text[:160_000] + "\n--- DOCUMENT TEXT TRUNCATED ---"
        return _generate(client, model, [prompt, "\nDOCUMENT TEXT:\n", text])

    suffix = Path(filename).suffix.lower()
    remote_file = None
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(raw)
            temp_path = tmp.name
        try:
            remote_file = client.files.upload(file=temp_path, config={"mime_type": _mime(filename)})
        except TypeError:
            remote_file = client.files.upload(file=temp_path)
        return _generate(client, model, [remote_file, prompt + "\nAnalyze the complete uploaded document."])
    except GeminiError:
        raise
    except Exception as exc:
        raise GeminiError(f"Gemini document analysis failed: {exc}") from exc
    finally:
        if remote_file is not None:
            try:
                client.files.delete(name=remote_file.name)
            except Exception:
                pass
        if temp_path:
            try:
                os.remove(temp_path)
            except OSError:
                pass


def _recover(raw: bytes, filename: str, model: str, api_key: str) -> ReportAnalysis:
    client = _client(api_key)
    text, usable, method = _extract_local_text(raw, filename)
    if usable:
        if len(text) > 160_000:
            text = text[:160_000]
        return _generate(client, model, [SYSTEM_PROMPT, RECOVERY_PROMPT, f"\nSOURCE FILE: {filename}\nPROCESSING MODE: {method}\n", text])
    return _analyze_once(raw, filename, model, api_key)


def _map_activity(activity: Activity, source_report: str, index: int, report_year: str) -> dict[str, str]:
    evidence_by_type = {item.document.strip().lower(): item for item in activity.evidence if item.document.strip()}
    present: list[str] = []
    absent: list[str] = []
    for doc_name in DOCUMENT_TYPES:
        item = evidence_by_type.get(doc_name.lower())
        if item and item.status.strip().lower() == "present":
            page = item.source_page if item.source_page != "Not Identified" else "Not Identified"
            present.append(f"{doc_name} (p. {page})" if page != "Not Identified" else doc_name)
        else:
            absent.append(doc_name)

    raw = {
        "Record ID": f"IQAC-{index:04d}",
        "Academic Year": activity.academic_year if activity.academic_year != "Not Identified" else report_year,
        "Activity Date": activity.activity_date,
        "Activity Title": activity.activity_title,
        "Activity Type": activity.activity_type,
        "Category": activity.category,
        "Organizing Department / Committee": activity.organizing_department_committee,
        "Collaborating Agency": activity.collaborating_agency,
        "Resource Person": activity.resource_person,
        "Venue": activity.venue,
        "Participants": activity.participants,
        "Objective": activity.objective,
        "Activity Description": activity.activity_description,
        "Outcome": activity.outcome,
        "Follow-up Action": activity.follow_up_action,
        "Feedback": activity.feedback,
        "NAAC Attribute": activity.naac_attribute,
        "NAAC Metric": activity.naac_metric,
        "Documents Present": "; ".join(present) if present else "None Identified",
        "Documents Absent": "; ".join(absent) if absent else "None Identified",
        "Source Report": source_report,
        "Source Page": activity.source_page,
    }
    return normalize_record(raw, source_report, index)


def analyze_report(raw: bytes, filename: str, model: str, api_key: str) -> tuple[list[dict[str, str]], dict[str, str]]:
    if not api_key.strip():
        raise GeminiError("GEMINI_API_KEY is not configured.")
    models = ["gemini-3.5-flash-lite"]
    if model and model not in models:
        models.append(model)
    last_error: Exception | None = None
    result: ReportAnalysis | None = None

    for selected_model in models:
        for attempt in range(2):
            try:
                result = _analyze_once(raw, filename, selected_model, api_key)
                break
            except Exception as exc:
                last_error = exc
                if not _is_transient(exc) or attempt == 1:
                    break
                time.sleep(1.5 * (2 ** attempt))
        if result is not None:
            break

    if result is None:
        raise GeminiError(f"Analysis failed for {filename}: {last_error}") from last_error

    if not result.activities:
        try:
            recovered = _recover(raw, filename, models[0], api_key)
            if recovered.activities:
                result = recovered
        except Exception:
            pass

    records = [_map_activity(a, filename, idx, result.academic_year) for idx, a in enumerate(result.activities, start=1)]

    if not records:
        text, usable, _ = _extract_local_text(raw, filename)
        if usable:
            title = _first_match(text, [r"(?:activity|title)\s*[:\-]\s*([^\n|]{5,160})"])
            date = _first_match(text, [r"(?:date|held on)\s*[:\-]\s*([^\n|]{5,80})"])
            if title:
                fallback = Activity(academic_year=result.academic_year, activity_title=title, activity_date=date or "Not Identified")
                records = [_map_activity(fallback, filename, 1, result.academic_year)]

    return records, {"Academic Year": result.academic_year, "Activities Detected": str(len(records))}


def _first_match(text: str, patterns: list[str]) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            value = " ".join(match.group(1).split()).strip(" :;-|")
            if value:
                return value
    return ""
