"""
IQAC Analyzer - Professional Excel Exporter

Builds a multi-sheet, presentation-ready IQAC workbook while preserving
the public API: build_excel_bytes(records) -> bytes.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from io import BytesIO
from typing import Any, Dict, Iterable, List

from openpyxl import Workbook
from openpyxl.formatting.rule import CellIsRule, FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo


MASTER_COLUMNS = [
    "Record ID", "Academic Year", "Activity Date", "Activity Title",
    "Activity Type", "Category", "Organizing Department",
    "Organizing Committee", "Collaborating Agency", "Resource Person",
    "Resource Person Affiliation", "Venue", "Duration", "Target Group",
    "Total Participants", "Student Participants", "Faculty Participants",
    "External Participants", "Objective", "Activity Description",
    "Outcome", "Impact", "Follow-up Action", "Feedback",
    "Evidence Available", "Evidence Link", "NAAC Attribute", "NAAC Metric",
    "Quantitative Data", "Source Report", "Source Page",
    "Missing Information", "Extraction Status", "Verification Status",
    "Extraction Confidence",
]

DARK = "17365D"
MID = "2F75B5"
LIGHT = "D9EAF7"
PALE = "EEF5FB"
WHITE = "FFFFFF"
GREEN = "E2F0D9"
YELLOW = "FFF2CC"
RED = "FCE4D6"
GREY = "E7E6E6"
TEXT = "1F2937"
BORDER = "B7C9D6"

thin = Side(style="thin", color=BORDER)


def _s(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _confidence(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        n = float(value)
        if n > 1:
            n /= 100.0
        return max(0.0, min(1.0, n))
    except Exception:
        return None


def _records(records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [dict(r or {}) for r in records]


def _style_title(ws, title, subtitle=None, end_col=8):
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=end_col)
    c = ws.cell(1, 1, title)
    c.font = Font(name="Aptos Display", size=20, bold=True, color=WHITE)
    c.fill = PatternFill("solid", fgColor=DARK)
    c.alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[1].height = 34
    if subtitle:
        ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=end_col)
        c = ws.cell(2, 1, subtitle)
        c.font = Font(name="Aptos", size=10, italic=True, color="52606D")
        c.fill = PatternFill("solid", fgColor=PALE)
        c.alignment = Alignment(vertical="center")
        ws.row_dimensions[2].height = 22


def _style_header(row):
    for c in row:
        c.font = Font(name="Aptos", size=10, bold=True, color=WHITE)
        c.fill = PatternFill("solid", fgColor=MID)
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = Border(bottom=thin)
    row[0].parent.row_dimensions[row[0].row].height = 30


def _style_body(ws, start_row, end_row, start_col=1, end_col=None):
    if end_col is None:
        end_col = ws.max_column
    for row in ws.iter_rows(min_row=start_row, max_row=end_row,
                            min_col=start_col, max_col=end_col):
        for c in row:
            c.font = Font(name="Aptos", size=10, color=TEXT)
            c.alignment = Alignment(vertical="top", wrap_text=True)
            c.border = Border(bottom=thin)
        if row[0].row % 2 == 0:
            for c in row:
                c.fill = PatternFill("solid", fgColor="F7FAFC")


def _autofit(ws, min_width=10, max_width=42):
    for col in range(1, ws.max_column + 1):
        letter = get_column_letter(col)
        max_len = 0
        for cell in ws[letter]:
            value = "" if cell.value is None else str(cell.value)
            max_len = max(max_len, max((len(x) for x in value.splitlines()), default=0))
        ws.column_dimensions[letter].width = max(min_width, min(max_width, max_len + 2))


def _add_table(ws, ref, name):
    if ws.max_row < 2:
        return
    table = Table(displayName=name, ref=ref)
    table.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium2",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False,
    )
    ws.add_table(table)


def _issue_rows(records):
    rows = []
    for r in records:
        missing = _s(r.get("Missing Information"))
        status = _s(r.get("Verification Status"))
        conf = _confidence(r.get("Extraction Confidence"))
        issues = []
        if missing and missing.lower() not in {"none", "not identified", "n/a"}:
            issues.append("Missing information")
        if "duplicate" in status.lower():
            issues.append("Possible duplicate")
        if conf is not None and conf < 0.70:
            issues.append("Low extraction confidence")
        if _s(r.get("NAAC Attribute")).lower() in {"", "not identified"}:
            issues.append("NAAC attribute not identified")
        if _s(r.get("NAAC Metric")).lower() in {"", "not identified"}:
            issues.append("NAAC metric not identified")
        if issues:
            rows.append([
                _s(r.get("Record ID")),
                _s(r.get("Activity Title")),
                "; ".join(issues),
                missing,
                status,
                _s(r.get("Source Report")),
                _s(r.get("Source Page")),
                _s(r.get("Recommended Action")) or "Review record",
            ])
    return rows


def build_excel_bytes(records):
    records = _records(records)

    wb = Workbook()
    dashboard = wb.active
    dashboard.title = "IQAC Dashboard"

    # ---------- Dashboard ----------
    _style_title(
        dashboard,
        "RTCCS IQAC Analyzer",
        "Professional IQAC Activity & Evidence Workbook",
        8,
    )
    dashboard.sheet_view.showGridLines = False

    total = len(records)
    verified = sum(_s(r.get("Verification Status")).lower() == "verified" for r in records)
    duplicates = sum("duplicate" in _s(r.get("Verification Status")).lower() for r in records)
    needs_review = sum(
        _s(r.get("Verification Status")).lower() in {"needs verification", "possible duplicate"}
        or bool(_s(r.get("Missing Information")))
        for r in records
    )
    mapped = sum(
        _s(r.get("NAAC Attribute")).lower() not in {"", "not identified"}
        and _s(r.get("NAAC Metric")).lower() not in {"", "not identified"}
        for r in records
    )
    evidence = sum(bool(_s(r.get("Evidence Available"))) for r in records)

    cards = [
        ("Total Activities", total),
        ("Verified", verified),
        ("Needs Review", needs_review),
        ("Possible Duplicates", duplicates),
        ("NAAC Mapped", mapped),
        ("Evidence Recorded", evidence),
    ]

    row = 4
    for i, (label, value) in enumerate(cards):
        col = 1 + (i % 3) * 3
        r = row + (i // 3) * 3
        dashboard.merge_cells(start_row=r, start_column=col, end_row=r, end_column=col + 1)
        dashboard.merge_cells(start_row=r + 1, start_column=col, end_row=r + 1, end_column=col + 1)
        lc = dashboard.cell(r, col, label)
        vc = dashboard.cell(r + 1, col, value)
        lc.font = Font(size=10, bold=True, color=WHITE)
        lc.fill = PatternFill("solid", fgColor=MID)
        lc.alignment = Alignment(horizontal="center", vertical="center")
        vc.font = Font(size=20, bold=True, color=DARK)
        vc.fill = PatternFill("solid", fgColor=PALE)
        vc.alignment = Alignment(horizontal="center", vertical="center")
        dashboard.row_dimensions[r].height = 22
        dashboard.row_dimensions[r + 1].height = 32

    start = 11
    dashboard.cell(start, 1, "Activity Type Distribution")
    dashboard.cell(start, 1).font = Font(size=13, bold=True, color=DARK)
    type_counts = Counter(_s(r.get("Activity Type")) or "Not Identified" for r in records)
    dashboard.append([])
    hdr = dashboard.max_row + 1
    dashboard.cell(hdr, 1, "Activity Type")
    dashboard.cell(hdr, 2, "Activities")
    _style_header(dashboard[hdr])
    for k, v in type_counts.most_common():
        dashboard.append([k, v])
    _style_body(dashboard, hdr + 1, dashboard.max_row, 1, 2)

    attr_col = 4
    dashboard.cell(start, attr_col, "NAAC Attribute Distribution")
    dashboard.cell(start, attr_col).font = Font(size=13, bold=True, color=DARK)
    attr_counts = Counter(_s(r.get("NAAC Attribute")) or "Not Identified" for r in records)
    ah = hdr
    dashboard.cell(ah, attr_col, "NAAC Attribute")
    dashboard.cell(ah, attr_col + 1, "Activities")
    _style_header(dashboard[ah][attr_col-1:attr_col+1])
    for k, v in attr_counts.most_common():
        dashboard.cell(dashboard.max_row + 1, attr_col, k)
        dashboard.cell(dashboard.max_row, attr_col + 1, v)
    _style_body(dashboard, ah + 1, dashboard.max_row, attr_col, attr_col + 1)
    dashboard.freeze_panes = "A4"
    for c in range(1, 9):
        dashboard.column_dimensions[get_column_letter(c)].width = 22

    # ---------- Master Data ----------
    ws = wb.create_sheet("Master Activity Data")
    _style_title(ws, "IQAC Master Activity Data", "Validated activity register", len(MASTER_COLUMNS))
    header_row = 3
    for col, name in enumerate(MASTER_COLUMNS, 1):
        ws.cell(header_row, col, name)
    _style_header(ws[header_row])

    for r in records:
        ws.append([r.get(c, "") for c in MASTER_COLUMNS])

    if records:
        _style_body(ws, header_row + 1, ws.max_row)
        for row in ws.iter_rows(min_row=header_row + 1, max_row=ws.max_row):
            # confidence
            idx = MASTER_COLUMNS.index("Extraction Confidence") + 1
            c = row[idx - 1]
            n = _confidence(c.value)
            if n is not None:
                c.value = n
                c.number_format = "0%"
        _add_table(ws, f"A{header_row}:{get_column_letter(len(MASTER_COLUMNS))}{ws.max_row}", "IQACMasterData")

        # Status / confidence formatting
        status_col = MASTER_COLUMNS.index("Verification Status") + 1
        conf_col = MASTER_COLUMNS.index("Extraction Confidence") + 1
        ws.conditional_formatting.add(
            f"{get_column_letter(status_col)}{header_row+1}:{get_column_letter(status_col)}{ws.max_row}",
            FormulaRule(formula=[f'LOWER({get_column_letter(status_col)}{header_row+1})="verified"'],
                        fill=PatternFill("solid", fgColor=GREEN)),
        )
        ws.conditional_formatting.add(
            f"{get_column_letter(conf_col)}{header_row+1}:{get_column_letter(conf_col)}{ws.max_row}",
            CellIsRule(operator="lessThan", formula=["0.70"], fill=PatternFill("solid", fgColor=RED)),
        )

    ws.freeze_panes = "A4"
    ws.auto_filter.ref = f"A{header_row}:{get_column_letter(len(MASTER_COLUMNS))}{max(ws.max_row, header_row)}"
    _autofit(ws, 10, 38)
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.print_title_rows = "1:3"

    # ---------- Verification Queue ----------
    vq = wb.create_sheet("Verification Queue")
    cols = ["Record ID", "Activity Title", "Issue", "Missing Information",
            "Verification Status", "Source Report", "Source Page", "Recommended Action"]
    _style_title(vq, "Verification Queue", "Records requiring human review", len(cols))
    for i, c in enumerate(cols, 1):
        vq.cell(3, i, c)
    _style_header(vq[3])
    issues = _issue_rows(records)
    for row in issues:
        vq.append(row)
    if issues:
        _style_body(vq, 4, vq.max_row)
        _add_table(vq, f"A3:H{vq.max_row}", "VerificationQueue")
    vq.freeze_panes = "A4"
    _autofit(vq, 12, 45)

    # ---------- NAAC Mapping ----------
    nm = wb.create_sheet("NAAC Mapping")
    ncols = ["Record ID", "Activity Title", "Activity Type", "NAAC Attribute",
             "NAAC Metric", "Objective", "Outcome", "Evidence Available",
             "Source Report", "Source Page", "Extraction Confidence",
             "Verification Status"]
    _style_title(nm, "NAAC Mapping", "AI/reference mapping for IQAC review; not an official NAAC score", len(ncols))
    for i, c in enumerate(ncols, 1):
        nm.cell(3, i, c)
    _style_header(nm[3])
    for r in records:
        nm.append([
            _s(r.get("Record ID")), _s(r.get("Activity Title")),
            _s(r.get("Activity Type")), _s(r.get("NAAC Attribute")),
            _s(r.get("NAAC Metric")), _s(r.get("Objective")),
            _s(r.get("Outcome")), _s(r.get("Evidence Available")),
            _s(r.get("Source Report")), _s(r.get("Source Page")),
            _confidence(r.get("Extraction Confidence")),
            _s(r.get("Verification Status")),
        ])
    if records:
        _style_body(nm, 4, nm.max_row)
        for row in nm.iter_rows(min_row=4, max_row=nm.max_row):
            row[10].number_format = "0%"
        _add_table(nm, f"A3:L{nm.max_row}", "NAACMapping")
    nm.freeze_panes = "A4"
    _autofit(nm, 12, 48)

    # ---------- Evidence Register ----------
    er = wb.create_sheet("Evidence Register")
    ecols = ["Record ID", "Activity Title", "Evidence Available", "Evidence Link",
             "Source Report", "Source Page", "Verification Status"]
    _style_title(er, "Evidence Register", "Evidence traceability by activity", len(ecols))
    for i, c in enumerate(ecols, 1):
        er.cell(3, i, c)
    _style_header(er[3])
    for r in records:
        er.append([
            _s(r.get("Record ID")), _s(r.get("Activity Title")),
            _s(r.get("Evidence Available")), _s(r.get("Evidence Link")),
            _s(r.get("Source Report")), _s(r.get("Source Page")),
            _s(r.get("Verification Status")),
        ])
    if records:
        _style_body(er, 4, er.max_row)
        _add_table(er, f"A3:G{er.max_row}", "EvidenceRegister")
    er.freeze_panes = "A4"
    _autofit(er, 12, 50)

    # ---------- Data Quality ----------
    dq = wb.create_sheet("Data Quality")
    dcols = ["Record ID", "Activity Title", "Issue Type", "Details",
             "Severity", "Source Report", "Source Page", "Suggested Action"]
    _style_title(dq, "Data Quality Report", "Extraction, validation and verification issues", len(dcols))
    for i, c in enumerate(dcols, 1):
        dq.cell(3, i, c)
    _style_header(dq[3])

    for r in records:
        rid = _s(r.get("Record ID"))
        title = _s(r.get("Activity Title"))
        source = _s(r.get("Source Report"))
        page = _s(r.get("Source Page"))
        missing = _s(r.get("Missing Information"))
        conf = _confidence(r.get("Extraction Confidence"))
        if missing and missing.lower() not in {"none", "not identified", "n/a"}:
            dq.append([rid, title, "Missing Information", missing, "High", source, page, "Verify source document"])
        if "duplicate" in _s(r.get("Verification Status")).lower():
            dq.append([rid, title, "Possible Duplicate", _s(r.get("Verification Status")), "Medium", source, page, "Compare with matching record"])
        if conf is not None and conf < 0.70:
            dq.append([rid, title, "Low Confidence", f"Extraction confidence: {conf:.0%}", "Medium", source, page, "Review extracted fields"])
        if _s(r.get("NAAC Attribute")).lower() in {"", "not identified"}:
            dq.append([rid, title, "NAAC Mapping", "NAAC attribute not identified", "Medium", source, page, "Review NAAC reference mapping"])
        if _s(r.get("NAAC Metric")).lower() in {"", "not identified"}:
            dq.append([rid, title, "NAAC Mapping", "NAAC metric not identified", "Medium", source, page, "Review NAAC reference mapping"])
        if _s(r.get("Outcome")) and not _s(r.get("Impact")):
            dq.append([rid, title, "Impact Not Documented",
                       "Outcome is documented; long-term impact is not identified.", "Low", source, page,
                       "Do not infer impact; verify source if required"])

    if dq.max_row >= 4:
        _style_body(dq, 4, dq.max_row)
        _add_table(dq, f"A3:H{dq.max_row}", "DataQuality")
    dq.freeze_panes = "A4"
    _autofit(dq, 12, 48)

    # ---------- Field Traceability ----------
    ft = wb.create_sheet("Field Traceability")
    ft_cols = [
        "Record ID", "Activity Title", "Field", "Extracted Value",
        "Source Page", "Field Confidence", "Verification Status", "Source Report"
    ]
    _style_title(
        ft,
        "Field Traceability",
        "Field-level source pages and extraction confidence",
        len(ft_cols),
    )
    for i, c in enumerate(ft_cols, 1):
        ft.cell(3, i, c)
    _style_header(ft[3])

    for r in records:
        field_sources = r.get("Field Sources") or r.get("field_sources") or {}
        field_conf = r.get("Field Confidence") or r.get("field_confidence") or {}

        # Support either dictionaries or JSON-like strings where practical.
        if isinstance(field_sources, str):
            try:
                import json
                field_sources = json.loads(field_sources)
            except Exception:
                field_sources = {}
        if isinstance(field_conf, str):
            try:
                import json
                field_conf = json.loads(field_conf)
            except Exception:
                field_conf = {}

        if isinstance(field_sources, dict):
            fields = list(field_sources.keys())
        elif isinstance(field_conf, dict):
            fields = list(field_conf.keys())
        else:
            fields = []

        # If the AI did not return field-level metadata, retain a useful
        # record-level traceability row rather than inventing page numbers.
        if not fields:
            fields = ["Record-level extraction"]

        for field in fields:
            value = r.get(field, "")
            if value == "":
                # Try common normalized/case-insensitive field names.
                normalized = str(field).strip().lower().replace("_", " ")
                for key, candidate in r.items():
                    if str(key).strip().lower().replace("_", " ") == normalized:
                        value = candidate
                        break

            page = field_sources.get(field, "") if isinstance(field_sources, dict) else ""
            conf = field_conf.get(field, "") if isinstance(field_conf, dict) else ""
            n = _confidence(conf)

            ft.append([
                _s(r.get("Record ID")),
                _s(r.get("Activity Title")),
                _s(field),
                _s(value),
                _s(page),
                n,
                _s(r.get("Verification Status")),
                _s(r.get("Source Report")),
            ])

    if ft.max_row >= 4:
        _style_body(ft, 4, ft.max_row)
        for row in ft.iter_rows(min_row=4, max_row=ft.max_row):
            row[5].number_format = "0%"
        _add_table(ft, f"A3:H{ft.max_row}", "FieldTraceability")
        ft.conditional_formatting.add(
            f"F4:F{ft.max_row}",
            CellIsRule(
                operator="lessThan",
                formula=["0.70"],
                fill=PatternFill("solid", fgColor=RED),
            ),
        )
    ft.freeze_panes = "A4"
    _autofit(ft, 12, 48)

    # ---------- Field Confidence Summary ----------
    fc = wb.create_sheet("Field Confidence")
    fc_cols = ["Record ID", "Activity Title", "Field", "Confidence", "Source Page", "Review Status"]
    _style_title(
        fc,
        "Field Confidence",
        "Field-level extraction confidence for review prioritization",
        len(fc_cols),
    )
    for i, c in enumerate(fc_cols, 1):
        fc.cell(3, i, c)
    _style_header(fc[3])

    for r in records:
        field_conf = r.get("Field Confidence") or r.get("field_confidence") or {}
        field_sources = r.get("Field Sources") or r.get("field_sources") or {}

        if isinstance(field_conf, str):
            try:
                import json
                field_conf = json.loads(field_conf)
            except Exception:
                field_conf = {}
        if isinstance(field_sources, str):
            try:
                import json
                field_sources = json.loads(field_sources)
            except Exception:
                field_sources = {}

        if isinstance(field_conf, dict) and field_conf:
            for field, conf in field_conf.items():
                n = _confidence(conf)
                page = field_sources.get(field, "") if isinstance(field_sources, dict) else ""
                status = "Review" if n is not None and n < 0.70 else "OK"
                fc.append([
                    _s(r.get("Record ID")),
                    _s(r.get("Activity Title")),
                    _s(field),
                    n,
                    _s(page),
                    status,
                ])

    if fc.max_row >= 4:
        _style_body(fc, 4, fc.max_row)
        for row in fc.iter_rows(min_row=4, max_row=fc.max_row):
            row[3].number_format = "0%"
        _add_table(fc, f"A3:F{fc.max_row}", "FieldConfidence")
        fc.conditional_formatting.add(
            f"D4:D{fc.max_row}",
            CellIsRule(
                operator="lessThan",
                formula=["0.70"],
                fill=PatternFill("solid", fgColor=RED),
            ),
        )
        fc.conditional_formatting.add(
            f"D4:D{fc.max_row}",
            CellIsRule(
                operator="greaterThanOrEqual",
                formula=["0.90"],
                fill=PatternFill("solid", fgColor=GREEN),
            ),
        )
    fc.freeze_panes = "A4"
    _autofit(fc, 12, 44)

    # ---------- Read Me ----------
    rm = wb.create_sheet("Read Me", 0)
    _style_title(rm, "IQAC Analyzer — Workbook Guide",
                 "How to interpret and use the generated workbook", 6)
    instructions = [
        ("Purpose", "This workbook consolidates extracted IQAC activity information from uploaded reports."),
        ("Master Activity Data", "Primary activity register. Review before treating extracted values as final."),
        ("Verification Queue", "Records with missing information, possible duplicates, low confidence or mapping gaps."),
        ("NAAC Mapping", "Reference/AI-assisted mapping against the configured metric catalogue. It is not an official NAAC score or determination."),
        ("Evidence Register", "Tracks evidence availability and source traceability."),
        ("Data Quality", "Lists extraction and validation issues requiring attention."),
        ("Confidence", "Extraction confidence is a data-quality indicator and should be reviewed alongside source evidence."),
        ("Outcome vs Impact", "An undocumented impact is not inferred from an activity outcome."),
        ("Recommended workflow", "Review flagged records, verify against source pages, then mark records as Verified."),
    ]
    rm.cell(4, 1, "Section")
    rm.cell(4, 2, "Guidance")
    _style_header(rm[4][:2])
    for a, b in instructions:
        rm.append([a, b])
    _style_body(rm, 5, rm.max_row, 1, 2)
    rm.column_dimensions["A"].width = 28
    rm.column_dimensions["B"].width = 100
    rm.freeze_panes = "A5"

    # Global print settings
    for ws in wb.worksheets:
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.sheet_view.showGridLines = False
        ws.sheet_properties.outlinePr.summaryBelow = True
        ws.page_margins.left = 0.25
        ws.page_margins.right = 0.25
        ws.page_margins.top = 0.5
        ws.page_margins.bottom = 0.5

    output = BytesIO()
    wb.save(output)
    return output.getvalue()
