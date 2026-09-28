from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.record_utils import COLUMNS, normalize_record
from src.excel_exporter import build_excel_bytes
from src.ai_engine import ReportAnalysis, Activity, EvidenceItem, _strict_schema

sample = normalize_record(
    {
        "Activity Title": "Rakhi Making Competition",
        "Activity Date": "21/08/2026",
        "Organizing Department / Committee": "Department of Mathematics",
        "Objective": "To foster creativity in students.",
        "Outcome": "Students explored mathematical ideas through artwork.",
        "Documents Present": "Notice; Attendance; Event Report; Photographs",
        "Documents Absent": "Programme/Schedule; Feedback",
        "Academic Year": "2026-27",
        "Source Page": "1-14",
    },
    "Rakhi Making Competition Dept. of Mathematics.pdf", 1,
)

assert sample["Activity Title"] == "Rakhi Making Competition"
assert sample["Documents Present"].startswith("Notice")
assert "Documents Absent" in sample
assert len(COLUMNS) == 22

analysis = ReportAnalysis(
    academic_year="2026-27",
    activities=[Activity(
        activity_title="Rakhi Making Competition",
        activity_date="21/08/2026",
        evidence=[EvidenceItem(document="Notice", status="Present", source_page="1")],
    )],
)
assert analysis.activities[0].activity_title == "Rakhi Making Competition"
schema = _strict_schema()
assert schema["additionalProperties"] is False
assert schema["properties"]["activities"]["items"]["additionalProperties"] is False

xlsx = build_excel_bytes([sample])
assert xlsx[:2] == b"PK"
print("Smoke test passed.")
