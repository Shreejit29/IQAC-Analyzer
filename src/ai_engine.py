from __future__ import annotations

import io
import json
import os
import re
import time
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from .record_utils import normalize_record


class GeminiError(RuntimeError):
    """User-facing error raised for Gemini configuration/API failures."""


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
You are the primary information-extraction engine for a college IQAC document system.
Read and understand the supplied report, including headings, paragraphs, tables, notices,
schedules, attendance sections, event reports, conclusions, feedback sections, captions and
evidence lists. Return structured activity records only.

CORE PRINCIPLE
- Extract facts from the supplied document only.
- Map information by meaning, not only by field labels.
- Do not invent names, numbers, dates, outcomes, agencies, locations or actions.
- If a field is genuinely unsupported, use exactly "Not Identified".
- Preserve actual names, dates, numbers and terminology.
- Do not create separate activities for notices, attendance sheets, photos, feedback pages,
  certificates or other evidence belonging to the same event.
- If the report contains several unrelated events, create one activity for each.

FIELD RULES
Academic Year: use the explicitly stated academic year/session/reporting year.
Activity Date: use the actual event date, not submission/publication/approval dates.
Activity Title: prefer the formal event/activity title from headings, notices, schedules or reports.
Activity Type: classify conservatively (workshop, seminar, competition, awareness programme,
field visit, training, lecture, campaign, drive, celebration, sports, cultural, outreach, etc.).
Category: use the report's stated category; otherwise infer conservatively from clear context.
Organizing Department / Committee: identify the actual organizing unit.
Collaborating Agency: identify partners/co-organizers/external agencies; do not duplicate the
college organizing unit unless it is explicitly a collaborator.
Resource Person: identify speakers, experts, trainers, guests, judges or facilitators.
Venue: identify the actual location of the activity.
Participants: preserve counts and groups when explicitly supported; do not calculate unsupported totals.
Objective: extract stated aims/purposes, not outcomes.
Activity Description: concise factual synthesis of what actually happened.
Outcome: extract reported results, impact, learning or benefits; never invent them.
Follow-up Action: extract explicit future actions, recommendations or continuation plans.
Feedback: extract actual feedback information; if only collection is stated, say "Feedback collected".
Source Page: use PDF page numbers supporting the activity. For DOCX/TXT use Not Identified unless
page numbers are explicitly available.

NAAC MAPPING
Select ONE best-fit Attribute and ONE best-fit Metric per activity using this internal reference:
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
Useful internal examples: technical/student extension activities -> 6.1; cultural -> 6.2;
wellbeing/health -> 6.3; value education/ethics -> 6.4; sports -> 6.5;
community service/NSS/UBA/outreach -> 6.6; IQAC/quality assurance -> 7.6;
explicit environmental/green initiatives -> 10.4. These are internal reference mappings,
not an official accreditation determination.

