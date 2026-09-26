from __future__ import annotations

from io import BytesIO
from typing import Any
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.utils import get_column_letter

from .record_utils import COLUMNS, clean

NAVY = "123B5D"
BLUE = "2F75B5"
LIGHT_BLUE = "DDEBF7"
PALE = "F5F8FB"
GREEN = "E2F0D9"
RED = "FCE4D6"
WHITE = "FFFFFF"
GREY = "6B7280"
BORDER = Side(style="thin", color="D9E2EC")


def build_excel_bytes(records: list[dict[str, Any]]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "IQAC_Master_Data"
    ws.sheet_view.showGridLines = False

    # Clean, printable title area.
    last_col = get_column_letter(len(COLUMNS))
    ws.merge_cells(f"A1:{last_col}1")
    ws["A1"] = "IQAC MASTER ACTIVITY DATA"
    ws["A1"].font = Font(name="Aptos Display", size=18, bold=True, color=WHITE)
    ws["A1"].fill = PatternFill("solid", fgColor=NAVY)
    ws["A1"].alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[1].height = 30

    ws.merge_cells(f"A2:{last_col}2")
    ws["A2"] = f"AI-assisted extraction • {len(records)} activity record(s) • Generated {datetime.now().strftime('%d %b %Y, %I:%M %p')}"
    ws["A2"].font = Font(size=10, italic=True, color=GREY)
    ws["A2"].alignment = Alignment(vertical="center")
    ws.row_dimensions[2].height = 20

    header_row = 4
    for col_idx, name in enumerate(COLUMNS, start=1):
        cell = ws.cell(header_row, col_idx, name)
        cell.fill = PatternFill("solid", fgColor=BLUE)
        cell.font = Font(bold=True, color=WHITE)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = Border(bottom=Side(style="medium", color=NAVY))
    ws.row_dimensions[header_row].height = 34

    for row_idx, record in enumerate(records, start=header_row + 1):
        for col_idx, column in enumerate(COLUMNS, start=1):
            cell = ws.cell(row_idx, col_idx, clean(record.get(column)))
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            cell.border = Border(bottom=BORDER)
            if row_idx % 2 == 1:
                cell.fill = PatternFill("solid", fgColor=PALE)

        # Visually distinguish the two useful status columns.
        present_col = COLUMNS.index("Documents Present") + 1
        absent_col = COLUMNS.index("Documents Absent") + 1
        ws.cell(row_idx, present_col).fill = PatternFill("solid", fgColor=GREEN)
        ws.cell(row_idx, absent_col).fill = PatternFill("solid", fgColor=RED)

    if records:
        end_row = header_row + len(records)
        table = Table(displayName="IQACMasterData", ref=f"A{header_row}:{last_col}{end_row}")
        table.tableStyleInfo = TableStyleInfo(
            name="TableStyleMedium2",
            showFirstColumn=False,
            showLastColumn=False,
            showRowStripes=False,
            showColumnStripes=False,
        )
        ws.add_table(table)

    widths = {
        "A": 13, "B": 14, "C": 16, "D": 34, "E": 19, "F": 18,
        "G": 28, "H": 27, "I": 23, "J": 24, "K": 18, "L": 38,
        "M": 42, "N": 38, "O": 30, "P": 28, "Q": 31, "R": 15,
        "S": 48, "T": 48, "U": 30, "V": 12,
    }
    for idx in range(1, len(COLUMNS) + 1):
        letter = get_column_letter(idx)
        ws.column_dimensions[letter].width = widths.get(letter, 22)

    ws.freeze_panes = "A5"
    ws.auto_filter.ref = f"A{header_row}:{last_col}{header_row + len(records)}" if records else f"A{header_row}:{last_col}{header_row}"
    ws.print_title_rows = "1:4"
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_margins.left = 0.25
    ws.page_margins.right = 0.25
    ws.page_margins.top = 0.5
    ws.page_margins.bottom = 0.5

    out = BytesIO()
    wb.save(out)
    return out.getvalue()
