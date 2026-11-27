"""SRS-2 - the two "AI Suggest Records" Excel downloads, as the owner approved them on the samples
(`SAMPLE_AI_Suggest_Records_Summary.xlsx` / `..._Full.xlsx`; owner R5 27 Nov 13:41, R6 13:43).

  SUMMARY (cap 50,000 rows): sheet "AI Suggest Records" with the sample's 20 columns in the sample's order, and "Read me".
  FULL (cap 5,000 rows): the same + "AI question fingerprint" (a LINK to its row on sheet "AI questions"), "AI input (this
        row, as sent)", "Raw AI reply (this row)"; sheet "AI questions" (fingerprint, category, size, part, text in parts
        of at most 30,000 characters, "Used by rows" = a COUNTIF over the records sheet's fingerprint column); "Read me".
  FINAL VALUES (R6): ONE text column when the rows span more than one category; ONE COLUMN PER VALUE (the category's
        attribute order) when they are one category.
  RATES (R8): a figure only where `records.shown_rates` gives one (priced, and a kind the pricer priced); otherwise the
        cell is empty and "Rates status" says why. The BCS supply (BCS-FX): the suggested BCS supply recorded at the run,
        "-" when none, "not recorded (run before BCS)" for a record made before the BCS merge (`records.shown_bcs`).
  OVER THE CAP: a clear refusal, nothing partial. A row's own input or reply over 30,000 characters is FLAGGED in its cell
        (owner D-3 choice: never cut silently) and listed on "Read me".

Built with openpyxl directly (as `boq_rate_master/xlsx_io` is): `write_xlsx` writes one sheet with no links.
"""

import io

import frappe
import openpyxl
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.hyperlink import Hyperlink

from nirmaan_stack.services.boq_suggest_store import records

SUMMARY, FULL = "summary", "full"
CAPS = {SUMMARY: 50000, FULL: 5000}
PART_CHARS = 30000
XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
RECORDS_SHEET, QUESTIONS_SHEET, README_SHEET = "AI Suggest Records", "AI questions", "Read me"
HEADER_FILL = PatternFill(fill_type="solid", start_color="2F5BD3", end_color="2F5BD3")
HEADER_FONT = Font(bold=True, color="FFFFFF")
LINK_FONT = Font(color="0563C1", underline="single")
MONEY = "#,##0"

# the sample's columns, in the sample's order; "Final attributes" is the one R6 may widen
SUMMARY_COLUMNS = [
    ("Run date", 16), ("Run by", 16), ("Project", 12), ("BoQ", 14), ("Committed version", 10), ("Sheet", 20),
    ("Excel row", 9), ("Row identifier (BoQ node)", 18), ("Description", 40), ("Discipline", 10), ("Category", 18),
    ("Final attributes", 60), ("Supply rate", 11), ("Install rate", 11), ("Combined rate", 12), ("BCS supply rate", 18),
    ("Rates status", 26), ("Catalogue stamp", 18), ("Model", 16), ("Rows in AI call", 9),
]
FULL_EXTRA = [("AI question fingerprint", 24), ("AI input (this row, as sent)", 70), ("Raw AI reply (this row)", 70)]
QUESTION_COLUMNS = [("AI question fingerprint", 26), ("Category", 20), ("Size (characters)", 14), ("Part", 8),
                    ("Question text", 90), ("Used by rows", 14)]


def _safe(text):
    """Cell text: a character Excel refuses is written visibly as [xNN], never dropped."""
    if not isinstance(text, str):
        return text
    return ILLEGAL_CHARACTERS_RE.sub(lambda m: "[x%02X]" % ord(m.group(0)), text)


def _put(ws, row, col, value, number_format=None):
    cell = ws.cell(row=row, column=col, value=_safe(value))
    if isinstance(value, str) and value.startswith("="):
        cell.data_type = "s"   # data, never a formula
    if number_format:
        cell.number_format = number_format
    return cell


def _header(ws, columns):
    for c, (title, width) in enumerate(columns, start=1):
        cell = ws.cell(row=1, column=c, value=title)
        cell.font, cell.fill = HEADER_FONT, HEADER_FILL
        ws.column_dimensions[get_column_letter(c)].width = width
    ws.freeze_panes = "A2"


