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
You are the primary information-extraction engine for a college IQAC document system.
Your task is NOT simple keyword filling. Read and understand the COMPLETE supplied report, including headings, paragraphs, tables, notices, schedules, attendance sections, event reports, conclusions, feedback sections, captions and evidence lists. Then convert the information into structured activity records.

CORE PRINCIPLE
Extract intelligently from context while remaining factual.
- If the document clearly states something but does not use the exact field label, map it to the appropriate field.
- Do NOT require labels such as 'Venue:', 'Participants:' or 'Objective:' when the meaning is clear from surrounding text.
- You may combine closely related statements from different parts of the SAME report when they clearly refer to the same activity.
- Do not use general world knowledge to fill a factual field.
- Do not invent names, numbers, dates, outcomes, agencies, locations or actions.
- If the report truly does not support a field, use exactly "Not Identified".
- Preserve the document's actual names, dates, numbers and terminology.

ACTIVITY DETECTION
1. Identify every distinct genuine activity in the report.
2. One distinct activity = one Activity object.
3. Do not create separate activities for a notice, attendance sheet, photographs, feedback page or other evidence belonging to the same event.
4. If one report contains several unrelated events, create one object for each event.
5. If a report has a title/header and then detailed sections for one event, consolidate them into one record.
6. Supporting documents are evidence for an activity, not separate activities.

FIELD EXTRACTION — USE CONTEXT, NOT ONLY LABELS
Academic Year:
- Use the explicitly stated academic year, session or reporting year.
- A report-level academic year may be applied to activities when it clearly governs the whole report.

Activity Date:
- Extract the actual event/activity date.
- Do not confuse publication date, submission date or approval date with event date.
- If multiple dates are present, select the date that clearly belongs to the activity.

Activity Title:
- Prefer the formal event/activity title from the heading, title block, notice, schedule or event report.
- Do not replace a specific title with a generic category.

Activity Type:
- Identify the type from the report context, such as workshop, seminar, competition, awareness programme, extension activity, field visit, training, lecture, campaign, drive, celebration, sports activity, cultural activity, outreach activity, etc.

Category:
- Capture the report's own category/type when explicitly stated.
- If a clear category is evident from the activity description, map it conservatively.

Organizing Department / Committee:
- Look for department, committee, cell, NSS, student association, club, IQAC, NCC, examination committee, etc.
- Also recognize phrases such as 'organized by', 'conducted by', 'under the guidance of', 'through', 'coordinated by', when they clearly identify the organizing unit.

Collaborating Agency:
- Extract external/internal partners, institutions, NGOs, companies, government bodies, associations or agencies described as collaborators, partners, co-organizers or institutions in association with the activity.
- Do not put the college's own organizing department here unless it is explicitly a collaborating organization.

Resource Person:
- Extract speaker, expert, trainer, guest, chief guest, invited resource person, facilitator, judge or other named person who delivered/contributed to the activity.
- If several clearly relevant persons exist, list them concisely.
- A coordinator should not automatically be treated as a resource person.

Venue:
- Extract the actual place/location where the activity occurred.
- Recognize 'held at', 'conducted at', 'venue', 'place', 'location', room/building names and outdoor locations.

Participants:
- Extract participant groups and counts from the whole report.
- Use attendance counts, volunteer counts, registration counts, participant statements and tables when they clearly refer to the activity.
- Preserve both count and group, e.g. '72 NSS Volunteers'.
- Do not calculate a number unless the report itself provides enough information to make the total explicit.

Objective:
- Extract stated aims, purposes, objectives, intended goals or reasons for conducting the activity.
- Recognize objective statements even when they occur in prose rather than under an 'Objective' heading.
- Keep objectives separate from what actually happened and from reported outcomes.

Activity Description:
- Summarize what was actually conducted, using only information from the report.
- Include important programme components, methodology, major activities, sessions or sequence when clearly described.
- This field can be a concise synthesis of multiple factual statements from the report.

Outcome:
- Extract reported results, impact, benefits, achievements, learning, awareness created or other consequences explicitly stated in the report.
- Do not turn objectives into outcomes.
- Do not invent an outcome simply because an activity normally would have one.

Follow-up Action:
- Extract explicit future actions, continuation plans, recommendations, next steps, monitoring, subsequent programmes or commitments.
- If the report only describes the completed event, use Not Identified.

