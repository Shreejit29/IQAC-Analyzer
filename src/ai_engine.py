from __future__ import annotations

import io
import os
import re
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .record_utils import normalize_record


class GeminiError(RuntimeError):
    pass


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
    source_page: str = "Not Identified"


class ReportAnalysis(BaseModel):
    academic_year: str = "Not Identified"
    activities: list[Activity] = Field(default_factory=list)


SYSTEM_PROMPT = """
You are an IQAC document analyzer for a college.

TASK:
Read the supplied document and extract genuine college activities into structured records.
This is an ANALYZER, not a report writer. Return concise factual data only.

RULES:
- Identify every distinct genuine activity described in the document.
- Do not create separate activities for notices, attendance sheets, circulars, certificates or supporting pages that belong to the same event.
- If the document describes one event, normally return one activity.
- Combine information about the same event from different pages.
- Never invent facts.
- If a field is not supported by the document, return exactly "Not Identified".
- Preserve names, dates, counts and terminology accurately.
- Do not copy long paragraphs. Summarize concisely.
- Use the actual event date, not document creation/submission date.
- Participants may include both group and count when stated.
- Outcome must be a reported outcome, not an assumed benefit.
- Follow-up Action only if explicitly stated.
- Feedback only if actual feedback or feedback collection is described.

NAAC MAPPING:
Select one conservative best-fit Attribute and Metric only when supported by the activity.
Use this internal reference:
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

Useful examples:
- Student technical/domain activities and competitions -> Attribute 6, Metric 6.1 when supported.
- Cultural activities -> 6.2.
- Student health/wellbeing -> 6.3.
- Value education/ethics -> 6.4.
- Sports -> 6.5.
- NSS/community outreach -> 6.6.
- IQAC/quality assurance -> 7.6.
- Explicit green/environment initiatives -> Attribute 10, Metric 10.4.

SOURCE PAGE:
- For PDFs, provide page number(s) supporting the activity, such as "2-4" or "2, 5".
- For DOCX/TXT, use "Not Identified" unless page information is explicitly available.

OUTPUT:
Return only the structured activity data requested by the schema.
"""


@lru_cache(maxsize=4)
def _client(api_key: str):
    try:
        from google import genai
        return genai.Client(api_key=api_key)
    except Exception as exc:
        raise GeminiError(f"Gemini SDK is not available: {exc}") from exc


def check_connection(api_key: str, model: str) -> tuple[bool, str]:
    if not api_key.strip():
        return False, "GEMINI_API_KEY is not configured."
    try:
        _client(api_key)
        return True, f"Gemini is configured ({model})."
    except Exception as exc:
        return False, f"Gemini connection check failed: {exc}"


def _extract_local_text(raw: bytes, filename: str) -> tuple[str, bool]:
    suffix = Path(filename).suffix.lower()
    try:
        if suffix == ".txt":
            text = raw.decode("utf-8", errors="replace").strip()
            return text, bool(text)

        if suffix == ".docx":
            from docx import Document
            doc = Document(io.BytesIO(raw))
            chunks = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
            for table in doc.tables:
                for row in table.rows:
                    cells = [c.text.strip() for c in row.cells]
                    if any(cells):
                        chunks.append(" | ".join(cells))
            text = "\n".join(chunks).strip()
            return text, bool(text)

    except Exception:
        return "", False

    return "", False


def _fallback_title_date(text: str) -> tuple[str, str]:
    title_patterns = [
        r"(?:activity\s+title|event\s+title|programme\s+title|title)\s*[:\-]\s*([^\n|]{5,180})",
    ]
    date_patterns = [
        r"(?:date|held on|conducted on|event date)\s*[:\-]\s*([^\n|]{5,100})",
    ]
    title = ""
    date = ""
    for pattern in title_patterns:
        m = re.search(pattern, text, re.I)
        if m:
            title = " ".join(m.group(1).split()).strip(" :;-|")
            break
    for pattern in date_patterns:
        m = re.search(pattern, text, re.I)
        if m:
            date = " ".join(m.group(1).split()).strip(" :;-|")
            break
    return title, date


