"""SRS-2 T4 - the two Excel downloads (services/boq_suggest_store/export.py), as the owner approved them on the samples.

  + Summary = the sample's 20 columns in the sample's order, a "Read me" sheet with the filters used;
  + Full = Summary + fingerprint / input / reply; each fingerprint cell is a LINK to its own row on "AI questions", whose
    "Used by rows" COUNTIF counts the records that used it;
  + one category -> one column per attribute (the category's attribute order); mixed categories -> one text column;
  + a pending row's 0 shows blank, with its status; a kind outside the pricer's scope is blank; the BCS supply figure is
    the text "not yet - added when the BCS branch merges", never a number;
  + a question over 30,000 characters is SPLIT into parts (nothing lost); a row's own input over 30,000 characters is
    FLAGGED in its cell and listed on "Read me" (never cut silently);
  - a description that starts with "=" is written as text, never as a formula.
Builds workbooks from in-memory rows (no database row is needed except the questions, which are fixtures and roll back).
"""

import io
import json
from unittest import mock

import frappe
import openpyxl
from frappe.tests.utils import FrappeTestCase

from nirmaan_stack.services.boq_suggest_store import export, records
from nirmaan_stack.services.boq_suggest_store.store_test_support import purge_store_fixtures, raw_question

SAMPLE_SUMMARY_HEADERS = [
    "Run date", "Run by", "Project", "BoQ", "Committed version", "Sheet", "Excel row", "Row identifier (BoQ node)",
    "Description", "Discipline", "Category", "Final attributes", "Supply rate", "Install rate", "Combined rate",
    "BCS supply rate", "Rates status", "Catalogue stamp", "Model", "Rows in AI call",
]
SAMPLE_FULL_EXTRA = ["AI question fingerprint", "AI input (this row, as sent)", "Raw AI reply (this row)"]
SAMPLE_QUESTION_HEADERS = ["AI question fingerprint", "Category", "Size (characters)", "Part", "Question text", "Used by rows"]
F = {"date_from": "2026-11-01", "date_to": "2026-11-27", "boq": "BOQ-TEST-SRS1-X"}


def _row(er, cat="cat_a", status="priced", scope=("supply_rate", "install_rate", "combined_rate"), question=None, **kw):
    r = {"name": "n%d" % er, "run_date": "2026-11-27 18:00:00", "project": "P1", "project_name": "Project One",
         "boq": "BOQ-TEST-SRS1-X", "sheet_name": "S", "committed_version": 1, "excel_row": er, "boq_node": "BOQN-%d" % er,
         "description": "row %d" % er, "discipline": "D", "category_id": cat,
         "final_attributes": {"excel_row": er, "category_id": cat,
                              "attributes": {"zeta": {"value": "z%d" % er}, "alpha": {"value": er}}},
         "supply_rate": 100.0, "install_rate": 20.0, "combined_rate": 120.0, "rates_status": status,
         "rates_detail": {"scope": list(scope)} if status == "priced" else None, "catalogue_stamp": "stamp",
         "pricing_stamp": "code|asset", "question": question, "batch_rows": 3, "run_by": "u@example.com", "model": "m",
         "ai_input": '{"id": %d}' % er, "raw_reply": '{"id": %d, "attributes": {}}' % er}
    r.update(kw)
    return r


def _book(rows, kind, order=()):
    with mock.patch.object(records, "attribute_order", return_value=list(order)):
        data, titles = export.workbook(rows, dict(F), kind)
    return openpyxl.load_workbook(io.BytesIO(data)), titles


def _col(ws, title):
    for c in ws[1]:
        if c.value == title:
            return c.column
    raise AssertionError("no column %r" % title)


