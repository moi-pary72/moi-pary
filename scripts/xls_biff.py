"""Strict BIFF reader. MULBLANK (0xBE) contains formatting, not RK numbers.
Formula results are the cached values saved by Excel; formulas are not executed.
"""
import xlrd


def xls_book(path):
    with xlrd.open_workbook(path, formatting_info=True) as book:
        sheets = []
        for sheet in book.sheets():
            cells = {}
            for row in range(sheet.nrows):
                for col in range(sheet.ncols):
                    cell = sheet.cell(row, col)
                    if cell.ctype in (xlrd.XL_CELL_TEXT, xlrd.XL_CELL_NUMBER):
                        cells[row, col] = cell.value
                    elif cell.ctype == xlrd.XL_CELL_ERROR:
                        raise ValueError(f'Ошибка Excel: {sheet.name}!R{row+1}C{col+1}')
            sheets.append({'name': sheet.name, 'cells': cells,
                           'merged': [(r0, r1-1, c0, c1-1)
                                      for r0, r1, c0, c1 in sheet.merged_cells],
                           'height': sheet.nrows, 'width': sheet.ncols})
        return sheets
