from __future__ import annotations

from collections import Counter
from io import BytesIO
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.worksheet.datavalidation import DataValidation

from .record_utils import COLUMNS, EVIDENCE_FIELDS


HEADER_FILL = PatternFill("solid", fgColor="0F766E")
SUBHEADER_FILL = PatternFill("solid", fgColor="D9EDEB")
WARNING_FILL = PatternFill("solid", fgColor="FFF2CC")
ERROR_FILL = PatternFill("solid", fgColor="FCE4D6")
SUCCESS_FILL = PatternFill("solid", fgColor="E2F0D9")
WHITE_FONT = Font(bold=True, color="FFFFFF")
BOLD_FONT = Font(bold=True)


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _missing(value: Any) -> bool:
    v = _text(value).lower()
    return v in {"", "not identified", "not mentioned", "unknown", "n/a", "na", "none", "unclear"}


def _style_header(ws, row: int = 1) -> None:
    for cell in ws[row]:
        cell.fill = HEADER_FILL
        cell.font = WHITE_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[row].height = 38


def _add_table(ws, name: str, min_row: int = 1) -> None:
    if ws.max_row < min_row + 1 or ws.max_column < 1:
        return
    ref = f"A{min_row}:{get_column_letter(ws.max_column)}{ws.max_row}"
    table = Table(displayName=name, ref=ref)
    table.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium4",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False,
    )
    ws.add_table(table)


def _format_sheet(ws, widths: dict[str, float] | None = None, freeze: str = "A2") -> None:
    ws.freeze_panes = freeze
    ws.sheet_view.showGridLines = False
    for row in ws.iter_rows():
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    if widths:
        for col, width in widths.items():
            ws.column_dimensions[col].width = width


def _safe_table_name(value: str) -> str:
    cleaned = "".join(ch for ch in value if ch.isalnum())
    return cleaned[:200] or "IQACTable"


def _build_master_sheet(wb: Workbook, records: list[dict[str, Any]]) -> None:
    ws = wb.active
    ws.title = "IQAC_Master_Data"

    ws.append(COLUMNS)
    for rec in records:
        ws.append([_text(rec.get(c)) or "Not Identified" for c in COLUMNS])

    _style_header(ws)
    _format_sheet(ws, freeze="A2")

    # Make important review fields visually obvious.
    try:
        status_col = COLUMNS.index("Verification Status") + 1
        confidence_col = COLUMNS.index("Extraction Confidence") + 1
        missing_col = COLUMNS.index("Missing Information") + 1
        gap_col = COLUMNS.index("Evidence Gaps") + 1

        for row in range(2, ws.max_row + 1):
            status = _text(ws.cell(row, status_col).value).lower()
            confidence = _text(ws.cell(row, confidence_col).value).lower()
            if "possible duplicate" in status:
                ws.cell(row, status_col).fill = ERROR_FILL
            elif "verified" == status:
                ws.cell(row, status_col).fill = SUCCESS_FILL
            elif "needs verification" in status:
                ws.cell(row, status_col).fill = WARNING_FILL
            if "low" in confidence:
                ws.cell(row, confidence_col).fill = ERROR_FILL
            elif "medium" in confidence:
                ws.cell(row, confidence_col).fill = WARNING_FILL
            if _text(ws.cell(row, missing_col).value) not in {"", "None identified"}:
                ws.cell(row, missing_col).fill = WARNING_FILL
            if _text(ws.cell(row, gap_col).value) not in {"", "None identified"}:
                ws.cell(row, gap_col).fill = WARNING_FILL
    except ValueError:
        pass

    # Useful starting widths; remaining columns get a safe default.
    for i, column in enumerate(COLUMNS, 1):
        width = 22
        if column == "Record ID":
            width = 20
        elif column == "Activity Title":
            width = 36
        elif column in {"Objective", "Activity Description", "Outcome", "Impact", "Follow-up Action", "Feedback", "Missing Information", "Evidence Gaps"}:
            width = 42
        elif column in {"Source Report", "Evidence Link"}:
            width = 34
        elif column in {"NAAC Attribute", "NAAC Metric"}:
            width = 34
        ws.column_dimensions[get_column_letter(i)].width = width

    if records:
        _add_table(ws, "IQACMasterData")


