from __future__ import annotations

import json
import os
import tempfile
import time
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .record_utils import COLUMNS, NAAC_ATTRIBUTES, normalize_record


NAAC_METRICS = {
    "Curriculum Design": {"1.1", "1.2", "1.3", "1.4", "1.5", "1.6", "1.7", "1.8"},
    "Faculty Resources": {"2.1", "2.2", "2.3", "2.7"},
    "Infrastructure": {"3.1", "3.2", "3.3", "3.4", "3.5", "3.6"},
    "Financial Resources & Management": {"4.1 & 4.2", "4.3 & 4.4", "4.5", "4.6"},
    "Learning & Teaching": {"5.1", "5.2", "5.3", "5.4", "5.5", "5.6", "5.7", "5.8"},
    "Extended Curricular Engagements": {"6.1", "6.2", "6.3", "6.4", "6.5", "6.6"},
    "Governance and Administration": {"7.1", "7.2", "7.3", "7.4", "7.5", "7.6", "7.7", "7.8", "7.9", "7.10"},
    "Student Outcomes": {"8.1", "8.2", "8.3", "8.4", "8.5", "8.6", "8.7", "8.8"},
    "Research & Innovation Outcomes": {"9.1", "9.2", "9.3", "9.4", "9.5", "9.6", "9.7", "9.8", "9.9"},
    "Sustainability Outcomes (Including Green Initiatives)": {"10.1", "10.2", "10.3", "10.4", "10.5"},
}


RECOVERY_PROMPT = r"""
ACTIVITY RECOVERY PASS — HIGH PRIORITY
The previous structured extraction returned zero activities. This is a recovery pass for a college IQAC report.

Read the COMPLETE uploaded document again. Pay special attention to the FIRST 1–3 PAGES. Many RTCCS reports contain
an "Activity Sheet", "Basic Summary", "IQAC Cell Activity Number", "Activity Number", "Type of Activity", "Title",
"Date", "Time", "Venue", "Department/Committee/Association", "Objective", "Participants", "Coordinator", and
"Outcome" fields near the beginning.

If those anchors describe a real institutional event/activity, you MUST return exactly one Activity for that event,
even when later pages are only attendance, photographs, feedback, notices or evidence. Do not require a programme table,
invitation, certificate or publicity item.

Examples of genuine activities include tree plantation drives, seminars, workshops, camps, awareness programmes,
sports events, cultural events, NSS activities, extension activities and other college events.

IMPORTANT:
- A multi-page report for one event is ONE activity.
- Attendance sheets, feedback forms, photographs, proposals and notices normally SUPPORT an activity; they are not
  separate activities.
- If the first pages clearly identify an activity, do not return zero activities.
- For a genuine Activity Report or Activity Sheet / Basic Summary, set document_profile.is_primary_activity_document=true.
- Use the document_profile anchors as an additional safety net. If the first pages identify an activity, populate at
  least one Activity object from those anchors even if many detailed fields remain Not Identified.
- Use "Not Identified" for fields that cannot be established.
- Preserve exact institutional wording.
- Do not invent values.

Only return zero activities when the entire document genuinely contains no identifiable institutional activity,
such as a standalone administrative document with no event context.
"""


NAAC_METRIC_TEXT = r"""
NAAC METRIC VALIDATION
The metric must be one of the exact metric codes in the supplied catalog. Keep the attribute and metric logically
consistent. Do not output a metric from a different attribute. If the report does not support a mapping, use
Not Identified. Never invent an official NAAC score."""


class GeminiError(RuntimeError):
    pass


DOCUMENT_TYPES = [
    "Activity Report",
    "Activity Sheet / Basic Summary",
    "Notice",
    "Proposal",
    "Attendance Sheet",
    "Feedback Form",
    "Feedback Analysis",
    "Certificate",
    "Circular",
    "Invitation",
    "Photographic Evidence",
    "News / Publicity",
    "Programme / Schedule",
    "Appreciation Letter",
    "Other Supporting Document",
    "Unknown",
]


class DocumentProfile(BaseModel):
    document_type: str = "Unknown"
    is_primary_activity_document: bool = False
    activity_title_anchor: str = "Not Identified"
    activity_date_anchor: str = "Not Identified"
    activity_number: str = "Not Identified"
    academic_year_anchor: str = "Not Identified"
    organizing_department_anchor: str = "Not Identified"
    organizing_committee_anchor: str = "Not Identified"
    venue_anchor: str = "Not Identified"
    collaborating_agency_anchor: str = "Not Identified"
    relationship_notes: str = "Not Identified"
    relationship_confidence: str = "Not Identified"
    source_pages: str = "Not Identified"


class EvidenceChecklist(BaseModel):
    proposal: str = Field(description="Present, Absent, or Unclear. Do not infer absence from silence; use Unclear if the document cannot be determined.")
    notice: str = Field(description="Present, Absent, or Unclear.")
    programme_table: str = Field(description="Present, Absent, or Unclear. This is optional and must not be treated as mandatory.")
    invitation: str = Field(description="Present, Absent, or Unclear.")
    appreciation_letter: str = Field(description="Present, Absent, or Unclear.")
    attendance: str = Field(description="Present, Absent, or Unclear.")
    event_report: str = Field(description="Present, Absent, or Unclear.")
    photographs: str = Field(description="Present, Absent, or Unclear.")
    geotagged_photo: str = Field(description="Present, Absent, or Unclear.")
    feedback_evidence: str = Field(description="Present, Absent, or Unclear.")
    news_publicity: str = Field(description="Present, Absent, or Unclear.")
    certificates: str = Field(description="Present, Absent, or Unclear.")
    other_evidence: str = Field(description="Present, Absent, or Unclear; mention the type in the same field.")