DOCUMENT EVIDENCE
Return exactly one EvidenceItem for EVERY document type below, in this exact order:
{', '.join(DOCUMENT_TYPES)}
Status rules:
- Present = the supplied report actually contains or clearly identifies the evidence.
- Absent = the report has been sufficiently checked and the evidence is not present.
- Not Identified = ambiguous, unreadable, or impossible to determine reliably.
- Never infer evidence merely because an activity exists.
- For Present, give PDF page where possible.
- For Absent/Not Identified, source_page must be "Not Identified".
- If explicitly marked NA/not available/not attached, treat it as Absent.
"""

RECOVERY_PROMPT = """
Re-read the supplied document and perform a conservative recovery pass. Return only the
structured IQAC extraction. Merge evidence belonging to the same activity. Do not invent facts.
"""


def _client(api_key: str):
    if not api_key.strip():
        raise GeminiError("GEMINI_API_KEY is not configured.")
    return genai.Client(api_key=api_key.strip())


def _extract_local_text(raw: bytes, filename: str) -> tuple[str, bool, str]:
    suffix = Path(filename).suffix.lower()
    try:
        if suffix == ".txt":
            text = raw.decode("utf-8", errors="ignore").strip()
            return text, len(text) >= 80, "local-text"
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
            page_count = max(1, len(pages))
            doc.close()
            result = "\n".join(pages).strip()
            usable = total >= 500 and (useful_pages / page_count) >= 0.45
            return result, usable, "local-pdf-text" if usable else "gemini-pdf"
    except Exception:
        return "", False, "extraction-failed"
    return "", False, "unsupported"


def _strict_schema() -> dict[str, Any]:
    return ReportAnalysis.model_json_schema()


def _generate(client: Any, model: str, contents: Any, recovery: bool = False) -> ReportAnalysis:
    try:
        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=RECOVERY_PROMPT if recovery else SYSTEM_PROMPT,
                temperature=0,
                max_output_tokens=8192,
                response_mime_type="application/json",
                response_schema=_strict_schema(),
            ),
        )
    except Exception as exc:
        raise GeminiError(_friendly_error(exc)) from exc

    text = getattr(response, "text", None) or ""
    if not text:
        raise GeminiError("Gemini returned an empty response.")
    try:
        return ReportAnalysis.model_validate_json(text)
    except Exception as exc:
        try:
            return ReportAnalysis.model_validate(json.loads(text))
        except Exception as inner:
            raise GeminiError(f"Gemini returned invalid structured JSON: {inner}") from exc


def _wait_until_active(client: Any, uploaded_file: Any, timeout: int = 120) -> Any:
    state = getattr(uploaded_file, "state", None)
    state_name = getattr(state, "name", str(state)) if state is not None else "ACTIVE"
    started = time.time()
    current = uploaded_file
    while state_name == "PROCESSING" and time.time() - started < timeout:
        time.sleep(1.5)
        current = client.files.get(name=current.name)
        state = getattr(current, "state", None)
        state_name = getattr(state, "name", str(state)) if state is not None else "ACTIVE"
    if state_name == "FAILED":
        raise GeminiError("Gemini could not process the uploaded document.")
    if state_name == "PROCESSING":
        raise GeminiError("Gemini file processing timed out. Please retry the document.")
    return current


def _analyze_pdf(client: Any, model: str, raw: bytes, filename: str) -> ReportAnalysis:
    uploaded = None
    try:
        uploaded = client.files.upload(
            file=io.BytesIO(raw),
            config={"display_name": filename, "mime_type": "application/pdf"},
        )
        uploaded = _wait_until_active(client, uploaded)
        prompt = (
            f"SOURCE FILE: {filename}\n\n"
            "Analyze the complete PDF. Identify every distinct IQAC activity and consolidate all "
            "supporting evidence belonging to each activity. Pay attention to tables, images, "
            "captions, attendance, schedules and page numbers. Return only the required JSON structure."
        )
        return _generate(client, model, [uploaded, prompt])
    finally:
        if uploaded is not None:
            try:
                client.files.delete(name=uploaded.name)
            except Exception:
                pass


def _analyze_text(client: Any, model: str, text: str, filename: str) -> ReportAnalysis:
    if len(text) > 240_000:
        text = text[:240_000] + "\n--- DOCUMENT TEXT TRUNCATED ---"
    prompt = (
        f"SOURCE FILE: {filename}\n\n"
        "Analyze the complete extracted document text below. Identify every distinct IQAC activity "
        "and consolidate supporting evidence belonging to each activity.\n\nDOCUMENT TEXT:\n" + text
    )
    return _generate(client, model, prompt)


def _analyze_once(raw: bytes, filename: str, model: str, api_key: str) -> ReportAnalysis:
    client = _client(api_key)
    suffix = Path(filename).suffix.lower()
    text, usable, method = _extract_local_text(raw, filename)
    if suffix == ".pdf":
        # Gemini's native PDF understanding is preferable because it can interpret both text
        # and visual evidence in the same request. This is especially useful for scanned IQAC reports.
        return _analyze_pdf(client, model, raw, filename)
    if usable:
        return _analyze_text(client, model, text, filename)
    raise GeminiError(f"Could not extract usable content from {filename}.")


def _recover(raw: bytes, filename: str, model: str, api_key: str) -> ReportAnalysis:
    client = _client(api_key)
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        uploaded = None
        try:
            uploaded = client.files.upload(
                file=io.BytesIO(raw),
                config={"display_name": filename, "mime_type": "application/pdf"},
            )
            uploaded = _wait_until_active(client, uploaded)
            return _generate(
                client,
                model,
                [uploaded, f"SOURCE FILE: {filename}\n{RECOVERY_PROMPT}"],
                recovery=True,
            )
        finally:
            if uploaded is not None:
                try:
                    client.files.delete(name=uploaded.name)
                except Exception:
                    pass
    text, usable, _ = _extract_local_text(raw, filename)
    if usable:
        return _generate(client, model, f"SOURCE FILE: {filename}\n{RECOVERY_PROMPT}\n{text}", recovery=True)
    return ReportAnalysis()


def _norm_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _merge_activities(old: Activity, new: Activity) -> Activity:
    data = old.model_dump()

    def choose(a: str, b: str) -> str:
        if (not a or a == "Not Identified") and b and b != "Not Identified":
            return b
        return a or "Not Identified"

    for field in data:
        if field != "evidence":
            data[field] = choose(str(data[field]), str(getattr(new, field)))

    evidence: dict[str, EvidenceItem] = {
        _norm_key(e.document): e for e in old.evidence if e.document.strip()
    }
    rank = {"present": 3, "not identified": 2, "absent": 1}
    for item in new.evidence:
        key = _norm_key(item.document)
        if not key:
            continue
        if key not in evidence or rank.get(item.status.lower(), 2) > rank.get(evidence[key].status.lower(), 2):
            evidence[key] = item
        elif evidence[key].source_page == "Not Identified" and item.source_page != "Not Identified":
            evidence[key] = item
    data["evidence"] = list(evidence.values())
    return Activity.model_validate(data)


def _merge_results(results: list[ReportAnalysis]) -> ReportAnalysis:
    if not results:
        return ReportAnalysis()
    merged: list[Activity] = []
    academic_year = next(
        (r.academic_year for r in results if r.academic_year != "Not Identified"),
        "Not Identified",
    )

    def norm(v: str) -> str:
        return _norm_key(v)

    def similar(a: Activity, b: Activity) -> bool:
        ta, tb = norm(a.activity_title), norm(b.activity_title)
        da, db = norm(a.activity_date), norm(b.activity_date)
        if ta and tb and ta != "not identified" and tb != "not identified":
            return (ta == tb or ta in tb or tb in ta) and (
                da == db or "not identified" in (da, db) or not da or not db
            )
        return False

    for result in results:
        for activity in result.activities:
            hit = next((i for i, existing in enumerate(merged) if similar(existing, activity)), None)
            if hit is None:
                merged.append(activity)
            else:
                merged[hit] = _merge_activities(merged[hit], activity)
    return ReportAnalysis(academic_year=academic_year, activities=merged)


def _map_activity(activity: Activity, source_report: str, index: int, report_year: str) -> dict[str, str]:
    evidence_by_type = {_norm_key(item.document): item for item in activity.evidence if item.document.strip()}
    present: list[str] = []
    absent: list[str] = []
    not_identified: list[str] = []

    for doc_name in DOCUMENT_TYPES:
        item = evidence_by_type.get(_norm_key(doc_name))
        status = item.status.strip().lower() if item else "not identified"
        if status == "present":
            page = item.source_page if item.source_page and item.source_page != "Not Identified" else "Not Identified"
            present.append(f"{doc_name} (p. {page})" if page != "Not Identified" else doc_name)
        elif status == "absent":
            absent.append(doc_name)
        else:
            not_identified.append(doc_name)

    absent_display = "; ".join(absent) if absent else "None Identified"
    if not_identified:
        absent_display += " | Not Identified: " + "; ".join(not_identified)

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
        "Documents Absent": absent_display,
        "Source Report": source_report,
        "Source Page": activity.source_page,
    }
    return normalize_record(raw, source_report, index)


def _is_retryable(message: str) -> bool:
    text = message.lower()
    return any(token in text for token in ("429", "503", "500", "temporarily unavailable", "deadline exceeded"))


def _friendly_error(exc: Exception) -> str:
    text = str(exc)
    low = text.lower()
    if "api key" in low or "unauthenticated" in low or "invalid_argument" in low and "key" in low:
        return "Gemini API key is invalid. Create a Gemini API key in Google AI Studio and set GEMINI_API_KEY in Streamlit Secrets."
    if "quota" in low or "resource_exhausted" in low or "429" in low:
        return "Gemini free-tier quota/rate limit was reached. Wait for the quota window to reset or use another eligible Gemini model/project."
    if "413" in low or "too large" in low:
        return "The document/request is too large for the current Gemini request. Try a smaller file or split the report."
    return text


def analyze_report(raw: bytes, filename: str, model: str, api_key: str) -> tuple[list[dict[str, str]], dict[str, str]]:
    if not api_key.strip():
        raise GeminiError("GEMINI_API_KEY is not configured.")

    selected_model = model or "gemini-3.5-flash-lite"
    last_error: Exception | None = None
    result: ReportAnalysis | None = None

    for attempt in range(2):
        try:
            result = _analyze_once(raw, filename, selected_model, api_key)
            break
        except GeminiError as exc:
            last_error = exc
            if attempt == 1 or not _is_retryable(str(exc)):
                break
            time.sleep(2.0 * (2 ** attempt))
        except Exception as exc:
            last_error = exc
            if attempt == 1 or not _is_retryable(str(exc)):
                break
            time.sleep(2.0 * (2 ** attempt))

    if result is None:
        raise GeminiError(f"Analysis failed for {filename}: {last_error}") from last_error

    if not result.activities:
        try:
            recovered = _recover(raw, filename, selected_model, api_key)
            if recovered.activities:
                result = recovered
        except Exception:
            pass

    records = [
        _map_activity(a, filename, idx, result.academic_year)
        for idx, a in enumerate(result.activities, start=1)
    ]

    if not records:
        text, usable, _ = _extract_local_text(raw, filename)
        if usable:
            title = _first_match(text, [
                r"(?:activity\s+title|event\s+title|programme\s+title|title|activity)\s*[:\-]\s*([^\n|]{5,180})"
            ])
            date = _first_match(text, [
                r"(?:date|held on|conducted on|event date)\s*[:\-]\s*([^\n|]{5,100})"
            ])
            if title:
                fallback = Activity(
                    academic_year=result.academic_year,
                    activity_title=title,
                    activity_date=date or "Not Identified",
                    activity_description="Extracted from readable report text after AI recovery.",
                )
                records = [_map_activity(fallback, filename, 1, result.academic_year)]

    return records, {
        "Academic Year": result.academic_year,
        "Activities Detected": str(len(records)),
    }


def _first_match(text: str, patterns: list[str]) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            value = " ".join(match.group(1).split()).strip(" :;-|")
            if value:
                return value
    return ""
