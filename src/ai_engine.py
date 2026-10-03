from __future__ import annotations

import io
import json
import re
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .record_utils import normalize_record


class GeminiError(RuntimeError):
    pass


# Documentary evidence categories that may be present inside the uploaded activity file.
# This does NOT mean a separate photo-evidence module is used.
DOCUMENT_TYPES = [
    "Proposal",
    "Notice",
    "Programme/Schedule",
    "Invitation",
    "Attendance",
    "Event Report",
    "Photographs",
    "Feedback",
    "Feedback Analysis",
    "News/Publicity",
    "Certificate",
    "Appreciation Letter",
    "Other Supporting Document",
]


class EvidenceItem(BaseModel):
    document: str = Field(default="Not Identified")
    status: str = Field(default="Not Identified")
    source_page: str = Field(default="Not Identified")


class Activity(BaseModel):
    academic_year: str = Field(default="Not Identified")
    activity_date: str = Field(default="Not Identified")
    activity_title: str = Field(default="Not Identified")
    activity_type: str = Field(default="Not Identified")
    category: str = Field(default="Not Identified")
    organizing_department_committee: str = Field(default="Not Identified")
    collaborating_agency: str = Field(default="Not Identified")
    resource_person: str = Field(default="Not Identified")
    venue: str = Field(default="Not Identified")
    participants: str = Field(default="Not Identified")
    objective: str = Field(default="Not Identified")
    activity_description: str = Field(default="Not Identified")
    outcome: str = Field(default="Not Identified")
    follow_up_action: str = Field(default="Not Identified")
    feedback: str = Field(default="Not Identified")
    naac_attribute: str = Field(default="Not Identified")
    naac_metric: str = Field(default="Not Identified")
    evidence: list[EvidenceItem] = Field(default_factory=list)
    source_page: str = Field(default="Not Identified")


class ReportAnalysis(BaseModel):
    academic_year: str = Field(default="Not Identified")
    activities: list[Activity] = Field(default_factory=list)


SYSTEM_PROMPT = f"""
You are the document-analysis engine for a college IQAC Analyzer.

SCOPE
- This is an IQAC ANALYZER, not an IQAC report generator.
- Extract facts from the supplied document and return structured data only.
- Do not write a new report.
- Do not invent facts.
- If a field is genuinely unsupported, return exactly "Not Identified".
- Treat only the supplied document as evidence. Do not use general knowledge to fill missing facts.

ACTIVITY DETECTION
1. Identify each distinct genuine activity described in the supplied document.
2. One genuine activity = one Activity object.
3. Do not create separate activities merely because the file contains a notice, attendance sheet, feedback page, photographs, certificate, or other evidence belonging to the same activity.
4. If the document describes several unrelated activities, create one object per activity.
5. Consolidate information across pages that clearly belongs to the same activity.

FIELD RULES
Academic Year: use the stated academic/session year.
Activity Date: use the actual event date, not approval/submission/publication dates.
Activity Title: use the formal title when available.
Activity Type: identify the event type from context.
Category: use the stated category or a conservative contextual category.
Organizing Department / Committee: identify the organizer.
Collaborating Agency: identify actual partner/collaborator, not merely the organizer.
Resource Person: identify named speakers/experts/trainers/guests.
Venue: identify the actual event location.
Participants: preserve supported groups/counts exactly.
Objective: extract stated aims/purposes, not outcomes.
Activity Description: concise factual summary.
Outcome: extract reported results/impact only; do not infer.
Follow-up Action: extract explicit next steps only.
Feedback: extract actual feedback information, or "Feedback collected" only when collection is explicitly stated.
Source Page: give the PDF page number/range supporting the activity. For DOCX/TXT, use "Not Identified" unless the source itself gives page numbers.

NAAC MAPPING
Select one best-fit Attribute and one best-fit Metric conservatively from this internal catalog:
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

Useful conservative examples:
- Student technical/domain competitions and similar extension activities -> Attribute 6, often 6.1 when supported.
- Cultural activities -> 6.2.
- Student wellbeing/health activities -> 6.3.
- Value education/ethics -> 6.4.
- Sports -> 6.5.
- Community service/NSS/UBA/outreach -> 6.6.
- IQAC/quality assurance -> 7.6.
- Explicit environmental/green initiatives -> Attribute 10, typically 10.4.
These mappings are internal references, not an official accreditation determination.

DOCUMENT PRESENCE
Return exactly one EvidenceItem for every type, in this exact order:
{', '.join(DOCUMENT_TYPES)}

Status must be exactly one of: Present, Absent, Not Identified.
- Present: the uploaded document visibly/explicitly contains that evidence.
- Absent: the uploaded document has been sufficiently checked and that evidence is not present.
- Not Identified: the file is ambiguous/unreadable or does not allow a reliable determination.
- Never infer that evidence exists because an activity normally has it.
- "Attendance will be taken" does not make Attendance Present.
- An attendance sheet/table makes Attendance Present.
- Visible photographs embedded in the supplied document make Photographs Present.
- Do not separately process or require photo uploads.
- If a section explicitly says a document is not attached/not available/NA, mark Absent.
- For Present, source_page must show where it appears. For Absent and Not Identified use "Not Identified".

OUTPUT QUALITY
- Keep fields concise and factual.
- Preserve names, dates, counts and titles.
- Do not copy large paragraphs.
- Do not invent.
""".strip()


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
        client = _client(api_key)
        model_ids: set[str] = set()
        try:
            for item in client.models.list():
                model_name = getattr(item, "name", "") or getattr(item, "id", "")
                model_ids.add(str(model_name).replace("models/", ""))
        except Exception:
            # A models-list failure should not prevent actual document analysis.
            pass
        if model_ids and model not in model_ids:
            return False, f"Gemini model '{model}' is not available for this account."
        return True, f"Gemini is configured ({model})."
    except Exception as exc:
        return False, f"Gemini connection/model check failed: {exc}"


