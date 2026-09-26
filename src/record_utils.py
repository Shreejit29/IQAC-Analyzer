from __future__ import annotations

import re
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any

# Final master register. Keep these column names stable because the Streamlit UI,
# Excel exporter and existing GitHub workflow depend on them.
COLUMNS = [
    "Record ID", "Academic Year", "Activity Date", "Activity Title", "Activity Type",
    "Category", "Organizing Department", "Organizing Committee", "Collaborating Agency",
    "Resource Person", "Resource Person Affiliation", "Venue", "Duration", "Target Group",
    "Total Participants", "Student Participants", "Faculty Participants", "External Participants",
    "Objective", "Activity Description", "Outcome", "Impact", "Follow-up Action", "Feedback",
    "Evidence Available", "Evidence Link", "Proposal", "Notice", "Programme Table",
    "Invitation", "Appreciation Letter", "Attendance", "Event Report", "Photographs",
    "Geotagged Photo", "Feedback Evidence", "News/Publicity", "Certificates", "Other Evidence",
    "NAAC Attribute", "NAAC Metric", "Quantitative Data", "Source Report", "Source Page",
    "Activity Summary Pages", "Missing Information", "Evidence Gaps", "Extraction Status",
    "Verification Status", "Extraction Confidence",
]

NAAC_ATTRIBUTES = [
    "Curriculum Design",
    "Faculty Resources",
    "Infrastructure",
    "Financial Resources & Management",
    "Learning & Teaching",
    "Extended Curricular Engagements",
    "Governance and Administration",
    "Student Outcomes",
    "Research & Innovation Outcomes",
    "Sustainability Outcomes (Including Green Initiatives)",
    "Not Identified",
]

EVIDENCE_FIELDS = [
    "Proposal", "Notice", "Programme Table", "Invitation", "Appreciation Letter",
    "Attendance", "Event Report", "Photographs", "Geotagged Photo", "Feedback Evidence",
    "News/Publicity", "Certificates", "Other Evidence",
]

# These fields are the minimum useful activity identity/content fields.
# They are used for data-quality reporting, not as hard validity requirements.
CORE_ACTIVITY_FIELDS = [
    "Activity Title", "Activity Date", "Organizing Department", "Objective", "Outcome",
]

# Additional fields improve confidence but should not make an otherwise valid activity fail.
SUPPORTING_CONFIDENCE_FIELDS = [
    "Activity Type", "Organizing Committee", "Venue", "Total Participants",
    "Source Page", "NAAC Attribute", "NAAC Metric",
]

_MISSING_VALUES = {
    "", "not identified", "not mentioned", "unknown", "n/a", "na", "none",
    "null", "-", "—",
}


def _norm(value: Any) -> str:
    value = "" if value is None else str(value)
    value = value.replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", value).strip().lower()


def _is_missing(value: Any) -> bool:
    return _norm(value) in _MISSING_VALUES


def _clean_for_similarity(value: Any) -> str:
    text = _norm(value)
    if text in _MISSING_VALUES:
        return ""
    # Remove punctuation while preserving words. This makes comparisons robust to
    # harmless differences such as "Tree Plantation Drive" vs "Tree Plantation-Drive".
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _similarity(a: Any, b: Any) -> float:
    left = _clean_for_similarity(a)
    right = _clean_for_similarity(b)
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def _date_key(value: Any) -> str:
    """Return a normalized date key for common Indian/institutional date formats."""
    text = _norm(value)
    if not text:
        return ""

    # Try common explicit date formats first.
    formats = (
        "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
        "%d/%m/%y", "%d-%m-%y", "%d.%m.%y",
        "%Y/%m/%d", "%Y-%m-%d", "%Y.%m.%d",
    )
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass

    # Extract a date from text such as "05/06/2025, 10.30 am onwards".
    match = re.search(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})\b", text)
    if match:
        day, month, year = match.groups()
        if len(year) == 2:
            year = "20" + year
        try:
            return datetime(int(year), int(month), int(day)).date().isoformat()
        except ValueError:
            return ""
    return ""


def _evidence_gap_fields(record: dict[str, Any]) -> list[str]:
    gaps: list[str] = []
    for field in EVIDENCE_FIELDS:
        status = _norm(record.get(field))
        # "Absent" is a real evidence status, so it belongs in the gap report.
        if status in {"", "not identified", "not mentioned", "unknown", "unclear", "absent"}:
            gaps.append(field)
    return gaps


def _calculate_confidence(record: dict[str, Any]) -> str:
    """Calculate extraction confidence deterministically from observed fields.

    Gemini is not allowed to invent a confidence score. The score is based only on
    whether useful fields were actually extracted and whether source traceability /
    NAAC classification are present.
    """
    # Core fields carry most of the score because they establish that an activity exists.
    weights = {
        "Activity Title": 20,
        "Activity Date": 15,
        "Organizing Department": 10,
        "Objective": 10,
        "Outcome": 10,
        "Activity Type": 5,
        "Organizing Committee": 5,
        "Venue": 5,
        "Total Participants": 5,
        "Source Page": 5,
        "NAAC Attribute": 5,
        "NAAC Metric": 5,
    }

    score = sum(weight for field, weight in weights.items() if not _is_missing(record.get(field)))

    # Evidence presence is useful supporting information, but it must not overpower
    # the activity identity/content fields.
    evidence_present = sum(_norm(record.get(field)) == "present" for field in EVIDENCE_FIELDS)
    score += min(5, evidence_present)
    score = min(100, score)

    if score >= 85:
        return f"High — {score}% — verify"
    if score >= 65:
        return f"Medium — {score}% — verify"
    return f"Low — {score}% — verify"


