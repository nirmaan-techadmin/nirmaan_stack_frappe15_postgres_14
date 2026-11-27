"""SRS-1 T1 - the three store DocTypes (owner R-BCS-138 / 139; SRS-D0 D4; owner 27 Nov 13:30 "no source field").

  + the overwrite key refuses a second record for the same (boq, sheet_name, committed_version, excel_row);
  + a new committed version of the sheet gets its OWN record (owner "1 agree");
  + the key is the four-column UNIQUE constraint the doctype declares; run_date is indexed (the purge key);
  - no "source" field on any of the three (AI Suggest only; matching gets its own store later).
(The store's upsert naming the same constraint is pinned in test_store.)

Nothing here commits: every fixture row rolls back with the test, and the store purge helper runs after as the safety net.

Run: bench --site localhost run-tests --module nirmaan_stack.services.boq_suggest_store.test_doctypes
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from nirmaan_stack.nirmaan_stack.doctype.boq_ai_suggest_row_record import boq_ai_suggest_row_record as row_doctype
from nirmaan_stack.services.boq_suggest_store.permissions import STORE_DOCTYPES
from nirmaan_stack.services.boq_suggest_store.store_test_support import fixture_boq, purge_store_fixtures, raw_row


class TestStoreDoctypes(FrappeTestCase):
    def tearDown(self):
        purge_store_fixtures()

    def _count(self, boq):
        return frappe.db.sql('select count(*) from "tabBoQ AI Suggest Row Record" where boq = %s', (boq,))[0][0]

    def test_t1_the_overwrite_key_refuses_a_duplicate(self):
        boq = fixture_boq("dup")
        raw_row(boq, 12)
        frappe.db.savepoint("t1_dup")
        with self.assertRaises(Exception) as raised:
            raw_row(boq, 12)
        self.assertTrue(frappe.db.is_unique_key_violation(raised.exception), raised.exception)
        frappe.db.rollback(save_point="t1_dup")
        self.assertEqual(self._count(boq), 1)

    def test_t1_the_key_has_four_parts_other_rows_and_sheets_are_separate(self):
        boq = fixture_boq("parts")
        raw_row(boq, 12)
        raw_row(boq, 13)
        raw_row(boq, 12, sheet_name="Sheet A")   # the trailing space is part of the verbatim sheet name
        self.assertEqual(self._count(boq), 3)

    def test_t1_a_new_committed_version_makes_a_new_record(self):
        boq = fixture_boq("cv")
        raw_row(boq, 12, committed_version=1)
        raw_row(boq, 12, committed_version=2)
        self.assertEqual(self._count(boq), 2)

    def test_t1_the_key_is_the_declared_four_column_unique_constraint(self):
        cols = frappe.db.sql(
            """select pg_get_constraintdef(oid) from pg_constraint where conname = %s""", (row_doctype.ROW_KEY_CONSTRAINT,))
        self.assertEqual(cols[0][0], "UNIQUE (%s)" % ", ".join(row_doctype.ROW_KEY_FIELDS))
        self.assertEqual(row_doctype.ROW_KEY_FIELDS, ["boq", "sheet_name", "committed_version", "excel_row"])

    def test_t1_the_run_date_is_indexed(self):
        idx = frappe.db.sql("""select indexdef from pg_indexes where tablename = 'tabBoQ AI Suggest Row Record'""")
        self.assertTrue(any("(run_date)" in d for (d,) in idx), idx)

    def test_t1_no_source_field_on_any_store_doctype(self):
        for dt in STORE_DOCTYPES:
            self.assertIsNone(frappe.get_meta(dt).get_field("source"), dt)
            self.assertFalse(frappe.db.has_column(dt, "source"), dt)

    def test_t1_no_change_tracking_and_no_desk_create(self):
        for dt in STORE_DOCTYPES:
            meta = frappe.get_meta(dt)
            self.assertEqual((meta.track_changes, meta.in_create), (0, 1), dt)
            perms = [(p.role, p.read, p.create, p.write, p.delete) for p in meta.permissions]
            self.assertEqual(perms, [("System Manager", 1, 0, 0, 0)], dt)