class TestExport(FrappeTestCase):
    def setUp(self):
        self.started = frappe.utils.now_datetime()
        self.questions = []

    def tearDown(self):
        frappe.db.rollback()
        purge_store_fixtures(self.questions)

    def _q(self, text):
        name = raw_question(text)
        self.questions.append(name)
        return name

    def test_t4_summary_is_the_samples_columns_in_order_with_a_read_me(self):
        wb, titles = _book([_row(1, "cat_a"), _row(2, "cat_b")], export.SUMMARY)
        self.assertEqual(wb.sheetnames, ["AI Suggest Records", "Read me"])
        ws = wb["AI Suggest Records"]
        self.assertEqual([c.value for c in ws[1]], SAMPLE_SUMMARY_HEADERS)
        self.assertEqual(titles, SAMPLE_SUMMARY_HEADERS)
        self.assertEqual(ws.freeze_panes, "A2")
        readme = [r[0].value for r in wb["Read me"].iter_rows()]
        self.assertIn("Filters used: run date from 2026-11-01; run date to 2026-11-27; BoQ BOQ-TEST-SRS1-X.", readme)
        self.assertTrue(any("one text column" in (x or "") for x in readme))

    def test_t4_mixed_categories_one_text_column_one_category_one_column_per_attribute(self):
        wb, _ = _book([_row(1, "cat_a"), _row(2, "cat_b")], export.SUMMARY)
        ws = wb["AI Suggest Records"]
        self.assertEqual(ws.cell(row=2, column=_col(ws, "Final attributes")).value, "zeta = z1; alpha = 1")
        wb, titles = _book([_row(1), _row(2)], export.SUMMARY, order=["alpha", "zeta"])
        ws = wb["AI Suggest Records"]
        at = SAMPLE_SUMMARY_HEADERS.index("Final attributes")
        self.assertEqual(titles, SAMPLE_SUMMARY_HEADERS[:at] + ["alpha", "zeta"] + SAMPLE_SUMMARY_HEADERS[at + 1:],
                         "the category's attribute order, in the place of the text column")
        self.assertEqual((ws.cell(row=3, column=_col(ws, "alpha")).value, ws.cell(row=3, column=_col(ws, "zeta")).value),
                         ("2", "z2"))
        self.assertTrue(any("one column per attribute" in (r[0].value or "") for r in wb["Read me"].iter_rows()))

    def test_t4_rates_only_where_priced_and_in_scope_bcs_is_text(self):
        rows = [_row(1), _row(2, status="pending", supply_rate=0, install_rate=0, combined_rate=0),
                _row(3, scope=("supply_rate",)), _row(4, status="rates not computed: pricing step bundle missing")]
        wb, _ = _book(rows, export.SUMMARY)
        ws = wb["AI Suggest Records"]
        s, i, c = (_col(ws, t) for t in ("Supply rate", "Install rate", "Combined rate"))
        got = [(ws.cell(row=r, column=s).value, ws.cell(row=r, column=i).value, ws.cell(row=r, column=c).value,
                ws.cell(row=r, column=_col(ws, "Rates status")).value) for r in range(2, 6)]
        self.assertEqual(got, [(100, 20, 120, "priced"), (None, None, None, "pending"), (100, None, None, "priced"),
                               (None, None, None, "rates not computed: pricing step bundle missing")])
        self.assertEqual(ws.cell(row=2, column=s).number_format, "#,##0")
        for r in range(2, 6):
            self.assertEqual(ws.cell(row=r, column=_col(ws, "BCS supply rate")).value,
                             "not yet - added when the BCS branch merges")

    def test_t4_full_fingerprints_link_to_their_question_row_and_used_by_rows_counts(self):
        q1, q2 = self._q("question one " * 10), self._q("question two")
        rows = [_row(1, question=q1), _row(2, "cat_b", question=q2), _row(3, question=q1)]   # mixed: the text column
        wb, titles = _book(rows, export.FULL)
        self.assertEqual(wb.sheetnames, ["AI Suggest Records", "AI questions", "Read me"])
        self.assertEqual(titles, SAMPLE_SUMMARY_HEADERS + SAMPLE_FULL_EXTRA)
        ws, qs = wb["AI Suggest Records"], wb["AI questions"]
        self.assertEqual([c.value for c in qs[1]], SAMPLE_QUESTION_HEADERS)
        fp = _col(ws, "AI question fingerprint")
        letter = openpyxl.utils.get_column_letter(fp)
        fps = [ws.cell(row=r, column=fp).value for r in range(2, 5)]
        for r in range(2, 5):
            cell = ws.cell(row=r, column=fp)
            target = cell.hyperlink.location
            self.assertTrue(target.startswith("'AI questions'!A"), target)
            q_row = int(target.rsplit("A", 1)[1])
            self.assertEqual(qs.cell(row=q_row, column=1).value, cell.value, "the link lands on its own question")
            self.assertEqual(qs.cell(row=q_row, column=6).value, "=COUNTIF('AI Suggest Records'!%s:%s,A%d)" % (letter, letter, q_row))
            self.assertEqual(fps.count(qs.cell(row=q_row, column=1).value), {q1: 2, q2: 1}[cell.value],
                             "what the COUNTIF counts")
        self.assertEqual(ws.cell(row=2, column=_col(ws, "AI input (this row, as sent)")).value, '{"id": 1}')
        self.assertEqual(ws.cell(row=2, column=_col(ws, "Raw AI reply (this row)")).value, '{"id": 1, "attributes": {}}')

    def test_t4_a_long_question_is_split_and_a_long_input_is_flagged(self):
        long_q = "".join(chr(65 + (k % 26)) for k in range(65000))
        q1, q2 = self._q(long_q), self._q("short question")
        big = "x" * 30005
        wb, _ = _book([_row(1, question=q1, ai_input=big), _row(2, question=q2)], export.FULL)
        qs, ws = wb["AI questions"], wb["AI Suggest Records"]
        parts = [r for r in qs.iter_rows(min_row=2, values_only=True) if r[0] == q1]
        self.assertEqual([p[3] for p in parts], ["1 of 3", "2 of 3", "3 of 3"])
        self.assertEqual("".join(p[4] for p in parts), long_q, "split, nothing lost")
        self.assertTrue(all(len(p[4]) <= export.PART_CHARS for p in parts))
        self.assertEqual(parts[0][5][:9], "=COUNTIF(")
        self.assertIsNone(parts[1][5], "the count sits on part 1 only")
        link = ws.cell(row=3, column=_col(ws, "AI question fingerprint")).hyperlink.location
        self.assertEqual(qs.cell(row=int(link.rsplit("A", 1)[1]), column=1).value, q2, "the next question starts after the parts")
        cell = ws.cell(row=2, column=_col(ws, "AI input (this row, as sent)")).value
        self.assertTrue(cell.startswith("x" * export.PART_CHARS))
        self.assertIn("[... 5 more characters - cut for Excel; the full text is on the AI Suggest Records page]", cell)
        readme = " ".join(r[0].value or "" for r in wb["Read me"].iter_rows())
        self.assertIn("BOQ-TEST-SRS1-X / S / row 1: AI input (30,005 characters)", readme)

    def test_t4_no_long_cell_means_read_me_says_nothing_was_cut(self):
        wb, _ = _book([_row(1)], export.FULL)
        readme = " ".join(r[0].value or "" for r in wb["Read me"].iter_rows())
        self.assertIn("No input or reply was cut", readme)

    def test_t4_a_leading_equals_sign_is_text_not_a_formula(self):
        wb, _ = _book([_row(1, description="=HYPERLINK(1)")], export.SUMMARY)
        ws = wb["AI Suggest Records"]
        cell = ws.cell(row=2, column=_col(ws, "Description"))
        self.assertEqual((cell.value, cell.data_type), ("=HYPERLINK(1)", "s"))

    def test_t4_empty_download_still_has_headers_and_read_me(self):
        wb, _ = _book([], export.SUMMARY)
        self.assertEqual([c.value for c in wb["AI Suggest Records"][1]], SAMPLE_SUMMARY_HEADERS)
        self.assertIn("0 records", " ".join(r[0].value or "" for r in wb["Read me"].iter_rows()))
