from __future__ import annotations

from typing import Any

# Simple, practical output. No NAAC/evidence/verification metrics.
COLUMNS = [
    "Record ID",
    "Academic Year",
    "Activity Date",
    "Activity Title",
    "Activity Type",
    "Category",
    "Organizing Department / Committee",
    "Collaborating Agency",
    "Resource Person",
    "Venue",
    "Participants",
    "Objective",
    "Activity Description",
    "Outcome",
    "Follow-up Action",
    "Feedback",
    "Source Report",
    "Source Page",
]

MISSING = {"", "not identified", "not mentioned", "unknown", "n/a", "na", "none", "null", "-", "—"}


def clean(value: Any) -> str:
    if value is None:
        return "Not Identified"
    text = " ".join(str(value).split()).strip()
    return text if text else "Not Identified"


def normalize_record(record: dict[str, Any], source_report: str, index: int) -> dict[str, str]:
    out = {column: clean(record.get(column)) for column in COLUMNS}
    out["Record ID"] = f"IQAC-{index:04d}"
    out["Source Report"] = clean(source_report)
    return out


def session_summary(records: list[dict[str, Any]]) -> dict[str, int]:
    return {"activities": len(records)}