class EvidenceTrace(BaseModel):
    evidence_type: str = Field(description="Evidence category.")
    status: str = Field(default="Not Identified", description="Present, Not Identified, or Not Applicable.")
    source_page: str = Field(default="Not Identified", description="Supporting PDF page or page range.")
    notes: str = Field(default="", description="Short source-grounded note.")


class FieldTrace(BaseModel):
    field: str = Field(description="Canonical field name, for example Activity Date, Activity Title, or Total Participants.")
    source_page: str = Field(default="Not Identified", description="PDF page number or compact page range directly supporting the field.")
    confidence: str = Field(default="Not Identified", description="Extraction confidence from 0-100, not factual certainty.")


class Activity(BaseModel):
    academic_year: str = "Not Identified"
    activity_date: str = "Not Identified"
    activity_title: str = "Not Identified"
    activity_type: str = "Not Identified"
    category: str = "Not Identified"
    organizing_department: str = "Not Identified"
    organizing_committee: str = "Not Identified"
    collaborating_agency: str = "Not Identified"
    resource_person: str = "Not Identified"
    resource_person_affiliation: str = "Not Identified"
    venue: str = "Not Identified"
    duration: str = "Not Identified"
    target_group: str = "Not Identified"
    total_participants: str = "Not Identified"
    student_participants: str = "Not Identified"
    faculty_participants: str = "Not Identified"
    external_participants: str = "Not Identified"
    objective: str = "Not Identified"
    activity_description: str = "Not Identified"
    outcome: str = "Not Identified"
    impact: str = "Not Identified"
    follow_up_action: str = "Not Identified"
    feedback: str = "Not Identified"
    evidence_available: str = "Not Identified"
    evidence_link: str = "Not Identified"
    evidence: EvidenceChecklist
    naac_attribute: str = "Not Identified"
    naac_metric: str = "Not Identified"
    quantitative_data: str = "Not Identified"
    source_page: str = "Not Identified"
    activity_summary_pages: str = "Not Identified"
    missing_information: str = "Not Identified"
    evidence_gaps: str = "Not Identified"
    extraction_notes: str = "Not Identified"
    # Fixed-list traceability is used instead of dynamic dictionaries because the
    # Gemini structured-output schema must not require a dynamic additionalProperties object.
    field_trace: list[FieldTrace] = Field(
        default_factory=list,
        description="Field-level source page and extraction-confidence records."
    )
    evidence_trace: list[EvidenceTrace] = Field(
        default_factory=list,
        description="Structured evidence checklist with source-grounded status and page references."
    )


class ReportAnalysis(BaseModel):
    document_type: str = "Not Identified"
    academic_year: str = "Not Identified"
    report_summary: str = "Not Identified"
    document_profile: DocumentProfile = Field(default_factory=DocumentProfile)
    activities: list[Activity] = Field(default_factory=list)


