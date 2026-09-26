from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

# Final one-sheet master register. The evidence checklist is intentionally explicit
# because real IQAC reports may contain some supporting documents but not others.
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
    "Activity Summary Pages", "Evidence Trace", "Evidence Present Count", "Evidence Trace Details",
    "Missing Information", "Evidence Gaps", "Extraction Status",
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

# These are useful for review, not hard validity requirements. A report may omit
# any one of these and still be a valid activity record.
CORE_ACTIVITY_FIELDS = [
    "Activity Title", "Activity Date", "Organizing Department", "Objective", "Outcome",
]


def _norm(value: Any) -> str:
    value = "" if value is None else str(value)
    return re.sub(r"\s+", " ", value).strip().lower()


def _is_missing(value: Any) -> bool:
    return _norm(value) in {"", "not identified", "not mentioned", "unknown", "n/a", "na", "none"}


def normalize_record(record: dict[str, Any], source_file: str, index: int, source_page_hint: str = "Not Identified") -> dict[str, str]:
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
    out["Record ID"] = f"{source_file}::ACT-{index:03d}"
    out["Extraction Status"] = "AI Extracted"
    out["Verification Status"] = "Needs Verification"

    missing = [field for field in CORE_ACTIVITY_FIELDS if _is_missing(out.get(field))]
    out["Missing Information"] = "; ".join(missing) if missing else "None identified"

    missing_evidence = [field for field in EVIDENCE_FIELDS if _norm(out.get(field)) in {"not identified", "not mentioned", "unknown", "", "absent", "unclear"}]
    out["Evidence Gaps"] = "; ".join(missing_evidence) if missing_evidence else "None identified"

    identified = len(CORE_ACTIVITY_FIELDS) - len(missing)
    if identified == len(CORE_ACTIVITY_FIELDS):
        out["Extraction Confidence"] = "High — verify"
    elif identified >= 3:
        out["Extraction Confidence"] = "Medium — verify"
    else:
        out["Extraction Confidence"] = "Low — verify"

    if out["NAAC Attribute"] not in NAAC_ATTRIBUTES:
        out["NAAC Attribute"] = "Not Identified"
    return out


def _same_activity(a: dict[str, Any], b: dict[str, Any]) -> bool:
    ta, tb = _norm(a.get("Activity Title")), _norm(b.get("Activity Title"))
    if not ta or ta == "not identified" or not tb or tb == "not identified":
        return False
    da, db = _norm(a.get("Activity Date")), _norm(b.get("Activity Date"))
    sa, sb = _norm(a.get("Source Report")), _norm(b.get("Source Report"))
    if sa != sb:
        return False
    if da and db and da != "not identified" and db != "not identified" and da != db:
        return False
    ratio = SequenceMatcher(None, ta, tb).ratio()
    return ratio >= 0.93


def deduplicate_records(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    kept: list[dict[str, Any]] = []
    duplicates = 0
    for rec in records:
        if any(_same_activity(rec, old) for old in kept):
            duplicates += 1
            continue
        kept.append(rec)
    for i, rec in enumerate(kept, 1):
        rec["Record ID"] = f"ACT-{i:04d}"
    return kept, duplicates


def session_summary(records: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "activities": len(records),
        "needs_verification": sum(r.get("Verification Status") == "Needs Verification" for r in records),
        "missing_information": sum(not _is_missing(r.get("Missing Information")) and r.get("Missing Information") != "None identified" for r in records),
        "evidence_gaps": sum(not _is_missing(r.get("Evidence Gaps")) and r.get("Evidence Gaps") != "None identified" for r in records),
        "possible_duplicates": sum(r.get("Verification Status") == "Possible Duplicate" for r in records),
    }
