from __future__ import annotations

import json
import os
import tempfile
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .record_utils import COLUMNS, NAAC_ATTRIBUTES, normalize_record


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

DOCUMENT CLASSIFICATION AND RELATIONSHIP INTELLIGENCE
17. Classify the uploaded file into exactly one document type from this controlled vocabulary:
    Activity Report, Activity Sheet / Basic Summary, Notice, Proposal, Attendance Sheet, Feedback Form,
    Feedback Analysis, Certificate, Circular, Invitation, Photographic Evidence, News / Publicity,
    Programme / Schedule, Appreciation Letter, Other Supporting Document, or Unknown.
18. Set is_primary_activity_document=true only when the document itself is an activity report or activity/basic
    summary that can legitimately create a master activity record. Notices, attendance sheets, feedback forms,
    photographs and other supporting documents normally have is_primary_activity_document=false.
19. Extract relationship anchors from the document when explicitly visible: activity title, date, activity number,
    academic year, department, committee, venue and collaborating agency. Use Not Identified when unavailable.
20. Supporting documents must not become separate activities merely because they contain the activity title, photos,
    participant names or repeated event details. If a supporting document contains evidence for an activity, keep
    activities empty unless it clearly documents a distinct additional activity.
21. If a file contains multiple distinct activities and is itself a primary activity report, return each distinct
    activity separately and use the document profile only for the strongest/common document-level anchor.
22. Use relationship_notes to state concise textual clues such as "same title/date as activity report" only when
    directly supported by the uploaded document. Do not invent a relationship to another uploaded file that you
    cannot see.
23. Relationship confidence describes confidence in the extracted anchors, not confidence that another uploaded
    file is actually the same activity. Cross-file matching will be performed separately from these anchors.

EVIDENCE STATUS
For each evidence type return exactly one of Present, Absent, or Unclear. Do not call an item Absent merely because
it was not obvious in a cropped image; use Unclear when the report cannot establish the status.

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


def _upload_and_analyze(raw: bytes, filename: str, model: str, api_key: str) -> ReportAnalysis:
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
    profile = result.document_profile
    # Keep the legacy top-level document_type usable while preferring the richer profile.
    document_type = profile.document_type if profile.document_type != "Unknown" else result.document_type
    if document_type not in DOCUMENT_TYPES:
        document_type = "Unknown"
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
    """Return a conservative cross-file relationship score and explanation.

    This helper never asserts that two files belong to the same activity. It only
    measures agreement among explicit document anchors for the later verification UI.
    """
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
    """Build candidate cross-document links for human verification.

    Only pairs with at least one explicit matching anchor are returned. The result is
    intentionally conservative: it is a candidate relationship, not an automatic merge.
    """
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