SYSTEM_PROMPT = r"""
You are the document-analysis engine for a college Internal Quality Assurance Cell (IQAC).
You are analyzing a real institutional IQAC activity report, which may be a scanned PDF with photographs,
handwriting, tables, notices, attendance sheets and newspaper clippings.

CORE RULES
1. Detect every distinct activity represented in the report. One activity = one output record.
2. Do not assume there is only one activity per uploaded report.
3. The first 1–2 pages may be an Activity Sheet / Basic Summary. Use it as the primary anchor for the activity,
   then connect later pages that belong to that same activity.
4. Supporting documents are variable. An activity may contain a proposal, notice, programme table, invitation,
   appreciation letter, attendance, event report, photographs, geotagged photographs, feedback, publicity,
   certificates, links, or other evidence. Some may be absent. Missing an optional document does NOT invalidate
   the activity.
5. In particular, Programme Table is NOT mandatory. Never invent one.
6. If an item is not visible or cannot be established, use "Not Identified" or "Unclear" as appropriate.
7. Never infer an outcome merely from generic language such as "successfully conducted". Extract the actual stated
   outcome. If no real outcome is stated, use "Not Identified".
8. Keep Outcome and Impact separate. Do not convert a stated outcome into an impact unless the report explicitly
   supports that distinction.
9. Extract numbers exactly when supported. Do not calculate or invent participant totals.
10. Preserve institutional wording, activity titles, department names, committee names, dates and venue names.
11. For page traceability, use the PDF page number(s) where the activity is summarized and where supporting evidence
    appears. If several pages belong to the activity, use a compact range/list such as "1-14" or "3, 7-14".
12. For every important extracted field, provide a field_sources entry using the canonical field name and the page(s)
    that directly support that value. Use "Not Identified" when the value is not supported. Do not invent page numbers.
13. For every important extracted field, provide field_confidence as an extraction-evidence estimate from 0-100.
14. Populate evidence_trace using the fixed evidence categories. Use Present, Not Identified, or Not Applicable only from actual document evidence. For Present evidence, provide its supporting page or page range. Do not invent evidence or page numbers.
15. Attendance, photographs, feedback, proposals and notices normally support an activity and must not become separate activities.
    Use high confidence only when the value is clearly readable and directly supported; use lower confidence for
    partial/uncertain OCR or indirect evidence. For a missing field use 0 or "Not Identified".
14. If multiple pages support a field, list them compactly, e.g. "1-2" or "6-8". If the field is supported by the
    activity summary page and later evidence, list both, e.g. "2, 9-10".
15. Field confidence is NOT factual certainty and must not be presented as an official probability.
16. If the document is image-based, read the page images visually. Handwritten attendance and feedback count as evidence.
17. Do not treat a newspaper clipping, photo or feedback form as a separate activity unless it clearly describes a
    separate event.
18. Do not create duplicate activities from repeated headers, feedback pages, photos or evidence pages.
19. NAAC/Binary mapping is a reference classification only. Do not claim an official NAAC score or accreditation result.
20. Return at least one activity whenever the document clearly contains an institutional event/activity, even if some fields are missing.
17. Do not return zero activities merely because the report contains scanned images, handwriting or supporting evidence pages.
18. For a single event with many supporting pages, return exactly one activity unless the report clearly documents multiple distinct events.
19. Use the exact NAAC metric code from the supplied catalog; never write a metric name without its code.
20. The output is for human verification. Be conservative when evidence is ambiguous.

REAL REPORT PATTERN TO RECOGNIZE
A typical RTCCS activity report may have:
- Activity Sheet / Basic Summary (often 1–2 pages)
- Proposal
- Notice
- Programme Table (sometimes absent)
- Invitation / Appreciation
- Attendance
- Event Report
- Normal / Geotagged Photos
- Feedback Forms
- News / Publicity
The exact combination can vary by activity.

DOCUMENT CLASSIFICATION AND RELATIONSHIP INTELLIGENCE
17. Classify the uploaded file into exactly one document type from this controlled vocabulary:
    Activity Report, Activity Sheet / Basic Summary, Notice, Proposal, Attendance Sheet, Feedback Form,
    Feedback Analysis, Certificate, Circular, Invitation, Photographic Evidence, News / Publicity,
    Programme / Schedule, Appreciation Letter, Other Supporting Document, or Unknown.
18. Set is_primary_activity_document=true when the document itself can legitimately create one or more master
    activity records. Activity Report and Activity Sheet / Basic Summary are primary when they contain identifiable
    institutional activities. Supporting documents normally have is_primary_activity_document=false.
19. Extract relationship anchors only when explicitly visible: activity title, date, activity number, academic year,
    department, committee, venue and collaborating agency. Use Not Identified when unavailable.
20. Supporting documents must not become separate activities merely because they repeat an activity title, date,
    participant names or event details. Keep activities empty for a pure supporting document unless it clearly
    documents a distinct additional activity.
21. If a primary document contains multiple distinct activities, return each distinct activity separately.
22. relationship_notes must contain only source-grounded clues from this document. Do not claim that another uploaded
    file is related because you cannot see the other file in the current Gemini request.
23. relationship_confidence describes confidence in the extracted anchors, not certainty of a cross-file match.

EVIDENCE STATUS
For each evidence type return exactly one of Present, Absent, or Unclear. Do not call an item Absent merely because
it was not obvious in a cropped image; use Unclear when the report cannot establish the status.


NAAC / BINARY ACCREDITATION REFERENCE MAPPING
Use this only as a classification/reference layer. Do not calculate official NAAC scores.

ATTRIBUTE 1 — Curriculum Design
1.1 Outcome-based Curriculum
1.2 Stakeholder Participation
1.3 Curriculum Flexibility
1.4 Practical and Industry Focus
1.5 Practical/Skill Orientation
1.6 Online and Blended Learning
1.7 Curriculum Revision
1.8 Indian Knowledge System

ATTRIBUTE 2 — Faculty Resources
2.1 Recruitment
2.2 Pay and Allowances
2.3 Faculty Diversity
2.7 Faculty Quality

ATTRIBUTE 3 — Infrastructure
3.1 Physical Infrastructure
3.2 Learning Resources
3.3 IT Infrastructure
3.4 Research Resources
3.5 Divyangjan Friendly Facilities
3.6 Innovation Resources

ATTRIBUTE 4 — Financial Resources & Management
4.1 & 4.2 Capital Income / Revenue Income
4.3 & 4.4 Capital Expenditure / Revenue Expenditure
4.5 Sustainability and Growth
4.6 Financial Controls & Risk Management

ATTRIBUTE 5 — Learning & Teaching
5.1 Pedagogical Approaches
5.2 Internships, Field Projects etc.
5.3 Assessment Components
5.4 Academic Grievances Redressal
5.5 Catering to Diversity
5.6 Learning Management System
5.7 Industry Academia Linkage
5.8 Adherence to Academic Calendar

ATTRIBUTE 6 — Extended Curricular Engagements
6.1 Technical/Domain related Clubs, activities and technical festivals
6.2 Cultural Clubs and activities and festivals
6.3 Mental health/wellbeing clubs and activities
6.4 Value Education
6.5 Sports clubs/teams and activities
6.6 Community related (focus) activities including UBA

ATTRIBUTE 7 — Governance and Administration
7.1 Statutory Compliance and Public Disclosure
7.2 Institutional Development Plan
7.3 e-Governance
7.4 Student & Employee Welfare
7.5 Grievance Handling Mechanism
7.6 Quality Assurance System
7.7 Effective Leadership
7.8 National, International, Inter-University Collaborations
7.9 Efforts for Employability
7.10 Faculty Retention

ATTRIBUTE 8 — Student Outcomes
8.1 Placements/Employment
8.2 Graduate Progression
8.3 Self-employment/Entrepreneurship
8.4 Competitive Exams
8.5 Awards/Prizes/Recognitions for curricular and extended curricular areas
8.6 Student Enrolment
8.7 Pass Percentage or Graduation Rate
8.8 Student/Alumni Learning Experience

ATTRIBUTE 9 — Research & Innovation Outcomes
9.1 External Research Grants
9.2 Research Publications
9.3 Research Quality
9.4 PhDs Awarded
9.5 Research Fellowships
9.6 IPRs Produced
9.7 Consultancy and Training
9.8 Research Collaboration
9.9 Number of Student Startups

ATTRIBUTE 10 — Sustainability Outcomes (Including Green Initiatives)
10.1 Community Activities
10.2 Waste and Water Management
10.3 Progressing towards Net Zero
10.4 Green Audits and Initiatives
10.5 Collaborations with Industry/NGOs

CLASSIFICATION RULES
- Choose the most specific metric supported by the actual activity content.
- Tree plantation, green-environment drives, biodiversity/greening activities and similar green initiatives should normally map to 10.4 Green Audits and Initiatives when the report documents the green initiative itself.
- Community outreach/service activities may map to 6.6 Community related (focus) activities including UBA when community engagement is the primary nature.
- Cultural activities map to 6.2; sports to 6.5; technical/domain activities to 6.1; mental-health/wellbeing to 6.3; value education to 6.4.
- Teaching methods map to 5.1; internships/field projects to 5.2; assessment methods to 5.3; industry linkage to 5.7; academic-calendar compliance to 5.8.
- IQAC, quality assurance, audits, stakeholder satisfaction and quality initiatives map to 7.6.
- Awards/recognitions map to 8.5 when student awards/recognitions are documented.
- Do not force a mapping when the report genuinely does not support one. Use "Not Identified" only in that case.

SOURCE DISCIPLINE
Every extracted value must be supported by the uploaded report. Do not use outside knowledge to fill missing values.
"""


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