Feedback:
- Extract actual participant/stakeholder feedback information, feedback summary or feedback-related findings.
- If the report states that feedback was collected but does not give its content, say 'Feedback collected' rather than inventing comments.
- Do not confuse a feedback form with the content of feedback.

SOURCE PAGE
- Use the PDF page number(s) where the activity itself is supported.
- If the information comes from several pages, give a compact range/list such as '2-4' or '2, 5'.
- For DOCX/TXT, use 'Not Identified' unless the source itself provides page numbers.

NAAC MAPPING
Select ONE best-fit Attribute and ONE best-fit Metric for each activity.
Use the following internal reference catalog exactly:
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

Use the activity's actual purpose and content, not merely words in its title.
Useful internal examples:
- Technical/domain-oriented student activities, competitions and similar extension activities → Attribute 6; Metric 6.1 when clearly supported.
- Cultural activities → 6.2 when clearly supported.
- Student wellbeing/health activities → 6.3 when clearly supported.
- Value education/ethics → 6.4 when clearly supported.
- Sports activities → 6.5 when clearly supported.
- Community service/NSS/UBA/community outreach → 6.6 when clearly supported.
- IQAC/quality assurance activities → 7.6 when clearly supported.
- Explicit environmental/green initiatives such as tree plantation → Attribute 10; Metric 10.4 when clearly supported.
These are internal reference mappings, not an official accreditation determination.
Do not force a mapping when the activity genuinely provides insufficient information.

DOCUMENT EVIDENCE — COMPLETE CHECKLIST
You MUST return exactly one EvidenceItem for EVERY document type below, in the same order:
{', '.join(DOCUMENT_TYPES)}

For each evidence type:
- Present = the supplied report actually contains that evidence, or clearly identifies it as part of the report.
- Absent = the report has been sufficiently checked and that evidence is not present.
- Not Identified = the document is ambiguous, unreadable, or the available material does not allow a reliable determination.
- Never infer evidence merely because the activity exists.
- For Present, give the PDF page where it appears when possible.
- For Absent/Not Identified, source_page = Not Identified.
- If the report explicitly says an evidence item is 'NA', 'not available', 'not attached', etc., treat that as Absent.
- If an event report contains embedded photographs, mark Photographs as Present.
- If those photographs are explicitly identified as geotagged/location-tagged, mark Geotagged Photographs as Present; do not assume every photograph is geotagged.
- If the report has an attendance list/table, mark Attendance as Present.
- If it has a feedback form, feedback summary or feedback analysis, mark the corresponding evidence type as Present only according to what is actually shown.
- Do not confuse a mention of a document with the document itself unless the report clearly identifies it as attached/included.

QUALITY RULES
- Never leave a field as Not Identified merely because the report used different wording.
- Prefer a concise factual value over a vague value.
- Do not copy huge paragraphs into individual fields.
- Preserve important counts and names exactly.
- When several pages contain complementary information for the same event, consolidate them.
- Never create facts to make a record look complete.
""".strip()

RECOVERY_PROMPT = """
Re-read the COMPLETE supplied document as an experienced college IQAC records officer.
The previous pass did not produce usable activity records. Look beyond literal field labels: use headings, paragraphs, tables, notices, event descriptions, attendance, evidence sections and conclusions to identify genuine activities and extract the information that is actually present.
Return at least one activity when the document clearly describes one. Missing facts should remain Not Identified, but do not mark a clearly stated fact as Not Identified merely because it is expressed indirectly.
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
        if len(text) > 220_000:
            text = text[:220_000] + "\n--- DOCUMENT TEXT TRUNCATED ---"
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
        return _generate(client, model, [remote_file, prompt + "\nAnalyze the complete uploaded document, including its visual layout, tables and embedded evidence pages."])
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
        if len(text) > 220_000:
            text = text[:220_000]
        return _generate(client, model, [SYSTEM_PROMPT, RECOVERY_PROMPT, f"\nSOURCE FILE: {filename}\nPROCESSING MODE: {method}\n", text])
    return _analyze_once(raw, filename, model, api_key)


def _norm_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


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

    # Keep the main two requested columns, while preserving uncertainty clearly.
    if not_identified:
        absent_display = "; ".join(absent) if absent else "None Identified"
        absent_display += " | Not Identified: " + "; ".join(not_identified)
    else:
        absent_display = "; ".join(absent) if absent else "None Identified"

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
