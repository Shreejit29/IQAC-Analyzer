from __future__ import annotations

"""IQAC cross-record validation helpers.

This module is intentionally independent from Streamlit and Gemini.  It can be
called after AI extraction and before Excel export.  It does not delete records
or silently change extracted facts; it adds review flags and validation notes.
"""

import re
from difflib import SequenceMatcher
from typing import Any

MISSING = {"", "not identified", "not mentioned", "unknown", "n/a", "na", "none", "null"}


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", "" if value is None else str(value)).strip().lower()


def _missing(value: Any) -> bool:
    return _norm(value) in MISSING


def _similar(a: Any, b: Any, threshold: float = 0.88) -> bool:
    a, b = _norm(a), _norm(b)
    if not a or not b or a in MISSING or b in MISSING:
        return False
    return SequenceMatcher(None, a, b).ratio() >= threshold


def _number(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).replace(",", "")
    # Accept values such as "72", "72 participants", or "72 students".
    match = re.search(r"(?<!\d)(\d{1,6})(?!\d)", text)
    return int(match.group(1)) if match else None


def _add_issue(record: dict[str, Any], issue: str, severity: str = "Medium") -> None:
    existing = str(record.get("Data Quality Issues", "")).strip()
    item = f"{severity}: {issue}"
    if not existing or existing in MISSING or existing == "None identified":
        record["Data Quality Issues"] = item
    elif item not in existing:
        record["Data Quality Issues"] = existing + "; " + item


def _append_missing(record: dict[str, Any], field: str) -> None:
    current = str(record.get("Missing Information", "")).strip()
    if current in MISSING or current == "None identified":
        record["Missing Information"] = field
    elif field not in current.split("; "):
        record["Missing Information"] = current + "; " + field


def _append_evidence_gap(record: dict[str, Any], field: str) -> None:
    current = str(record.get("Evidence Gaps", "")).strip()
    if current in MISSING or current == "None identified":
        record["Evidence Gaps"] = field
    elif field not in current.split("; "):
        record["Evidence Gaps"] = current + "; " + field


def validate_record(record: dict[str, Any]) -> dict[str, Any]:
    """Run conservative validation on one extracted activity record."""
    out = record

    # Critical fields: do not invent values; flag them for human verification.
    critical = ["Activity Title", "Activity Date", "Organizing Department"]
    for field in critical:
        if _missing(out.get(field)):
            _append_missing(out, field)
            _add_issue(out, f"Missing critical field: {field}", "High")

    # Outcome/impact distinction. An absent impact is not an error; it is simply
    # a documentation gap. We never manufacture an impact from an outcome.
    if _missing(out.get("Outcome")):
        _append_missing(out, "Outcome")
        _add_issue(out, "Outcome is not documented", "Medium")

    if _missing(out.get("Impact")):
        _add_issue(out, "Long-term impact is not documented; do not infer it from outcome", "Low")

    # Basic participant consistency inside one extracted record.
    total = _number(out.get("Total Participants"))
    student = _number(out.get("Student Participants"))
    faculty = _number(out.get("Faculty Participants"))
    external = _number(out.get("External Participants"))
    parts = [x for x in (student, faculty, external) if x is not None]
    if total is not None and parts and sum(parts) > total:
        _add_issue(
            out,
            f"Participant subtotal ({sum(parts)}) exceeds reported total ({total})",
            "High",
        )

    # Preserve an explicit verification state. Validation never marks an
    # unreviewed record as verified.
    status = str(out.get("Verification Status", "Needs Verification"))
    if status in {"", "AI Extracted", "Not Identified"}:
        out["Verification Status"] = "Needs Verification"

    if out.get("Data Quality Issues") and out.get("Verification Status") == "Verified":
        out["Verification Status"] = "Needs Verification"

    return out


def _activity_key(record: dict[str, Any]) -> tuple[str, str]:
    return _norm(record.get("Activity Title")), _norm(record.get("Activity Date"))