def _mime_for(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        return "application/pdf"
    if suffix == ".docx":
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if suffix == ".txt":
        return "text/plain"
    raise GeminiError("Only PDF, DOCX and TXT files are supported.")


def _is_transient_gemini_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(term in message for term in (
        "503", "service unavailable", "unavailable", "overloaded", "high demand",
        "temporarily unavailable", "429", "resource exhausted", "too many requests",
        "500", "502", "504", "timeout", "timed out", "deadline exceeded"
    ))


def _upload_and_analyze(
    raw: bytes,
    filename: str,
    model: str,
    api_key: str,
    max_retries: int = 2,
) -> ReportAnalysis:
    # FAST PATH: use the lightweight model first. The configured model is retained
    # only as a fallback, so normal documents require a single Gemini generation call.
    models_to_try = ["gemini-3.5-flash-lite"]
    if model and model != "gemini-3.5-flash-lite":
        models_to_try.append(model)

    last_error: Exception | None = None
    for selected_model in models_to_try:
        for attempt in range(1, max_retries + 1):
            try:
                result = _upload_and_analyze_once(raw, filename, selected_model, api_key)

                # FAST PATH: if Gemini already identified a primary activity document
                # and supplied title/date anchors, let the deterministic safety-net in
                # analyze_report create the minimal record. Do NOT spend another Gemini
                # call on recovery in this common case. Recovery is reserved for genuinely
                # ambiguous zero-activity results.
                if not result.activities:
                    profile = result.document_profile
                    has_anchor = (
                        profile.is_primary_activity_document
                        and (
                            profile.activity_title_anchor not in {"", "Not Identified", "Unknown", "Unclear"}
                            or profile.activity_date_anchor not in {"", "Not Identified", "Unknown", "Unclear"}
                        )
                    )
                    if has_anchor:
                        return result

                    recovered = _recover_activities(raw, filename, selected_model, api_key)
                    if recovered.activities:
                        return recovered
                    last_error = GeminiError(
                        f"{selected_model} returned zero activities after recovery for {filename}."
                    )
                    continue

                return result
            except Exception as exc:
                last_error = exc
                if not _is_transient_gemini_error(exc):
                    if isinstance(exc, GeminiError):
                        raise
                    raise GeminiError(f"Gemini analysis failed for {filename}: {exc}") from exc
                if attempt < max_retries:
                    time.sleep(2 ** (attempt - 1))

    raise GeminiError(
        f"Gemini is temporarily unavailable for {filename}. "
        f"Please retry after a short wait. Last error: {last_error}"
    ) from last_error


def _recover_activities(raw: bytes, filename: str, model: str, api_key: str) -> ReportAnalysis:
    """Run a targeted second extraction pass only when the first pass found no activities."""
    client = _client(api_key)
    suffix = Path(filename).suffix.lower()
    temp_path: str | None = None
    remote_file = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(raw)
            temp_path = tmp.name
        try:
            remote_file = client.files.upload(
                file=temp_path,
                config={"mime_type": _mime_for(filename)},
            )
        except TypeError:
            remote_file = client.files.upload(file=temp_path)

        prompt = SYSTEM_PROMPT + "\n\n" + RECOVERY_PROMPT + "\n\n" + NAAC_METRIC_TEXT
        prompt += """
RECOVERY OUTPUT REQUIREMENT:
If the first pages contain a recognizable institutional activity sheet/basic summary,
populate one Activity object from those anchors. It is preferable to return one
partially populated activity with Not Identified fields than to return zero activities
for a genuine event report.
If document_profile identifies an Activity Report or Activity Sheet / Basic Summary and
provides a title or date anchor, return at least one Activity object.
"""
        prompt += f"\n\nSOURCE FILE NAME: {filename}\nReturn the structured report after this recovery pass."
        response = client.models.generate_content(
            model=model,
            contents=[remote_file, prompt],
            config={
                "temperature": 0.0,
                "response_mime_type": "application/json",
                "response_schema": ReportAnalysis,
            },
        )
        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, ReportAnalysis):
            return parsed
        raw_text = getattr(response, "text", "") or ""
        if not raw_text:
            raise GeminiError("Gemini recovery pass returned an empty response.")
        try:
            return ReportAnalysis.model_validate_json(raw_text)
        except Exception as exc:
            raise GeminiError(f"Gemini recovery pass returned invalid structured data: {exc}") from exc
    except GeminiError:
        raise
    except Exception as exc:
        raise GeminiError(f"Gemini activity-recovery pass failed for {filename}: {exc}") from exc
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