def _build_verification_sheet(wb: Workbook, records: list[dict[str, Any]]) -> None:
    ws = wb.create_sheet("Verification_Queue")
    fields = [
        "Record ID", "Activity Date", "Activity Title", "Activity Type",
        "Organizing Department", "Organizing Committee", "NAAC Attribute", "NAAC Metric",
        "Missing Information", "Evidence Gaps", "Verification Status", "Extraction Confidence",
        "Source Report", "Source Page",
    ]
    ws.append(fields)

    for rec in records:
        status = _text(rec.get("Verification Status"))
        missing = _text(rec.get("Missing Information"))
        gaps = _text(rec.get("Evidence Gaps"))
        confidence = _text(rec.get("Extraction Confidence"))
        needs_review = (
            status.lower() != "verified"
            or (missing and missing != "None identified")
            or (gaps and gaps != "None identified")
            or "low" in confidence.lower()
            or "medium" in confidence.lower()
        )
        if needs_review:
            ws.append([_text(rec.get(f)) or "Not Identified" for f in fields])

    _style_header(ws)
    _format_sheet(ws)
    widths = {
        "A": 20, "B": 16, "C": 36, "D": 24, "E": 28, "F": 28,
        "G": 34, "H": 34, "I": 42, "J": 42, "K": 22, "L": 24,
        "M": 34, "N": 16,
    }
    _format_sheet(ws, widths)
    if ws.max_row > 1:
        _add_table(ws, "VerificationQueue")


def _build_naac_sheet(wb: Workbook, records: list[dict[str, Any]]) -> None:
    ws = wb.create_sheet("NAAC_Mapping")
    fields = [
        "Record ID", "Academic Year", "Activity Date", "Activity Title", "Activity Type",
        "Category", "Organizing Department", "NAAC Attribute", "NAAC Metric",
        "Objective", "Outcome", "Evidence Available", "Evidence Gaps", "Source Report", "Source Page",
        "Extraction Confidence", "Verification Status",
    ]
    ws.append(fields)
    for rec in records:
        ws.append([_text(rec.get(f)) or "Not Identified" for f in fields])

    _style_header(ws)
    _format_sheet(ws)
    widths = {"A": 20, "B": 16, "C": 16, "D": 36, "E": 24, "F": 24, "G": 28,
              "H": 36, "I": 34, "J": 42, "K": 42, "L": 40, "M": 42, "N": 34, "O": 16, "P": 24, "Q": 22}
    _format_sheet(ws, widths)
    if records:
        _add_table(ws, "NAACMapping")


def _build_evidence_sheet(wb: Workbook, records: list[dict[str, Any]]) -> None:
    ws = wb.create_sheet("Evidence_Register")
    fields = ["Record ID", "Academic Year", "Activity Date", "Activity Title", "Source Report", "Source Page"] + EVIDENCE_FIELDS
    ws.append(fields)
    for rec in records:
        row = [_text(rec.get(f)) or "Not Identified" for f in fields]
        ws.append(row)

    _style_header(ws)
    _format_sheet(ws)
    for i, field in enumerate(fields, 1):
        width = 24
        if field == "Activity Title":
            width = 36
        elif field == "Source Report":
            width = 34
        elif field in EVIDENCE_FIELDS:
            width = 20
        ws.column_dimensions[get_column_letter(i)].width = width

    if records:
        _add_table(ws, "EvidenceRegister")


def _build_quality_sheet(wb: Workbook, records: list[dict[str, Any]]) -> None:
    ws = wb.create_sheet("Data_Quality_Report")
    ws.append(["Record ID", "Activity Title", "Issue Type", "Severity", "Issue / Details", "Recommended Action", "Source Report"])

    for rec in records:
        rid = _text(rec.get("Record ID"))
        title = _text(rec.get("Activity Title")) or "Not Identified"
        source = _text(rec.get("Source Report")) or "Not Identified"

        missing = _text(rec.get("Missing Information"))
        if missing and missing != "None identified":
            ws.append([rid, title, "Missing Information", "High", missing, "Verify the source report and complete the missing fields.", source])

        gaps = _text(rec.get("Evidence Gaps"))
        if gaps and gaps != "None identified":
            ws.append([rid, title, "Evidence Gap", "Medium", gaps, "Check whether the evidence exists in the report or supporting files.", source])

        status = _text(rec.get("Verification Status"))
        if "possible duplicate" in status.lower():
            ws.append([rid, title, "Possible Duplicate", "High", status, "Compare with the suspected duplicate before finalizing the master register.", source])
        elif status and status.lower() != "verified":
            ws.append([rid, title, "Verification", "Medium", status, "Review and verify the extracted record.", source])

        confidence = _text(rec.get("Extraction Confidence"))
        if "low" in confidence.lower():
            ws.append([rid, title, "Low Confidence", "High", confidence, "Manually verify the complete record against the source document.", source])
        elif "medium" in confidence.lower():
            ws.append([rid, title, "Medium Confidence", "Medium", confidence, "Review important fields before final use.", source])

        if _missing(rec.get("NAAC Attribute")) or _missing(rec.get("NAAC Metric")):
            ws.append([rid, title, "NAAC Mapping", "Medium", "NAAC Attribute or Metric is not identified.", "Review the activity and confirm the applicable reference mapping.", source])

    _style_header(ws)
    _format_sheet(ws)
    widths = {"A": 20, "B": 36, "C": 24, "D": 14, "E": 52, "F": 52, "G": 34}
    _format_sheet(ws, widths)
    if ws.max_row > 1:
        _add_table(ws, "DataQualityReport")