def validate_cross_document(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Validate extracted records against one another.

    Returns:
        (updated_records, issue_rows)

    The function keeps all records. Potential duplicates and conflicts are
    flagged rather than removed.
    """
    updated = [validate_record(dict(r)) for r in records]
    issues: list[dict[str, Any]] = []

    for i in range(len(updated)):
        a = updated[i]
        title_a = a.get("Activity Title")
        if _missing(title_a):
            continue

        for j in range(i + 1, len(updated)):
            b = updated[j]
            title_b = b.get("Activity Title")
            if _missing(title_b):
                continue

            same_title = _similar(title_a, title_b, 0.90)
            date_a, date_b = a.get("Activity Date"), b.get("Activity Date")
            same_date = _missing(date_a) or _missing(date_b) or _norm(date_a) == _norm(date_b)

            if not same_title or not same_date:
                continue

            ida = a.get("Record ID", f"Record {i + 1}")
            idb = b.get("Record ID", f"Record {j + 1}")
            source_a = a.get("Source Report", "Not Identified")
            source_b = b.get("Source Report", "Not Identified")

            # Same activity represented in two files. Keep both records because
            # they may contain complementary evidence, but flag them.
            if _norm(source_a) != _norm(source_b):
                msg = f"Possible duplicate activity: {ida} and {idb}"
                _add_issue(a, msg, "Medium")
                _add_issue(b, msg, "Medium")
                if a.get("Verification Status") != "Verified":
                    a["Verification Status"] = "Possible Duplicate"
                if b.get("Verification Status") != "Verified":
                    b["Verification Status"] = "Possible Duplicate"
                issues.append({
                    "Issue Type": "Possible Duplicate",
                    "Severity": "Medium",
                    "Record A": ida,
                    "Record B": idb,
                    "Description": msg,
                    "Source A": source_a,
                    "Source B": source_b,
                })

            # Compare factual fields only when both records actually contain a
            # value. Missing data should not create a false contradiction.
            comparisons = [
                ("Organizing Department", "Department differs between reports"),
                ("Organizing Committee", "Committee differs between reports"),
                ("Venue", "Venue differs between reports"),
                ("Academic Year", "Academic year differs between reports"),
            ]
            for field, description in comparisons:
                va, vb = a.get(field), b.get(field)
                if not _missing(va) and not _missing(vb) and not _similar(va, vb, 0.80):
                    issue = {
                        "Issue Type": "Cross-document Inconsistency",
                        "Severity": "High" if field in {"Activity Date", "Academic Year"} else "Medium",
                        "Record A": ida,
                        "Record B": idb,
                        "Description": f"{description}: '{va}' vs '{vb}'",
                        "Source A": source_a,
                        "Source B": source_b,
                    }
                    issues.append(issue)
                    _add_issue(a, issue["Description"], issue["Severity"])
                    _add_issue(b, issue["Description"], issue["Severity"])

            # Participant count conflict.
            pa = _number(a.get("Total Participants"))
            pb = _number(b.get("Total Participants"))
            if pa is not None and pb is not None and pa != pb:
                description = f"Reported total participants differ: {pa} vs {pb}"
                issue = {
                    "Issue Type": "Quantitative Inconsistency",
                    "Severity": "High",
                    "Record A": ida,
                    "Record B": idb,
                    "Description": description,
                    "Source A": source_a,
                    "Source B": source_b,
                }
                issues.append(issue)
                _add_issue(a, description, "High")
                _add_issue(b, description, "High")

    # Any issue means the record needs review unless it has already been
    # explicitly verified by a human after the issue was resolved.
    for rec in updated:
        if rec.get("Data Quality Issues") and rec.get("Verification Status") != "Verified":
            if rec.get("Verification Status") not in {"Possible Duplicate"}:
                rec["Verification Status"] = "Needs Verification"

    return updated, issues


def validation_summary(records: list[dict[str, Any]], issues: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "records_checked": len(records),
        "records_with_issues": sum(bool(r.get("Data Quality Issues")) for r in records),
        "high_severity_issues": sum(i.get("Severity") == "High" for i in issues),
        "possible_duplicates": sum(i.get("Issue Type") == "Possible Duplicate" for i in issues),
        "quantitative_inconsistencies": sum(i.get("Issue Type") == "Quantitative Inconsistency" for i in issues),
        "cross_document_inconsistencies": sum(i.get("Issue Type") == "Cross-document Inconsistency" for i in issues),
    }