def _extract_local_text(raw: bytes, filename: str) -> tuple[str, bool, str]:
    """Extract page-labelled text locally before using Gemini file upload.

    Returns (text, usable, method).  The fast path is deliberately conservative:
    if a PDF looks scanned/image-only, the caller falls back to the original Gemini
    PDF upload so visual evidence is not silently discarded.
    """
    suffix = Path(filename).suffix.lower()
    try:
        if suffix == ".txt":
            text = raw.decode("utf-8", errors="replace")
            return text.strip(), bool(text.strip()), "local-text"

        if suffix == ".docx":
            from docx import Document
            import io
            doc = Document(io.BytesIO(raw))
            chunks = []
            for p in doc.paragraphs:
                if p.text.strip():
                    chunks.append(p.text.strip())
            for table in doc.tables:
                for row in table.rows:
                    cells = [c.text.strip() for c in row.cells]
                    if any(cells):
                        chunks.append(" | ".join(cells))
            text = "\n".join(chunks).strip()
            return text, len(text) >= 120, "local-docx"

        if suffix == ".pdf":
            import fitz
            doc = fitz.open(stream=raw, filetype="pdf")
            pages = []
            total_chars = 0
            nonspace = 0
            alpha = 0
            for idx, page in enumerate(doc, start=1):
                page_text = page.get_text("text") or ""
                cleaned = page_text.strip()
                pages.append(f"\n--- PDF PAGE {idx} ---\n{cleaned}")
                total_chars += len(cleaned)
                nonspace += sum(not ch.isspace() for ch in cleaned)
                alpha += sum(ch.isalpha() for ch in cleaned)
            doc.close()
            text = "\n".join(pages).strip()
            page_count = max(1, len(pages))
            avg_chars = total_chars / page_count
            alpha_ratio = alpha / max(1, nonspace)
            # Conservative threshold: use local text only when most pages contain
            # meaningful machine-readable text. Scanned/image-heavy PDFs retain the
            # original visual Gemini path.
            usable = total_chars >= 500 and avg_chars >= 80 and alpha_ratio >= 0.35
            return text, usable, "local-pdf-text" if usable else "pdf-visual-fallback"
    except Exception:
        return "", False, "extraction-failed"
    return "", False, "unsupported"


def _generate_structured(client, model: str, contents: list[Any]) -> ReportAnalysis:
    response = client.models.generate_content(
        model=model,
        contents=contents,
        config={
            "temperature": 0.1,
            "response_mime_type": "application/json",
            "response_schema": ReportAnalysis,
        },
    )
    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, ReportAnalysis):
        return parsed
    raw_text = getattr(response, "text", "") or ""
    if not raw_text:
        raise GeminiError("Gemini returned an empty response.")
    try:
        return ReportAnalysis.model_validate_json(raw_text)
    except Exception as exc:
        raise GeminiError(f"Gemini returned invalid structured data: {exc}") from exc


def _upload_and_analyze_once(raw: bytes, filename: str, model: str, api_key: str) -> ReportAnalysis:
    client = _client(api_key)
    extracted_text, usable_text, extraction_method = _extract_local_text(raw, filename)
    prompt = (
        SYSTEM_PROMPT
        + f"\n\nSOURCE FILE NAME: {filename}"
        + f"\nLOCAL EXTRACTION MODE: {extraction_method}"
    )

    # UPGRADE 11 FAST PATH: for text-readable PDFs/DOCX/TXT, avoid Gemini Files upload
    # and send compact page-labelled text directly. This removes upload, remote-file
    # processing and cleanup latency.
    if usable_text:
        # Keep enough context for large reports while avoiding pathological payloads.
        if len(extracted_text) > 180_000:
            extracted_text = extracted_text[:180_000] + "\n--- END OF LOCALLY EXTRACTED TEXT (TRUNCATED) ---"
        prompt += "\n\nAnalyze the complete locally extracted document text below. Preserve page markers.\n"
        return _generate_structured(client, model, [prompt, extracted_text])

    # VISUAL FALLBACK: scanned/image-heavy PDFs still go through Gemini's native PDF
    # understanding so photographs, handwriting and tables are not silently lost.
    suffix = Path(filename).suffix.lower()
    temp_path: str | None = None
    remote_file = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(raw)
            temp_path = tmp.name
        try:
            remote_file = client.files.upload(
                file=temp_path,
                config={"mime_type": _mime_for(filename)},
            )
        except TypeError:
            remote_file = client.files.upload(file=temp_path)
        prompt += "\n\nAnalyze the complete uploaded document and return the structured report."
        return _generate_structured(client, model, [remote_file, prompt])
    except GeminiError:
        raise
    except Exception as exc:
        raise GeminiError(f"Gemini analysis failed for {filename}: {exc}") from exc
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