def _is_retryable(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(
        token in msg
        for token in (
            "429",
            "500",
            "502",
            "503",
            "504",
            "timeout",
            "timed out",
            "unavailable",
            "resource exhausted",
        )
    )


def _extract_local_text(raw: bytes, filename: str) -> tuple[str, bool]:
    suffix = Path(filename).suffix.lower()
    try:
        if suffix == ".txt":
            text = raw.decode("utf-8", errors="replace").strip()
            return text, bool(text)

        if suffix == ".docx":
            from docx import Document

            doc = Document(io.BytesIO(raw))
            chunks: list[str] = []
            for paragraph in doc.paragraphs:
                if paragraph.text.strip():
                    chunks.append(paragraph.text.strip())
            for table in doc.tables:
                for row in table.rows:
                    cells = [cell.text.strip() for cell in row.cells]
                    if any(cells):
                        chunks.append(" | ".join(cells))
            text = "\n".join(chunks).strip()
            return text, len(text) >= 80
    except Exception:
        return "", False

    return "", False


def _generate(client: Any, model: str, contents: Any) -> ReportAnalysis:
    """
    Generate structured output using the Pydantic model directly.

    The previous implementation manually passed a JSON-schema dictionary to
    response_schema. That caused Gemini REST payload errors around
    `additional_properties` with the google-genai SDK. The SDK officially
    supports passing a Pydantic class directly as response_schema, so we use
    ReportAnalysis here and avoid hand-built schema translation entirely.
    """
    try:
        from google.genai import types

        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0,
                thinking_config=types.ThinkingConfig(thinking_level="minimal"),
                response_mime_type="application/json",
                response_schema=ReportAnalysis,
            ),
        )
    except Exception as exc:
        raise GeminiError(str(exc)) from exc

    parsed = getattr(response, "parsed", None)
    if parsed is not None:
        try:
            if isinstance(parsed, ReportAnalysis):
                return parsed
            return ReportAnalysis.model_validate(parsed)
        except Exception:
            pass

    text = getattr(response, "text", "") or ""
    if not text:
        raise GeminiError("Gemini returned an empty response.")

    try:
        return ReportAnalysis.model_validate_json(text)
    except Exception:
        try:
            return ReportAnalysis.model_validate(json.loads(text))
        except Exception as exc:
            raise GeminiError(f"Gemini returned invalid structured data: {exc}") from exc