def _build_summary_sheet(wb: Workbook, records: list[dict[str, Any]]) -> None:
    ws = wb.create_sheet("Summary", 0)
    ws.sheet_view.showGridLines = False

    total = len(records)
    verified = sum(_text(r.get("Verification Status")).lower() == "verified" for r in records)
    possible_dup = sum("possible duplicate" in _text(r.get("Verification Status")).lower() for r in records)
    needs_review = total - verified
    missing = sum(_text(r.get("Missing Information")) not in {"", "None identified"} for r in records)
    evidence_gaps = sum(_text(r.get("Evidence Gaps")) not in {"", "None identified"} for r in records)
    low_conf = sum("low" in _text(r.get("Extraction Confidence")).lower() for r in records)

    ws.append(["RTCCS IQAC Analyzer — Processing Summary", ""])
    ws.append([])
    ws.append(["Indicator", "Value"])
    metrics = [
        ("Total Activities", total),
        ("Verified Activities", verified),
        ("Records Requiring Review", needs_review),
        ("Possible Duplicates", possible_dup),
        ("Records With Missing Information", missing),
        ("Records With Evidence Gaps", evidence_gaps),
        ("Low-Confidence Records", low_conf),
    ]
    for label, value in metrics:
        ws.append([label, value])

    ws.append([])
    ws.append(["Activity Type", "Count"])
    activity_types = Counter(_text(r.get("Activity Type")) or "Not Identified" for r in records)
    for key, count in sorted(activity_types.items(), key=lambda x: (-x[1], x[0])):
        ws.append([key, count])

    ws.append([])
    ws.append(["NAAC Attribute", "Count"])
    attrs = Counter(_text(r.get("NAAC Attribute")) or "Not Identified" for r in records)
    for key, count in sorted(attrs.items(), key=lambda x: (-x[1], x[0])):
        ws.append([key, count])

    # Visual formatting for the title and metric blocks.
    ws[1][0].font = Font(bold=True, size=16)
    ws[3][0].fill = HEADER_FILL
    ws[3][1].fill = HEADER_FILL
    ws[3][0].font = WHITE_FONT
    ws[3][1].font = WHITE_FONT

    for row in ws.iter_rows(min_row=4):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)

    ws.column_dimensions["A"].width = 48
    ws.column_dimensions["B"].width = 24
    ws.freeze_panes = "A4"


def _build_readme_sheet(wb: Workbook) -> None:
    ws = wb.create_sheet("Read_Me")
    rows = [
        ["RTCCS IQAC Analyzer — Workbook Guide"],
        [],
        ["Sheet", "Purpose"],
        ["Summary", "High-level activity, verification, evidence and NAAC statistics for this export."],
        ["IQAC_Master_Data", "Primary activity register containing the configured IQAC master columns."],
        ["Verification_Queue", "Records that need human review because of status, confidence, missing information or evidence gaps."],
        ["NAAC_Mapping", "Activity-level NAAC attribute/metric reference mapping and supporting context."],
        ["Evidence_Register", "Evidence checklist for each activity record."],
        ["Data_Quality_Report", "Action-oriented list of missing information, evidence gaps, verification issues and mapping gaps."],
        [],
        ["Important", "NAAC mappings are a reference/AI-assistance layer and are not an official NAAC score or determination."],
        ["Important", "AI-extracted records should be verified by the responsible IQAC/department before official use."],
    ]
    for row in rows:
        ws.append(row)
    _style_header(ws, 3)
    ws[1][0].font = Font(bold=True, size=16)
    ws.column_dimensions["A"].width = 32
    ws.column_dimensions["B"].width = 110
    for row in ws.iter_rows():
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    ws.sheet_view.showGridLines = False


def build_excel_bytes(records: list[dict[str, Any]]) -> bytes:
    """Build the IQAC workbook while preserving the existing app API.

    The function intentionally keeps the original ``build_excel_bytes(records)``
    signature so app.py does not need another change for this upgrade.
    """
    wb = Workbook()

    _build_master_sheet(wb, records)
    _build_summary_sheet(wb, records)
    _build_verification_sheet(wb, records)
    _build_naac_sheet(wb, records)
    _build_evidence_sheet(wb, records)
    _build_quality_sheet(wb, records)
    _build_readme_sheet(wb)

    # Put the master register first, followed by the user-facing summary.
    wb._sheets = [wb["IQAC_Master_Data"], wb["Summary"], wb["Verification_Queue"], wb["NAAC_Mapping"], wb["Evidence_Register"], wb["Data_Quality_Report"], wb["Read_Me"]]

    out = BytesIO()
    wb.save(out)
    return out.getvalue()