def _keyword_naac_fallback(a: Activity) -> tuple[str, str]:
    blob = " ".join([
        a.activity_title, a.activity_type, a.category, a.objective,
        a.activity_description, a.outcome, a.collaborating_agency
    ]).lower()
    rules = [
        (("tree plantation", "tree planting", "plantation drive", "green environment",
          "environmental sustainability", "green initiative", "world environment day"),
         "Sustainability Outcomes (Including Green Initiatives)",
         "10.4 Green Audits and Initiatives"),
        (("blood donation", "health camp", "medical camp", "community service", "outreach"),
         "Extended Curricular Engagements",
         "6.6 Community related (focus) activities including UBA"),
        (("sports", "football", "cricket", "badminton", "athletics", "tournament"),
         "Extended Curricular Engagements",
         "6.5 Sports clubs/teams and activities"),
        (("cultural", "dance", "music", "drama", "rangoli", "art competition"),
         "Extended Curricular Engagements",
         "6.2 Cultural Clubs and activities and festivals"),
        (("technical", "hackathon", "coding", "robotics", "technical festival"),
         "Extended Curricular Engagements",
         "6.1 Technical/Domain related Clubs, activities and technical festivals"),
        (("yoga", "meditation", "mental health", "wellbeing", "counselling"),
         "Extended Curricular Engagements",
         "6.3 Mental health/wellbeing clubs and activities"),
    ]
    for keywords, attr, metric in rules:
        if any(k in blob for k in keywords):
            return attr, metric
    return "Not Identified", "Not Identified"


_CANONICAL_FIELD_ALIASES = {
    "academic_year": "Academic Year",
    "activity_date": "Activity Date",
    "activity_title": "Activity Title",
    "activity_type": "Activity Type",
    "category": "Category",
    "organizing_department": "Organizing Department",
    "organizing_committee": "Organizing Committee",
    "collaborating_agency": "Collaborating Agency",
    "resource_person": "Resource Person",
    "resource_person_affiliation": "Resource Person Affiliation",
    "venue": "Venue",
    "duration": "Duration",
    "target_group": "Target Group",
    "total_participants": "Total Participants",
    "student_participants": "Student Participants",
    "faculty_participants": "Faculty Participants",
    "external_participants": "External Participants",
    "objective": "Objective",
    "activity_description": "Activity Description",
    "outcome": "Outcome",
    "impact": "Impact",
    "follow_up_action": "Follow-up Action",
    "feedback": "Feedback",
    "evidence_available": "Evidence Available",
    "evidence_link": "Evidence Link",
    "naac_attribute": "NAAC Attribute",
    "naac_metric": "NAAC Metric",
    "quantitative_data": "Quantitative Data",
    "source_page": "Source Page",
    "activity_summary_pages": "Activity Summary Pages",
    "missing_information": "Missing Information",
    "evidence_gaps": "Evidence Gaps",
}


EVIDENCE_CATEGORIES = [
    "Proposal", "Notice", "Invitation", "Programme/Schedule", "Attendance",
    "Event Report", "Photographs", "Geotagged Photographs", "Feedback",
    "Feedback Analysis", "News/Publicity", "Certificate", "Other Evidence",
]


def _evidence_trace_parts(a: Activity) -> list[dict[str, str]]:
    aliases = {
        "program": "Programme/Schedule", "programme": "Programme/Schedule",
        "schedule": "Programme/Schedule", "program schedule": "Programme/Schedule",
        "photo": "Photographs", "photos": "Photographs", "photograph": "Photographs",
        "geotagged photo": "Geotagged Photographs", "geotagged photos": "Geotagged Photographs",
        "news": "News/Publicity", "publicity": "News/Publicity",
        "certificate": "Certificate", "certificates": "Certificate",
    }
    result, seen = [], set()
    for item in (a.evidence_trace or []):
        category = str(item.evidence_type or "").strip()
        if not category:
            continue
        category = aliases.get(category.lower().replace("_"," ").replace("-"," "), category)
        if category.lower() in seen:
            continue
        seen.add(category.lower())
        raw = str(item.status or "Not Identified").strip().lower()
        status = "Present" if raw in {"present","available","found","yes"} else (
            "Not Applicable" if raw in {"na","n/a","not applicable"} else "Not Identified"
        )
        result.append({
            "Evidence Type": category,
            "Status": status,
            "Source Page": str(item.source_page or "Not Identified").strip(),
            "Notes": str(item.notes or "").strip(),
        })
    return result


