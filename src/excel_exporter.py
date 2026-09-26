from __future__ import annotations

from io import BytesIO
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

from .record_utils import COLUMNS


def build_excel_bytes(records: list[dict[str, Any]]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "IQAC_Master_Data"

    ws.append(COLUMNS)
    for rec in records:
        ws.append(["" if rec.get(c) is None else str(rec.get(c)) for c in COLUMNS])

    header_fill = PatternFill("solid", fgColor="0F766E")
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = Font(bold=True, color="FFFFFF")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)

    if records:
        end = len(records) + 1
        ref = f"A1:{get_column_letter(len(COLUMNS))}{end}"
        table = Table(displayName="IQACMasterData", ref=ref)
        table.tableStyleInfo = TableStyleInfo(name="TableStyleMedium4", showFirstColumn=False, showLastColumn=False, showRowStripes=True, showColumnStripes=False)
        ws.add_table(table)

    widths = {
        "A": 14, "B": 14, "C": 16, "D": 34, "E": 22, "F": 22, "G": 28, "H": 28,
        "I": 26, "J": 26, "K": 30, "L": 22, "M": 16, "N": 24, "O": 16, "P": 18,
        "Q": 18, "R": 18, "S": 38, "T": 52, "U": 38, "V": 38, "W": 38, "X": 42,
        "Y": 36, "Z": 28, "AA": 15, "AB": 15, "AC": 18, "AD": 18, "AE": 20, "AF": 16,
        "AG": 22, "AH": 18, "AI": 18, "AJ": 20, "AK": 18, "AL": 20, "AM": 22, "AN": 30,
        "AO": 24, "AP": 30, "AQ": 30, "AR": 30, "AS": 22, "AT": 24, "AU": 28, "AV": 22,
        "AW": 24, "AX": 24, "AY": 24, "AZ": 24, "BA": 24,
    }
    for col, width in widths.items():
        ws.column_dimensions[col].width = width
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    ws.row_dimensions[1].height = 42
    for r in range(2, ws.max_row + 1):
        ws.row_dimensions[r].height = 70

    out = BytesIO()
    wb.save(out)
    return out.getvalue()
