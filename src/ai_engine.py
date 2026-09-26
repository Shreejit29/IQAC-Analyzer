from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .record_utils import COLUMNS, NAAC_ATTRIBUTES, normalize_record


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
12. If the document is image-based, read the page images visually. Handwritten attendance and feedback count as evidence.
13. Do not treat a newspaper clipping, photo or feedback form as a separate activity unless it clearly describes a
    separate event.
14. Do not create duplicate activities from repeated headers, feedback pages, photos or evidence pages.
15. NAAC/Binary mapping is a reference classification only. Do not claim an official NAAC score or accreditation result.
16. The output is for human verification. Be conservative when evidence is ambiguous.

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
Use the following draft Binary Accreditation framework as a REFERENCE CLASSIFICATION layer only.
It is not an official NAAC scoring calculator. Do not assign scores.

Choose an attribute/metric when the activity/report content provides a defensible match.
Do not leave these fields "Not Identified" merely because the report itself does not print a metric number.
Infer the classification from the actual activity content, objective, methodology, target group and evidence,
but do not invent facts about the activity.

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
(Use only when the report actually concerns faculty-resource matters.)

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

MAPPING DECISION RULES
- Prefer the most specific metric supported by the activity.
- A technical/domain mathematics activity may map to 6.1 when its content is a technical/domain activity.
- A cultural competition/event may map to 6.2.
- A sports activity may map to 6.5.
- A value/awareness activity may map to 6.4 when its primary purpose is value education.
- Community/outreach/UBA activities may map to 6.6 or 10.1 depending on whether the activity is primarily an extended-curricular/community engagement activity or a sustainability/green initiative.
- Teaching methodology, learning activities, assessment, internships and industry-linked learning should be considered under Attribute 5 with the relevant 5.x metric.
- Awards/recognitions should be considered under 8.5 when the report documents student awards/recognitions.
- IQAC, quality assurance, audits, stakeholder satisfaction, quality initiatives and related institutional QA activities should be considered under 7.6.
- Do not force a mapping when none of the documented metrics is actually supported. In that case use "Not Identified" and explain why in extraction_notes.
- Never invent a metric solely to avoid "Not Identified".
- Return the metric in the exact "number + title" form from this catalog, e.g. "6.1 Technical/Domain related Clubs, activities and technical festivals".

SOURCE DISCIPLINE
Every extracted value must be supported by the uploaded report. Do not use outside knowledge to fill missing values.

FINAL CLASSIFICATION CHECK
Before returning each activity, explicitly evaluate NAAC/Binary Attribute and Metric.
If the activity clearly matches one of the reference metrics above, populate both fields.
If it does not clearly match, use "Not Identified" and state the reason in extraction_notes.
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
    transient_terms = (
        "503", "service unavailable", "unavailable", "overloaded",
        "high demand", "temporarily unavailable", "deadline exceeded",
        "timeout", "timed out", "429", "resource exhausted",
        "too many requests", "500", "502", "504", "internal server error",
    )
    return any(term in message for term in transient_terms)


def _upload_and_analyze(
    raw: bytes,
    filename: str,
    model: str,
    api_key: str,
    max_retries: int = 3,
) -> ReportAnalysis:
    last_error: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            return _upload_and_analyze_once(raw, filename, model, api_key)
        except Exception as exc:
            last_error = exc
            if not _is_transient_gemini_error(exc) or attempt >= max_retries:
                if isinstance(exc, GeminiError):
                    raise
                raise GeminiError(
                    f"Gemini analysis failed for {filename}: {exc}"
                ) from exc
            time.sleep(2 if attempt == 1 else 5)

    raise GeminiError(
        f"Gemini analysis failed for {filename}: {last_error}"
    ) from last_error


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


def _map_activity(a: Activity, source_file: str, index: int, report_year: str) -> dict[str, str]:
    e = a.evidence
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
    }
    # Only allow known NAAC attributes.
    if mapped["NAAC Attribute"] not in NAAC_ATTRIBUTES:
        mapped["NAAC Attribute"] = "Not Identified"
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