def _evidence_summary(items: list[dict[str, str]]) -> str:
    if not items:
        return "Not Identified"
    return " | ".join(
        f"{x['Evidence Type']}: {x['Status']}" +
        (f" (p. {x['Source Page']})" if x["Source Page"] else "")
        for x in items
    )


def _evidence_present_count(items: list[dict[str, str]]) -> int:
    return sum(x["Status"] == "Present" for x in items)


def _trace_parts(a: Activity) -> tuple[dict[str, str], dict[str, str]]:
    """Convert fixed-list Gemini traceability into the legacy dict representation."""
    sources: dict[str, str] = {}
    confidence: dict[str, str] = {}
    for item in (a.field_trace or []):
        if not item.field:
            continue
        field = str(item.field).strip()
        if item.source_page:
            sources[field] = str(item.source_page).strip()
        if item.confidence:
            confidence[field] = str(item.confidence).strip()
    return sources, confidence


def _compact_field_sources(values: dict[str, str] | None) -> str:
    if not values:
        return "Not Identified"
    parts = [f"{k}: {v}" for k, v in values.items() if str(v).strip()]
    return " | ".join(parts) if parts else "Not Identified"


def _normalize_field_confidence(values: dict[str, str] | None, a: Activity) -> str:
    # Keep the existing human-readable master-field value while deriving it
    # from the new fixed-list traceability representation.
    if not values:
        return "Not Identified"
    parts = []
    for field, value in values.items():
        try:
            raw = str(value).strip().replace("%", "")
            score = float(raw)
            if score <= 1:
                score *= 100
            score = max(0, min(100, score))
            parts.append(f"{field}: {score:.0f}%")
        except Exception:
            if str(value).strip():
                parts.append(f"{field}: {value}")
    return " | ".join(parts) if parts else "Not Identified"

def _map_activity(a: Activity, source_file: str, index: int, report_year: str) -> dict[str, str]:
    e = a.evidence
    field_sources, field_confidence = _trace_parts(a)
    evidence_trace = _evidence_trace_parts(a)
    mapped: dict[str, Any] = {
        "Academic Year": a.academic_year if a.academic_year != "Not Identified" else report_year,
        "Activity Date": a.activity_date,
        "Activity Title": a.activity_title,
        "Activity Type": a.activity_type,
        "Category": a.category,
        "Organizing Department": a.organizing_department,
        "Organizing Committee": a.organizing_committee,
        "Collaborating Agency": a.collaborating_agency,
        "Resource Person": a.resource_person,
        "Resource Person Affiliation": a.resource_person_affiliation,
        "Venue": a.venue,
        "Duration": a.duration,
        "Target Group": a.target_group,
        "Total Participants": a.total_participants,
        "Student Participants": a.student_participants,
        "Faculty Participants": a.faculty_participants,
        "External Participants": a.external_participants,
        "Objective": a.objective,
        "Activity Description": a.activity_description,
        "Outcome": a.outcome,
        "Impact": a.impact,
        "Follow-up Action": a.follow_up_action,
        "Feedback": a.feedback,
        "Evidence Available": a.evidence_available,
        "Evidence Link": a.evidence_link,
        "Evidence Trace": _evidence_summary(evidence_trace),
        "Evidence Present Count": str(_evidence_present_count(evidence_trace)),
        "Evidence Trace Details": evidence_trace,
        "Proposal": e.proposal,
        "Notice": e.notice,
        "Programme Table": e.programme_table,
        "Invitation": e.invitation,
        "Appreciation Letter": e.appreciation_letter,
        "Attendance": e.attendance,
        "Event Report": e.event_report,
        "Photographs": e.photographs,
        "Geotagged Photo": e.geotagged_photo,
        "Feedback Evidence": e.feedback_evidence,
        "News/Publicity": e.news_publicity,
        "Certificates": e.certificates,
        "Other Evidence": e.other_evidence,
        "NAAC Attribute": a.naac_attribute,
        "NAAC Metric": a.naac_metric,
        "Quantitative Data": a.quantitative_data,
        "Source Report": source_file,
        "Source Page": a.source_page,
        "Activity Summary Pages": a.activity_summary_pages,
        "Missing Information": a.missing_information,
        "Evidence Gaps": a.evidence_gaps,
        "Field Sources": _compact_field_sources(field_sources),
        "Field Confidence": _normalize_field_confidence(field_confidence, a),
    }
    # Validate Gemini's mapping against the exact supplied catalog. If Gemini misses either field or produces an
    # inconsistent attribute/metric pair, use the deterministic activity classifier as a safety net.
    attr = str(mapped.get("NAAC Attribute", "Not Identified")).strip()
    metric = str(mapped.get("NAAC Metric", "Not Identified")).strip()
    valid_pair = attr in NAAC_METRICS and metric in NAAC_METRICS.get(attr, set())

    if not valid_pair:
        fallback_attr, fallback_metric = _keyword_naac_fallback(a)
        if fallback_attr != "Not Identified":
            attr, metric = fallback_attr, fallback_metric
        else:
            # Preserve a valid attribute if Gemini supplied one, but never preserve a metric that belongs to
            # another attribute. This prevents contradictory NAAC mappings from reaching the master sheet.
            if attr not in NAAC_METRICS:
                attr = "Not Identified"
            if metric not in NAAC_METRICS.get(attr, set()):
                metric = "Not Identified"

    mapped["NAAC Attribute"] = attr if attr in NAAC_ATTRIBUTES else "Not Identified"
    mapped["NAAC Metric"] = metric if metric in NAAC_METRICS.get(mapped["NAAC Attribute"], set()) else "Not Identified"
    return normalize_record(mapped, source_file, index, a.source_page or "Not Identified")


