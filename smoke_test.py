from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.ai_engine import Activity, EvidenceItem, ReportAnalysis, _response_schema
from src.excel_exporter import build_excel_bytes
from src.record_utils import COLUMNS, normalize_record

sample = normalize_record(
    {
        "Activity Title": "AI and Robotics Workshop",
        "Activity Date": "26/09/2026",
        "Organizing Department / Committee": "Department of Physics",
        "Objective": "Introduce students to AI and robotics applications.",
        "Outcome": "Students gained exposure to basic robotics concepts.",
        "Documents Present": "Notice (p. 2); Attendance (p. 5-7); Event Report (p. 8)",
        "Documents Absent": "Invitation; Feedback; Certificate",
        "Academic Year": "2026-27",
        "Source Page": "1-9",
    },
    "AI and Robotics Workshop.pdf",
    1,
)

assert sample["Activity Title"] == "AI and Robotics Workshop"
assert sample["Documents Present"].startswith("Notice")
assert "Documents Absent" in sample
assert len(COLUMNS) == 22

analysis = ReportAnalysis(
    academic_year="2026-27",
    activities=[
        Activity(
            activity_title="AI and Robotics Workshop",
            activity_date="26/09/2026",
            evidence=[
                EvidenceItem(document="Notice", status="Present", source_page="2"),
                EvidenceItem(document="Attendance", status="Present", source_page="5-7"),
            ],
        )
    ],
)
assert analysis.activities[0].activity_title == "AI and Robotics Workshop"
schema = _response_schema()
assert schema["additionalProperties"] is False
activity_schema = schema.get("$defs", {}).get("Activity", {})
assert activity_schema.get("additionalProperties") is False

xlsx = build_excel_bytes([sample])
assert xlsx[:2] == b"PK"
print("Smoke test passed.")