def flag_long(text, label, where_, cut):
    """A row's own input / reply over PART_CHARS: its first PART_CHARS characters and a visible flag (D-3)."""
    if not isinstance(text, str) or len(text) <= PART_CHARS:
        return text
    cut.append("%s: %s (%s characters)" % (where_, label, f"{len(text):,}"))
    return text[:PART_CHARS] + "\n[... %s more characters - cut for Excel; the full text is on the AI Suggest Records page]" % (
        f"{len(text) - PART_CHARS:,}")


def _date(v):
    return str(v)[:16] if v else None


def build(filters, kind):
    """-> {filename, content_type, content_base64, kind, row_count, columns}; refuses over the cap."""
    import base64

    if kind not in CAPS:
        frappe.throw("Unknown download: %s" % kind)
    f = records.normalise(filters)
    n = records.count(f)
    if n > CAPS[kind]:
        frappe.throw("%s records match these filters; the %s download holds at most %s. Narrow the filters "
                     "(run dates, project, BoQ, sheet or category) and download again." % (
                         f"{n:,}", "Summary" if kind == SUMMARY else "Full", f"{CAPS[kind]:,}"),
                     title="Too many records")
    extra = ", w.ai_input, w.raw_reply" if kind == FULL else ""
    rows = records.fetch(f, extra_cols=extra)
    data, columns = workbook(rows, f, kind)
    stamp = frappe.utils.now_datetime().strftime("%Y%m%d_%H%M")
    return {"filename": "ai_suggest_records_%s_%s.xlsx" % (kind, stamp), "content_type": XLSX_CONTENT_TYPE,
            "content_base64": base64.b64encode(data).decode("ascii"), "kind": kind, "row_count": len(rows),
            "columns": columns}