def analyze_report(raw: bytes, filename: str, model: str, api_key: str) -> tuple[list[dict[str, str]], dict[str, str]]:
    result = _upload_and_analyze(raw, filename, model, api_key)
    records = [_map_activity(a, filename, i, result.academic_year) for i, a in enumerate(result.activities, 1)]

    profile = result.document_profile
    document_type = profile.document_type if profile.document_type != "Unknown" else result.document_type
    if document_type not in DOCUMENT_TYPES:
        document_type = "Unknown"

    # Deterministic safety net: if Gemini identifies a primary activity document and
    # still returns no activity object, create a minimally populated record from
    # explicit document anchors only. This prevents a genuine report from disappearing
    # while preserving the no-hallucination rule.
    if not records and profile.is_primary_activity_document:
        title = profile.activity_title_anchor
        date = profile.activity_date_anchor
        if title not in {"", "Not Identified", "Unknown", "Unclear"} or date not in {"", "Not Identified", "Unknown", "Unclear"}:
            fallback = Activity(
                academic_year=(profile.academic_year_anchor if profile.academic_year_anchor not in {"", "Not Identified"} else result.academic_year),
                activity_date=date,
                activity_title=title,
                organizing_department=profile.organizing_department_anchor,
                organizing_committee=profile.organizing_committee_anchor,
                collaborating_agency=profile.collaborating_agency_anchor,
                venue=profile.venue_anchor,
                source_page=profile.source_pages,
                activity_summary_pages=profile.source_pages,
                extraction_notes="Minimal activity record created from explicit document-profile anchors because the primary document extraction returned no activity object. Human verification required.",
            )
            records = [_map_activity(fallback, filename, 1, result.academic_year)]

    meta = {
        "Document Type": document_type,
        "Academic Year": result.academic_year,
        "Summary": result.report_summary,
        "Is Primary Activity Document": str(profile.is_primary_activity_document),
        "Activity Title Anchor": profile.activity_title_anchor,
        "Activity Date Anchor": profile.activity_date_anchor,
        "Activity Number": profile.activity_number,
        "Academic Year Anchor": profile.academic_year_anchor,
        "Department Anchor": profile.organizing_department_anchor,
        "Committee Anchor": profile.organizing_committee_anchor,
        "Venue Anchor": profile.venue_anchor,
        "Collaborating Agency Anchor": profile.collaborating_agency_anchor,
        "Relationship Notes": profile.relationship_notes,
        "Relationship Confidence": profile.relationship_confidence,
        "Document Source Pages": profile.source_pages,
        "Source Report": filename,
    }
    return records, meta


# ---------------------------------------------------------------------------
# Cross-document relationship helpers for the verification layer.
# These functions never auto-merge activities. They only produce candidate links.
# ---------------------------------------------------------------------------
def _clean_anchor(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower()
    if text in {"", "not identified", "unknown", "unclear", "none", "n/a"}:
        return ""
    return " ".join(text.split())


def _similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    return SequenceMatcher(None, left, right).ratio()


def document_relationship_score(left: dict[str, Any], right: dict[str, Any]) -> tuple[float, str]:
    fields = [
        ("title", "Activity Title Anchor", 0.40),
        ("date", "Activity Date Anchor", 0.25),
        ("activity_number", "Activity Number", 0.15),
        ("venue", "Venue Anchor", 0.08),
        ("department", "Department Anchor", 0.06),
        ("committee", "Committee Anchor", 0.04),
        ("collaborating_agency", "Collaborating Agency Anchor", 0.02),
    ]
    score = 0.0
    matched: list[str] = []
    available_weight = 0.0
    for label, key, weight in fields:
        a = _clean_anchor(left.get(key))
        b = _clean_anchor(right.get(key))
        if not a or not b:
            continue
        available_weight += weight
        similarity = _similarity(a, b)
        if similarity >= 0.90:
            score += weight
            matched.append(label)
        elif similarity >= 0.70:
            score += weight * similarity
            matched.append(f"{label} (similar)")
    if available_weight <= 0:
        return 0.0, "No common explicit anchors available"
    normalized = min(1.0, score / available_weight)
    if not matched:
        return normalized, "No matching explicit anchors"
    return normalized, "Matched anchors: " + ", ".join(matched)


def build_document_relationships(document_profiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for i in range(len(document_profiles)):
        for j in range(i + 1, len(document_profiles)):
            left = document_profiles[i]
            right = document_profiles[j]
            score, reason = document_relationship_score(left, right)
            if score >= 0.55:
                candidates.append({
                    "Source Document": left.get("Source Report", f"Document {i + 1}"),
                    "Related Document": right.get("Source Report", f"Document {j + 1}"),
                    "Relationship Score": round(score * 100, 1),
                    "Relationship": "Candidate Link - Human Verification Required",
                    "Reason": reason,
                })
    candidates.sort(key=lambda item: item["Relationship Score"], reverse=True)
    return candidates