def _normalize_document_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _map_evidence(activity: Activity) -> tuple[str, str]:
    evidence_by_name = {
        _normalize_document_name(item.document): item
        for item in activity.evidence
        if item.document.strip()
    }

    present: list[str] = []
    absent: list[str] = []

    for document_name in DOCUMENT_TYPES:
        item = evidence_by_name.get(_normalize_document_name(document_name))
        if not item:
            absent.append(document_name)
            continue

        status = item.status.strip().lower()
        if status == "present":
            page = item.source_page.strip()
            if page and page.lower() != "not identified":
                present.append(f"{document_name} (p. {page})")
            else:
                present.append(document_name)
        elif status == "absent":
            absent.append(document_name)

    return (
        "; ".join(present) if present else "None Identified",
        "; ".join(absent) if absent else "None Identified",
    )


def _map_activity(
    activity: Activity,
    source_report: str,
    index: int,
    academic_year: str,
) -> dict[str, str]:
    present, absent = _map_evidence(activity)
    data = activity.model_dump()
    effective_year = data.get("academic_year") or academic_year or "Not Identified"

    field_map = {
        "academic_year": "Academic Year",
        "activity_date": "Activity Date",
        "activity_title": "Activity Title",
        "activity_type": "Activity Type",
        "category": "Category",
        "organizing_department_committee": "Organizing Department / Committee",
        "collaborating_agency": "Collaborating Agency",
        "resource_person": "Resource Person",
        "venue": "Venue",
        "participants": "Participants",
        "objective": "Objective",
        "activity_description": "Activity Description",
        "outcome": "Outcome",
        "follow_up_action": "Follow-up Action",
        "feedback": "Feedback",
        "naac_attribute": "NAAC Attribute",
        "naac_metric": "NAAC Metric",
        "source_page": "Source Page",
    }

    flat: dict[str, Any] = {
        target: data.get(source, "Not Identified")
        for source, target in field_map.items()
    }
    flat["Academic Year"] = effective_year
    flat["Documents Present"] = present
    flat["Documents Absent"] = absent
    flat["Source Report"] = source_report
    flat["Record ID"] = f"IQAC-{index:04d}"

    return normalize_record(flat, source_report, index)


def _analysis_prompt() -> str:
    return (
        "Analyze this complete IQAC source document. Identify every distinct genuine activity, "
        "extract the required activity fields, and complete the document-presence checklist. "
        "Return only the required structured JSON."
    )


def _generate_with_retry(client: Any, model: str, contents: Any) -> ReportAnalysis:
    last_error: Exception | None = None
    for attempt, delay in enumerate((0, 2, 5), start=1):
        if delay:
            time.sleep(delay)
        try:
            return _generate(client, model, contents)
        except Exception as exc:
            last_error = exc
            if not _is_retryable(exc) or attempt == 3:
                break
    raise GeminiError(str(last_error) if last_error else "Gemini analysis failed.")


def analyze_report(
    raw: bytes,
    filename: str,
    model: str,
    api_key: str,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    if not api_key.strip():
        raise GeminiError("GEMINI_API_KEY is not configured.")

    client = _client(api_key)
    suffix = Path(filename).suffix.lower()
    prompt = _analysis_prompt()

    try:
        if suffix == ".pdf":
            # Inline PDF input avoids the extra Files API upload round-trip for
            # one-shot analysis. Gemini supports inline PDFs up to 50 MB.
            from google.genai import types

            pdf_part = types.Part.from_bytes(
                data=raw,
                mime_type="application/pdf",
            )
            result = _generate_with_retry(client, model, [prompt, pdf_part])
        else:
            text, usable = _extract_local_text(raw, filename)
            if not usable:
                raise GeminiError(
                    f"Could not extract usable text from {filename}. Please use a readable PDF/DOCX/TXT file."
                )
            result = _generate_with_retry(client, model, [prompt, text])
    except GeminiError as exc:
        raise GeminiError(f"Analysis failed for {filename}: {exc}") from exc
    except Exception as exc:
        raise GeminiError(f"Analysis failed for {filename}: {exc}") from exc

    records = [
        _map_activity(activity, filename, index, result.academic_year)
        for index, activity in enumerate(result.activities, start=1)
    ]

    return records, {
        "Academic Year": result.academic_year,
        "Activities Detected": str(len(records)),
    }
