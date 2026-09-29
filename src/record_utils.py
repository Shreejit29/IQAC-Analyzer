from __future__ import annotations

from typing import Any

COLUMNS = [
    "Record ID", "Academic Year", "Activity Date", "Activity Title", "Activity Type",
    "Category", "Organizing Department / Committee", "Collaborating Agency",
    "Resource Person", "Venue", "Participants", "Objective", "Activity Description",
    "Outcome", "Follow-up Action", "Feedback", "NAAC Attribute", "NAAC Metric",
    "Source Report", "Source Page",
]


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