def workbook(rows, f, kind):
    """bytes of the workbook for already-fetched rows (the list's columns, plus ai_input / raw_reply for FULL)."""
    categories = sorted({r.get("category_id") for r in rows})
    one = len(categories) == 1
    order = records.attribute_order(rows[0].get("discipline"), categories[0]) if one and rows else []
    orders = {} if one else records._orders(rows)
    attr_cols = []
    if one:
        seen = set()
        for r in rows:
            for label, _, _ in records.final_pairs(r.get("final_attributes"), order):
                if label not in seen:
                    seen.add(label)
                    attr_cols.append(label)
    fa_at = [c[0] for c in SUMMARY_COLUMNS].index("Final attributes")
    columns = list(SUMMARY_COLUMNS)
    if one:
        columns = columns[:fa_at] + [(a, 18) for a in attr_cols] + columns[fa_at + 1:]
    if kind == FULL:
        columns += FULL_EXTRA

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = RECORDS_SHEET
    _header(ws, columns)
    titles = [c[0] for c in columns]
    col = {t: i + 1 for i, t in enumerate(titles)}
    questions, cut = {}, []
    q_rows = {}
    if kind == FULL:
        names = sorted({r.get("question") for r in rows if r.get("question")})
        if names:
            for q in frappe.db.sql('select name, question_text, category_id from "tabBoQ AI Suggest Question" '
                                   'where name in %s', (tuple(names),), as_dict=True):
                questions[q["name"]] = q
        # the questions sheet's layout first, so each fingerprint links to its part-1 row
        at = 2
        for name in names:
            q = questions.get(name) or {"question_text": "", "category_id": None}
            q_rows[name] = at
            at += max(1, -(-len(q["question_text"] or "") // PART_CHARS))

    for i, r in enumerate(rows, start=2):
        rates = records.shown_rates(r)
        where_ = "%s / %s / row %s" % (r["boq"], r["sheet_name"], r["excel_row"])
        vals = {
            "Run date": _date(r.get("run_date")), "Run by": r.get("run_by"), "Project": r.get("project_name") or r.get("project"),
            "BoQ": r["boq"], "Committed version": r.get("committed_version"), "Sheet": r["sheet_name"],
            "Excel row": r["excel_row"], "Row identifier (BoQ node)": r.get("boq_node"), "Description": r.get("description"),
            "Discipline": r.get("discipline"), "Category": r.get("category_id"),
            "Rates status": r.get("rates_status"),
            "Catalogue stamp": r.get("catalogue_stamp"), "Model": r.get("model"), "Rows in AI call": r.get("batch_rows"),
        }
        for t, v in vals.items():
            _put(ws, i, col[t], v)
        for t, k in (("Supply rate", "supply_rate"), ("Install rate", "install_rate"), ("Combined rate", "combined_rate")):
            if rates[k] is not None:
                _put(ws, i, col[t], rates[k], MONEY)
        bcs = records.shown_bcs(r)   # BCS-FX: a figure (money), or the text "-" / "not recorded (run before BCS)"
        _put(ws, i, col["BCS supply rate"], bcs, *((MONEY,) if isinstance(bcs, float) else ()))
        if one:
            for label, value, _ in records.final_pairs(r.get("final_attributes"), order):
                _put(ws, i, col[label], value)
        else:
            _put(ws, i, col["Final attributes"],
                 records.final_text(r.get("final_attributes"), orders.get((r.get("discipline"), r.get("category_id"))) or ()))
        if kind == FULL:
            qn = r.get("question")
            if qn:
                c = _put(ws, i, col["AI question fingerprint"], qn)
                if qn in q_rows:
                    c.hyperlink = Hyperlink(ref=c.coordinate, location="'%s'!A%d" % (QUESTIONS_SHEET, q_rows[qn]))
                    c.font = LINK_FONT
            _put(ws, i, col["AI input (this row, as sent)"], flag_long(r.get("ai_input"), "AI input", where_, cut))
            _put(ws, i, col["Raw AI reply (this row)"], flag_long(r.get("raw_reply"), "AI reply", where_, cut))
    if rows:
        ws.auto_filter.ref = "A1:%s%d" % (get_column_letter(len(columns)), len(rows) + 1)

    if kind == FULL:
        _questions_sheet(wb, questions, q_rows, get_column_letter(col["AI question fingerprint"]))
    _readme(wb, f, kind, len(rows), one, categories, cut)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue(), titles


def _questions_sheet(wb, questions, q_rows, fp_col):
    qs = wb.create_sheet(QUESTIONS_SHEET)
    _header(qs, QUESTION_COLUMNS)
    qs.freeze_panes = None
    for name, first in q_rows.items():
        q = questions.get(name) or {"question_text": "", "category_id": None}
        text = q["question_text"] or ""
        parts = [text[k:k + PART_CHARS] for k in range(0, len(text), PART_CHARS)] or [""]
        for p, piece in enumerate(parts, start=1):
            row = first + p - 1
            _put(qs, row, 1, name)
            _put(qs, row, 2, q.get("category_id"))
            _put(qs, row, 3, len(text))
            _put(qs, row, 4, "%d of %d" % (p, len(parts)))
            _put(qs, row, 5, piece)
            if p == 1:
                qs.cell(row=row, column=6, value="=COUNTIF('%s'!%s:%s,A%d)" % (RECORDS_SHEET, fp_col, fp_col, row))


def _readme(wb, f, kind, n, one, categories, cut):
    rm = wb.create_sheet(README_SHEET)
    rm.column_dimensions["A"].width = 120
    labels = {"date_from": "run date from", "date_to": "run date to", "project": "project", "boq": "BoQ",
              "sheet_name": "sheet", "discipline": "discipline", "category_id": "category", "rates_status": "rates status",
              "run_by": "run by", "search": "description contains"}
    used = "; ".join("%s %s" % (labels[k], f[k]) for k in records.FILTER_KEYS if f.get(k))
    lines = [
        "AI Suggest Records - %s download, made %s." % ("Summary" if kind == SUMMARY else "Full",
                                                         frappe.utils.now_datetime().strftime("%Y-%m-%d %H:%M")),
        "Filters used: %s." % used,
        "%s records. The Summary download holds up to 50,000 rows; the Full download up to 5,000." % f"{n:,}",
        ("Final values: one column per attribute (every row is category %s)." % categories[0]) if one else
        "Final values: one text column (the rows span more than one category).",
        "Rates are shown only where the rates status is 'priced'; otherwise the cell is empty and the status says why. "
        "The BCS supply rate is the suggested BCS supply worked out at the run, as the rate helper gives it; '%s' when "
        "the helper gave none; '%s' for a record made before the BCS merge (an Admin reprice re-prices the whole record)." % (records.NO_FIGURE,
                                                                                                     records.BCS_NOT_RECORDED),
    ]
    if kind == FULL:
        lines.append("Each row's own AI input and reply are in the last two columns; the AI question it shared is on the "
                     "'AI questions' sheet (click the fingerprint), in parts of at most 30,000 characters.")
        lines.append(("Cells cut for Excel (flagged in the cell): " + "; ".join(cut)) if cut else
                     "No input or reply was cut: every cell holds its full text.")
    for i, line in enumerate(lines, start=1):
        _put(rm, i, 1, line)
