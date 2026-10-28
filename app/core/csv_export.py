"""Server-side CSV serialization for the Reports module.

The only CSV code that existed before this was client-side (toCsv() in
frontend/app.js), which can only export the rows the browser already holds.
Report exports must contain the *filtered result set* requested from the
server, so serialization lives here too.

Two details worth knowing:

- Spreadsheet formula injection: a cell that starts with `=`, `+`, `-`, `@`
  (or a tab/CR) is executed as a formula by Excel/LibreOffice/Sheets when
  the CSV is opened. Report columns include free-text fields (names,
  departments, categories, audit resource ids), so any text cell beginning
  with one of those characters is prefixed with an apostrophe, the
  standard mitigation. Real numbers are written as numbers and are never
  prefixed, so negative values stay negative.
- A UTF-8 byte-order mark is written first so Excel opens non-ASCII names
  correctly instead of guessing a legacy code page.
"""
import csv
import io
from datetime import date, datetime, timezone
from decimal import Decimal

_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
UTF8_BOM = "﻿"


def csv_cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc)
        return value.isoformat(timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if text and text[0] in _FORMULA_PREFIXES:
        return "'" + text
    return text


def build_csv(headers: list[str], rows: list[list]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow([csv_cell(h) for h in headers])
    for row in rows:
        writer.writerow([csv_cell(cell) for cell in row])
    return UTF8_BOM + buffer.getvalue()
