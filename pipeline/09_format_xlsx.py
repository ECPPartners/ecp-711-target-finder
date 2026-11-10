"""Header styling, freeze panes, filters, widths for an output workbook. Usage: python3 -I 09_format_xlsx.py <xlsx>"""
import sys, openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
WIDE = ('Data Gaps', 'Sources & Dates', 'Read Me')
wb = openpyxl.load_workbook(sys.argv[1])
for ws in wb.worksheets:
    ws.freeze_panes = 'A2'
    for c in ws[1]:
        c.font = Font(bold=True, color='FFFFFF'); c.fill = PatternFill('solid', fgColor='1F3A5F'); c.alignment = Alignment(wrap_text=True, vertical='top')
    for col in ws.columns:
        L = max((len(str(c.value)) for c in list(col)[:200] if c.value is not None), default=8)
        ws.column_dimensions[col[0].column_letter].width = min(max(10, L + 2), 60 if ws.title in WIDE else 40)
    if ws.title in WIDE:
        for row in ws.iter_rows(min_row=2):
            for c in row: c.alignment = Alignment(wrap_text=True, vertical='top')
    elif ws.max_row > 1: ws.auto_filter.ref = ws.dimensions
wb.save(sys.argv[1])