def _generate(client: Any, model: str, contents: Any) -> ReportAnalysis:
    try:
        from google.genai import types
        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0,
                response_mime_type="application/json",
                response_schema=ReportAnalysis,
            ),
        )
    except Exception as exc:
        raise GeminiError(str(exc)) from exc

    try:
        parsed = response.parsed
        if parsed is not None:
            return ReportAnalysis.model_validate(parsed)
        text = response.text or ""
        return ReportAnalysis.model_validate_json(text)
    except Exception as exc:
        raise GeminiError(f"Gemini returned invalid structured data: {exc}") from exc


def _analyze_once(raw: bytes, filename: str, model: str, api_key: str) -> ReportAnalysis:
    client = _client(api_key)
    suffix = Path(filename).suffix.lower()

    # PDFs are sent natively to Gemini. No page rendering, OCR pipeline,
    # photo-evidence extraction, or multi-call vision fallback is used.
    if suffix == ".pdf":
        from google.genai import types
        prompt = (
            f"Analyze this PDF: {filename}\n"
            "Extract all genuine IQAC/college activities described in the complete PDF. "
            "Use PDF page numbers for source_page. Ignore decorative photographs and "
            "supporting-document details unless they help establish the activity."
        )
        part = types.Part.from_bytes(data=raw, mime_type="application/pdf")
        return _generate(client, model, [part, prompt])

    text, usable = _extract_local_text(raw, filename)
    if not usable:
        raise GeminiError(
            f"Could not extract readable text from {filename}. "
            "Please upload a text-based PDF, DOCX, or TXT file."
        )

    # Keep local text bounded for non-PDF files while retaining the beginning and end.
    if len(text) > 300_000:
        text = text[:240_000] + "\n--- MIDDLE OF DOCUMENT OMITTED LOCALLY ---\n" + text[-60_000:]

    prompt = (
        f"Analyze this document: {filename}\n"
        "Extract all genuine IQAC/college activities. "
        "This is the complete text extracted from the document:\n\n" + text
    )
    return _generate(client, model, prompt)


def _map_activity(activity: Activity, source_report: str, index: int, report_year: str) -> dict[str, str]:
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
        "Source Report": source_report,
        "Source Page": activity.source_page,
    }
    return normalize_record(raw, source_report, index)


def analyze_report(raw: bytes, filename: str, model: str, api_key: str) -> tuple[list[dict[str, str]], dict[str, str]]:
    if not api_key.strip():
        raise GeminiError("GEMINI_API_KEY is not configured.")

    selected_model = model or "gemini-3.5-flash-lite"
    last_error = None

    # Only retry transient server/rate-limit errors once. This avoids
    # duplicate calls for permanent errors such as invalid keys or models.
    for attempt in range(2):
        try:
            result = _analyze_once(raw, filename, selected_model, api_key)
            break
        except Exception as exc:
            last_error = exc
            msg = str(exc).lower()
            transient = any(x in msg for x in (
                "429", "500", "502", "503", "504",
                "resource exhausted", "temporarily unavailable", "timeout"
            ))
            if not transient or attempt == 1:
                raise GeminiError(f"Analysis failed for {filename}: {exc}") from exc
            time.sleep(2)
    else:
        raise GeminiError(f"Analysis failed for {filename}: {last_error}") from last_error

    records = [
        _map_activity(a, filename, idx, result.academic_year)
        for idx, a in enumerate(result.activities, start=1)
    ]

    # Small local fallback for unusually simple readable documents.
    if not records:
        text, usable = _extract_local_text(raw, filename)
        if usable:
            title, date = _fallback_title_date(text)
            if title:
                fallback = Activity(
                    academic_year=result.academic_year,
                    activity_title=title,
                    activity_date=date or "Not Identified",
                    activity_description="Extracted from the source document.",
                )
                records = [_map_activity(fallback, filename, 1, result.academic_year)]

    return records, {
        "Academic Year": result.academic_year,
        "Activities Detected": str(len(records)),
    }
