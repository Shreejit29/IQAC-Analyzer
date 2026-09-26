from __future__ import annotations

import json
import os
import tempfile
import time
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


class ReportAnalysis(BaseModel):
    document_type: str = "Not Identified"
    academic_year: str = "Not Identified"
    report_summary: str = "Not Identified"
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
    max_retries: int = 3,
) -> ReportAnalysis:
    # Prefer the configured model, then use the stable lightweight fallback.
    models_to_try = [model]
    if model != "gemini-3.5-flash-lite":
        models_to_try.append("gemini-3.5-flash-lite")

    last_error: Exception | None = None
    for selected_model in models_to_try:
        for attempt in range(1, max_retries + 1):
            try:
                result = _upload_and_analyze_once(raw, filename, selected_model, api_key)

                # An empty activity list is NOT immediately accepted. This was causing
                # activity reports to be reported as "No activities were extracted" even
                # though a fallback model was available. First run a focused recovery pass;
                # if that is still empty, continue to the next configured/fallback model.
                if not result.activities:
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


def _upload_and_analyze_once(raw: bytes, filename: str, model: str, api_key: str) -> ReportAnalysis:
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
            # Older/newer SDK variants may accept the file without an explicit config.
            remote_file = client.files.upload(file=temp_path)

        prompt = SYSTEM_PROMPT + f"\n\nSOURCE FILE NAME: {filename}\n\nAnalyze the complete uploaded document and return the structured report."
        response = client.models.generate_content(
            model=model,
            contents=[remote_file, prompt],
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
    except GeminiError:
        raise
    except Exception as exc:
        raise GeminiError(f"Gemini analysis failed for {filename}: {exc}") from exc
    finally:
        if remote_file is not None:
            try:
                client.files.delete(name=remote_file.name)
            except Exception:
                # Gemini automatically expires uploaded files; deletion is best-effort.
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
    meta = {
        "Document Type": result.document_type,
        "Academic Year": result.academic_year,
        "Summary": result.report_summary,
    }
    return records, meta
