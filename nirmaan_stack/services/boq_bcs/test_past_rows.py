"""BCS-6b K2 -- "Previously priced": the past row's BCS figures, server side (owner R-BCS-152 Q4 / Q5 a; Answer 1 Q1-B / Q1-C).

What each test protects:
  (+) an Administrator and an Estimates caller get the three BCS keys on every shown match, with the past row's CURRENT BCS record
      on the past sheet's CURRENT committed version (a stored 0 stays 0);
  (+) a past row with no BCS record gets the three keys as None (the pop-up shows "-");
  (+) superseded is not shown: a record on an older committed version, or an is_current = 0 record, is not read;
  (-) a caller WITHOUT cost access (a Procurement user; Guest) gets NO BCS key at all - the response's key set is compared;
  (+) through the real endpoint `rate_match.get_match_results` with a stored run (the one call it makes), and READ ONLY: nothing is
      written by the read (the BCS table and the run's stored results are unchanged), one query per batch.
Users are made-up names with `frappe.get_roles` patched (test_bcs3_role_check's `_AsUser`): no User record is created.
"""
import json

import frappe
from frappe.tests.utils import FrappeTestCase

from nirmaan_stack.services.boq_bcs import past_rows

_BCS = "BoQ Row BCS Rate"
_RUN = "BoQ Rate Match Run"