def normalize_record(
    record: dict[str, Any],
    source_file: str,
    index: int,
    source_page_hint: str = "Not Identified",
) -> dict[str, str]:
    """Normalize an AI activity into the stable master-register schema."""
    out: dict[str, str] = {}
    for field in COLUMNS:
        value = record.get(field, "Not Identified")
        if value is None or not str(value).strip():
            value = "Not Identified"
        out[field] = str(value).strip()

    out["Source Report"] = source_file
    if _is_missing(out["Source Page"]):
        out["Source Page"] = source_page_hint
    if _is_missing(out["Academic Year"]):
        out["Academic Year"] = "Not Identified"

    # IDs are reassigned after the full batch is known. This keeps them stable and
    # sequential after duplicate checking without changing the public API.
    out["Record ID"] = f"{source_file}::ACT-{index:03d}"
    out["Extraction Status"] = "AI Extracted"
    out["Verification Status"] = "Needs Verification"

    missing = [field for field in CORE_ACTIVITY_FIELDS if _is_missing(out.get(field))]
    out["Missing Information"] = "; ".join(missing) if missing else "None identified"

    gaps = _evidence_gap_fields(out)
    out["Evidence Gaps"] = "; ".join(gaps) if gaps else "None identified"

    if out["NAAC Attribute"] not in NAAC_ATTRIBUTES:
        out["NAAC Attribute"] = "Not Identified"

    # NAAC Metric is intentionally not hard-coded here. The AI engine's mapping
    # catalog/fallback is responsible for classification; this layer only records it.
    out["Extraction Confidence"] = _calculate_confidence(out)
    return out


def _duplicate_similarity(a: dict[str, Any], b: dict[str, Any]) -> tuple[bool, float]:
    """Return whether two records are strong duplicate candidates plus a score.

    We deliberately prefer false negatives over false positives. A human reviewer
    should see a candidate rather than having a legitimate activity removed.
    """
    title_similarity = _similarity(a.get("Activity Title"), b.get("Activity Title"))
    if title_similarity < 0.88:
        return False, title_similarity

    date_a = _date_key(a.get("Activity Date"))
    date_b = _date_key(b.get("Activity Date"))
    same_date = bool(date_a and date_b and date_a == date_b)

    dept_similarity = _similarity(a.get("Organizing Department"), b.get("Organizing Department"))
    venue_similarity = _similarity(a.get("Venue"), b.get("Venue"))
    committee_similarity = _similarity(a.get("Organizing Committee"), b.get("Organizing Committee"))

    # Same source + very similar title is a strong signal that Gemini repeated the
    # same activity while reading evidence pages.
    same_source = _norm(a.get("Source Report")) == _norm(b.get("Source Report"))
    if same_source and title_similarity >= 0.90 and (same_date or not date_a or not date_b):
        return True, title_similarity

    # Across different reports, require stronger corroboration to avoid suppressing
    # genuinely recurring activities.
    if same_date and title_similarity >= 0.90 and max(dept_similarity, committee_similarity, venue_similarity) >= 0.70:
        return True, (title_similarity + max(dept_similarity, committee_similarity, venue_similarity)) / 2

    # Extremely similar title + same date is still worth human review even when
    # department/venue information is missing.
    if same_date and title_similarity >= 0.96:
        return True, title_similarity

    return False, title_similarity


def deduplicate_records(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Flag likely duplicates instead of silently deleting them.

    Existing callers expect this function to return (records, count), so the API is
    unchanged. The important behavioral improvement is that suspected duplicates are
    retained in the master data and marked for human verification.
    """
    kept = list(records)
    duplicate_count = 0

    # Clear only the duplicate flag generated by this function; preserve any other
    # verification decision made by a user if the function is called again.
    for rec in kept:
        if rec.get("Verification Status") == "Possible Duplicate":
            rec["Verification Status"] = "Needs Verification"

    for i, rec in enumerate(kept):
        for old in kept[:i]:
            is_duplicate, similarity = _duplicate_similarity(rec, old)
            if is_duplicate:
                rec["Verification Status"] = "Possible Duplicate"
                rec["Duplicate Of"] = old.get("Record ID", "Not Identified")
                rec["Duplicate Similarity"] = f"{round(similarity * 100)}%"
                duplicate_count += 1
                break

    # Reassign clean batch IDs. Do not include source filenames in IDs because the
    # final workbook should have simple, portable identifiers.
    for i, rec in enumerate(kept, 1):
        rec["Record ID"] = f"ACT-{i:04d}"

    return kept, duplicate_count


def session_summary(records: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "activities": len(records),
        "needs_verification": sum(r.get("Verification Status") == "Needs Verification" for r in records),
        "missing_information": sum(
            not _is_missing(r.get("Missing Information"))
            and r.get("Missing Information") != "None identified"
            for r in records
        ),
        "evidence_gaps": sum(
            not _is_missing(r.get("Evidence Gaps"))
            and r.get("Evidence Gaps") != "None identified"
            for r in records
        ),
        "possible_duplicates": sum(r.get("Verification Status") == "Possible Duplicate" for r in records),
    }
