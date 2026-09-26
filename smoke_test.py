from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.record_utils import COLUMNS, EVIDENCE_FIELDS, normalize_record
from src.excel_exporter import build_excel_bytes

sample = normalize_record(
    {
        "Activity Title": "Rakhi Making Competition",
        "Activity Date": "21/08/2026",
        "Organizing Department": "Department of Mathematics",
        "Objective": "To foster creativity in mathematics through art.",
        "Outcome": "Students explored mathematical ideas through artwork.",
        "Proposal": "Present", "Notice": "Present", "Programme Table": "Absent",
        "Attendance": "Present", "Event Report": "Present", "Photographs": "Present",
        "Feedback Evidence": "Present", "Geotagged Photo": "Present", "News/Publicity": "Present",
        "Academic Year": "2026-27", "Source Page": "1-14",
    },
    "Rakhi Making Competition Dept. of Mathematics.pdf", 1,
)

assert sample["Programme Table"] == "Absent"
assert "Programme Table" in sample["Evidence Gaps"]
assert len(COLUMNS) > 40
xlsx = build_excel_bytes([sample])
assert xlsx[:2] == b"PK"
print("Smoke test passed.")