class TestPastRowBcs(FrappeTestCase):
    PAST = "Past Elec "      # VERBATIM trailing space (#152)
    HVAC = "Past HVAC"
    CUR = "Current Sheet"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # api-layer TEST helpers, imported here (not at module import) as test_readiness.py does
        from nirmaan_stack.api.boq.wizard.test_bcs import _SCALAR_ROLE_MAP, _cleanup_committed, _seed_sheet
        from nirmaan_stack.api.boq.wizard.test_bcs3_role_check import ESTIMATES, PROCUREMENT, _AsUser
        from nirmaan_stack.api.boq.wizard.test_review_screen import _cleanup_project, _make_project

        cls._cleanup_committed = staticmethod(_cleanup_committed)
        cls._cleanup_project = staticmethod(_cleanup_project)
        cls.AsUser, cls.ESTIMATES, cls.PROCUREMENT = _AsUser, ESTIMATES, PROCUREMENT
        cls.test_project = _make_project()
        boq = frappe.new_doc("BOQs")
        boq.project = cls.test_project.name
        boq.boq_name = "BCS-6b past rows BoQ"
        boq.insert(ignore_permissions=True)
        cls.boq = boq.name
        # the past Electrical sheet: v2 CURRENT, v1 superseded; the past HVAC sheet: v1 current; the sheet being priced: v1
        _seed_sheet(cls.boq, cls.PAST, 2, _SCALAR_ROLE_MAP, [], 1, is_current=1)
        _seed_sheet(cls.boq, cls.PAST, 1, _SCALAR_ROLE_MAP, [], 1, is_current=0)
        _seed_sheet(cls.boq, cls.HVAC, 1, _SCALAR_ROLE_MAP, [], 2, is_current=1)
        _seed_sheet(cls.boq, cls.CUR, 1, _SCALAR_ROLE_MAP, [], 3, is_current=1)
        cls._bcs(cls.PAST, 10, 2, 14250.0, 0.0, 0.0)            # row 10: the current record on the current version
        cls._bcs(cls.PAST, 10, 2, 99999.0, 1.0, 1.0, current=0)  # its superseded predecessor (is_current 0) - never read
        cls._bcs(cls.PAST, 11, 1, 555.0, 55.0, 0.0)             # row 11: a record only on the OLD version - never read
        cls._bcs(cls.HVAC, 10, 1, 1850.0, 240.0, 0.0)           # an HVAC past row
        frappe.db.commit()

    @classmethod
    def _bcs(cls, sheet, row, cv, sup, ins, comb, current=1):
        d = frappe.new_doc(_BCS)
        d.boq, d.sheet_name, d.excel_row, d.committed_version = cls.boq, sheet, row, cv
        d.supply_rate, d.install_rate, d.combined_rate = sup, ins, comb
        d.bcs_version, d.is_current, d.is_filled = (1 if current else 0) + 1, current, 1
        d.insert(ignore_permissions=True)

    @classmethod
    def tearDownClass(cls):
        frappe.db.delete(_RUN, {"boq": cls.boq})
        cls._cleanup_committed(cls.boq)
        cls._cleanup_project(cls.test_project.name)
        frappe.db.commit()
        super().tearDownClass()

    def _rows(self):
        m = lambda sheet, row: {"key": f"{sheet}|{row}", "boq": self.boq, "sheet_name": sheet, "excel_row": row, "colour": "green",
                                "supply_rate": 1.0, "install_rate": 2.0}
        return [{"excel_row": 5, "matches": [m(self.PAST, 10), m(self.PAST, 11), m(self.HVAC, 10), m(self.PAST, 12)]}]

    def _figs(self, rows):
        return [tuple(mm.get(k, "ABSENT") for k in past_rows.BCS_KEYS) for mm in rows[0]["matches"]]

    def test_admin_gets_the_past_rows_current_figures(self):
        rows = self._rows()
        self.assertTrue(past_rows.attach_past_row_bcs(rows, user="Administrator"))
        self.assertEqual(self._figs(rows), [
            (14250.0, 0.0, 0.0),        # (+) current record on the current version; a stored 0 stays 0
            (None, None, None),         # (+) only an OLD-version record -> none on today's sheet -> None
            (1850.0, 240.0, 0.0),       # (+) any discipline
            (None, None, None),         # (+) no record at all -> None
        ])
        # the other keys of each match are untouched
        self.assertEqual({(mm["supply_rate"], mm["install_rate"]) for mm in rows[0]["matches"]}, {(1.0, 2.0)})

    def test_estimates_gets_the_keys(self):
        rows = self._rows()
        with self.AsUser(self.ESTIMATES):
            self.assertTrue(past_rows.attach_past_row_bcs(rows))
        self.assertEqual(self._figs(rows)[0], (14250.0, 0.0, 0.0))

    def test_no_cost_access_gets_no_key_at_all(self):
        before = self._rows()
        for who in (self.PROCUREMENT, "Guest"):
            rows = self._rows()
            if who == "Guest":
                self.assertFalse(past_rows.attach_past_row_bcs(rows, user="Guest"))
            else:
                with self.AsUser(who):
                    self.assertFalse(past_rows.attach_past_row_bcs(rows))
            self.assertEqual(rows, before)   # (-) the key SET is unchanged: no bcs_* key, not even None
            self.assertFalse(any(k in mm for mm in rows[0]["matches"] for k in past_rows.BCS_KEYS))

    def test_through_get_match_results_read_only(self):
        from nirmaan_stack.api.boq import rate_match as RM

        run = frappe.new_doc(_RUN)
        run.boq, run.sheet_name, run.commit_version, run.active, run.status = self.boq, self.CUR, 1, 1, "complete"
        run.results = json.dumps({"rows": self._rows()})
        run.usage = json.dumps({})
        run.flags.ignore_mandatory = True
        run.insert(ignore_permissions=True)
        frappe.db.commit()
        stored = frappe.db.get_value(_RUN, run.name, "results")
        n_bcs = frappe.db.count(_BCS, {"boq": self.boq})
        out = RM.get_match_results(self.boq, self.CUR)
        self.assertEqual(self._figs(out["run"]["rows"])[0], (14250.0, 0.0, 0.0))
        with self.AsUser(self.PROCUREMENT):
            out2 = RM.get_match_results(self.boq, self.CUR)
        self.assertFalse(any(k in mm for r in out2["run"]["rows"] for mm in r["matches"] for k in past_rows.BCS_KEYS))
        # read only: the stored results and the BCS table are unchanged
        self.assertEqual(frappe.db.get_value(_RUN, run.name, "results"), stored)
        self.assertEqual(frappe.db.count(_BCS, {"boq": self.boq}), n_bcs)

    def test_one_query_per_batch(self):
        calls = []
        real = frappe.db.sql

        def counting(q, *a, **k):
            if "tabBoQ Row BCS Rate" in str(q):
                calls.append(1)
            return real(q, *a, **k)
        keys = [(self.boq, self.PAST, r) for r in range(1, 1201)]   # 1,200 past rows
        frappe.db.sql = counting
        try:
            past_rows.past_row_bcs(keys)
        finally:
            frappe.db.sql = real
        self.assertEqual(len(calls), 3)   # ceil(1,200 / 500): never one per row
