"""SRS-2 T3 - the "AI Suggest Records" endpoints (api/boq/suggest_records.py over services/boq_suggest_store/records.py).

  + Administrator and an Admin-profile user get rows from list / filter options / get / export, and may reprice;
  - an Estimates, a PMO and an HR user - each HOLDING System Manager - get PermissionError from every method, before
    anything is read;
  + each filter (run dates, project, BoQ, sheet, discipline, category, rates status, run by, description search),
    paging (50 a page), the sort (newest run first);
  + the caps refuse cleanly (nothing partial);
  + the display rules: a pending / not-computed row shows no figure (never a 0), a kind outside the pricer's scope shows
    none; the BCS supply (BCS-FX, moved check K1-5) is the suggested figure recorded at the run, "-" while pending, and
    "not recorded (run before BCS)" for a record with no `bcs` entry (every fixture row here).

Nothing here commits: the fixture rows and people roll back with the class (the reprice call is mocked for that reason);
the purge helpers run after as the safety net.
"""

import json
from unittest import mock

import frappe
from frappe.tests.utils import FrappeTestCase

from nirmaan_stack.api.boq import suggest_records as api
from nirmaan_stack.nirmaan_stack.doctype.asset_management.test_asset_management import _make_person
from nirmaan_stack.services.boq_suggest_store import export, rates, records
from nirmaan_stack.services.boq_suggest_store.store_test_support import (
    fixture_boq,
    purge_store_fixtures,
    raw_question,
    raw_row,
    raw_run,
)

QUESTION_TEXT = "SRS-2 T3 records fixture question (made up)"
SHEETS = ("Sheet R1", "Sheet R2")


def _fa(er, cat):
    return json.dumps({"excel_row": er, "description": "d%d" % er, "category_id": cat,
                       "attributes": {"alpha": {"value": "a%d" % er, "confidence": 0.9}, "beta": {"value": er, "confidence": 0.8},
                                      "gamma": {"value": None, "confidence": 0.5}, "delta": {"value": "x", "confidence": 0.4}}})


class TestRecords(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.people = {}
        for tag, profile in (("admin", "Nirmaan Admin Profile"), ("est", "Nirmaan Estimates Executive Profile"),
                             ("pmo", "Nirmaan PMO Executive Profile"), ("hr", "Nirmaan HR Executive Profile")):
            email = _make_person("srs2-" + tag, profile)
            frappe.get_doc({"doctype": "Has Role", "name": frappe.generate_hash(length=10), "parent": email,
                            "parenttype": "User", "parentfield": "roles", "role": "System Manager"}).db_insert()
            frappe.clear_cache(user=email)
            cls.people[tag] = email
        cls.boq = fixture_boq("rec")
        cls.boq2 = fixture_boq("rec2")
        cls.question = raw_question(QUESTION_TEXT)
        now = frappe.utils.now_datetime()
        cls.run_a = raw_run(cls.boq, run_by="user-a@example.com", model="m-a", run_id="rid-a")
        cls.run_b = raw_run(cls.boq2, run_by="user-b@example.com", model="m-b", run_id="rid-b")
        cls.rows = {}
        # 53 rows on boq (pager), newest first by run_date; three statuses and two categories
        for i in range(53):
            er = 100 + i
            status = ("priced" if i % 4 == 0 else "pending" if i % 4 == 1 else "not priced: no SKU" if i % 4 == 2
                      else "rates not computed: pricing step bundle missing")
            detail = json.dumps({"scope": ["supply_rate", "combined_rate"]}) if status == "priced" else None
            cat = "cat_one" if i < 40 else "cat_two"
            cls.rows[er] = raw_row(cls.boq, er, sheet_name=SHEETS[i % 2], run_record=cls.run_a, run_id="rid-a",
                                   run_date=frappe.utils.add_to_date(now, minutes=-i), category_id=cat, discipline="DiscA",
                                   description="pump row %d" % er if i == 7 else "row %d" % er,
                                   final_attributes=_fa(er, cat), question=cls.question, batch_no=1, batch_rows=4,
                                   supply_rate=11 if status == "priced" else 0, install_rate=22 if status == "priced" else 0,
                                   combined_rate=33 if status == "priced" else 0, bcs_supply_rate=0,
                                   rates_status=status, rates_detail=detail, project=None)
        # boq2: one recent row (other run_by / discipline) and one 40 days old (outside the default 30 days)
        cls.recent2 = raw_row(cls.boq2, 5, sheet_name="Sheet Z", run_record=cls.run_b, run_date=now, category_id="cat_three",
                              discipline="DiscB", final_attributes=_fa(5, "cat_three"), rates_status="pending")
        cls.old2 = raw_row(cls.boq2, 6, sheet_name="Sheet Z", run_record=cls.run_b,
                           run_date=frappe.utils.add_to_date(now, days=-40), category_id="cat_three", discipline="DiscB",
                           final_attributes=_fa(6, "cat_three"), rates_status="pending")

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        frappe.db.rollback()
        people = list(cls.people.values())
        for dt, filters in (("Has Role", {"parent": ["in", people], "parenttype": "User"}),
                            ("Nirmaan Users", {"name": ["in", people]}), ("User", {"name": ["in", people]})):
            try:
                frappe.db.delete(dt, filters)
                frappe.db.commit()
            except Exception as exc:  # noqa: BLE001 -- reported, never swallowed
                frappe.db.rollback()
                print("WARNING -- test_records people purge INCOMPLETE: %s: %s" % (dt, exc))
        purge_store_fixtures([cls.question])
        super().tearDownClass()

    def tearDown(self):
        frappe.set_user("Administrator")

    def _names(self, **filters):
        return [r["name"] for r in api.list_records(json.dumps(filters), 1)["rows"]]

    # ── the Admin gate ──────────────────────────────────────────────────────────────────────────────────────────────
    def test_t3_administrator_and_the_admin_profile_get_rows(self):
        for user in ("Administrator", self.people["admin"]):
            frappe.set_user(user)
            got = api.list_records(json.dumps({"boq": self.boq}), 1)
            self.assertEqual((got["total"], len(got["rows"])), (53, 50), user)
            self.assertEqual(api.get_record(self.rows[100])["excel_row"], 100, user)
            self.assertIn(self.boq, api.filter_options()["boqs"], user)
            self.assertEqual(api.export_records(json.dumps({"boq": self.boq2}), "summary")["row_count"], 1, user)
            with mock.patch.object(rates, "price_run_record", return_value={"rows": 53}) as rp:
                self.assertEqual(api.reprice_run_record(self.run_a), {"rows": 53})
            rp.assert_called_once_with(self.run_a)

    def test_t3_estimates_pmo_and_hr_holding_system_manager_are_refused_everywhere(self):
        for tag in ("est", "pmo", "hr"):
            frappe.set_user(self.people[tag])
            self.assertIn("System Manager", frappe.get_roles(self.people[tag]))
            with mock.patch.object(records, "list_records") as lr, mock.patch.object(records, "get_record") as gr, \
                    mock.patch.object(records, "filter_options") as fo, mock.patch.object(export, "build") as eb, \
                    mock.patch.object(rates, "price_run_record") as rp:
                for call in (lambda: api.list_records(None, 1), lambda: api.get_record(self.rows[100]),
                             api.filter_options, lambda: api.export_records(None, "summary"),
                             lambda: api.export_records(None, "full"), lambda: api.reprice_run_record(self.run_a)):
                    with self.assertRaises(frappe.PermissionError, msg=tag):
                        call()
                for m in (lr, gr, fo, eb, rp):
                    m.assert_not_called()   # refused BEFORE anything is read

    # ── filters, paging, sort ───────────────────────────────────────────────────────────────────────────────────────
    def test_t3_paging_50_a_page_and_newest_run_first(self):
        p1 = api.list_records(json.dumps({"boq": self.boq}), 1)
        p2 = api.list_records(json.dumps({"boq": self.boq}), 2)
        self.assertEqual((len(p1["rows"]), len(p2["rows"]), p1["page_size"]), (50, 3, 50))
        ers = [r["excel_row"] for r in p1["rows"] + p2["rows"]]
        self.assertEqual(ers, list(range(100, 153)), "newest run first (row 100 is the newest)")

    def test_t3_each_filter(self):
        boq = {"boq": self.boq}
        self.assertEqual(len(self._names(**boq, sheet_name=SHEETS[1])), 26)
        self.assertEqual(len(self._names(**boq, category_id="cat_two")), 13)
        self.assertEqual(self._names(**boq, search="PUMP"), [self.rows[107]], "the search is case-blind")
        self.assertEqual(len(self._names(**boq, rates_status="priced")), 14)
        self.assertEqual(len(self._names(**boq, rates_status="pending")), 13)
        self.assertEqual(len(self._names(**boq, rates_status="not priced")), 13)
        self.assertEqual(len(self._names(**boq, rates_status="rates not computed")), 13)
        self.assertEqual(self._names(boq=self.boq2), [self.recent2], "the default window is the last 30 days")
        old_from = str(frappe.utils.add_days(frappe.utils.nowdate(), -45))
        self.assertEqual(sorted(self._names(boq=self.boq2, date_from=old_from)), sorted([self.recent2, self.old2]))
        self.assertEqual(self._names(run_by="user-b@example.com", date_from=old_from, boq=self.boq2),
                         [self.recent2, self.old2])
        self.assertEqual(self._names(discipline="DiscB", boq=self.boq2), [self.recent2])
        self.assertEqual(self._names(boq=self.boq, discipline="DiscB"), [])
        self.assertEqual(self._names(boq=self.boq, search="%"), [], "a % in the search is a character, not a wildcard")
        with self.assertRaises(frappe.ValidationError):
            api.list_records(json.dumps({"rates_status": "made up"}), 1)

    def test_t3_project_filter(self):
        self.assertEqual(self._names(boq=self.boq, project="PROJ-NOT-THERE"), [])

    # ── display rules ───────────────────────────────────────────────────────────────────────────────────────────────
    def test_t5_server_rows_never_show_a_0_as_a_price_and_show_not_recorded_for_old_rows(self):
        rows = {r["excel_row"]: r for r in api.list_records(json.dumps({"boq": self.boq}), 1)["rows"]}
        priced, pending, not_priced, not_computed = rows[100], rows[101], rows[102], rows[103]
        self.assertEqual((priced["supply_rate"], priced["install_rate"], priced["combined_rate"]), (11, None, 33),
                         "install is outside the pricer's scope: no figure")
        for r in (pending, not_priced, not_computed):
            self.assertEqual((r["supply_rate"], r["install_rate"], r["combined_rate"]), (None, None, None), r["rates_status"])
        for r in rows.values():   # BCS-FX moved check K1-2: no `bcs` entry -> "not recorded (run before BCS)"; pending -> "-"
            self.assertEqual(r["bcs_supply_rate"], "-" if r["rates_status"] == "pending" else "not recorded (run before BCS)")
        self.assertEqual(priced["first_values"], "alpha = a100; beta = 100; gamma = None")

    def test_t3_get_record_brings_its_question_run_and_batch(self):
        frappe.db.sql('update "tabBoQ AI Suggest Run Record" set batches = %s where name = %s',
                      (json.dumps({"batches": [{"batch_no": 1, "rows": [100], "calls": [{"input_tokens": 9}]}]}), self.run_a))
        d = api.get_record(self.rows[100])
        self.assertEqual(d["question"]["name"], self.question)
        self.assertEqual(d["question"]["text"], QUESTION_TEXT)
        self.assertEqual((d["run"]["run_by"], d["run"]["model"]), ("user-a@example.com", "m-a"))
        self.assertEqual(d["batch"]["calls"], [{"input_tokens": 9}])
        self.assertEqual([a["attribute"] for a in d["final_attributes"]], ["alpha", "beta", "gamma", "delta"])
        self.assertEqual(d["rates"]["bcs_supply_rate"], records.BCS_NOT_RECORDED)   # BCS-FX moved check K1-3
        self.assertEqual((d["rates"]["supply_rate"], d["rates"]["install_rate"]), (11, None))
        with self.assertRaises(frappe.DoesNotExistError):
            api.get_record("no-such-record")

    def test_t3_the_caps_refuse_cleanly(self):
        with mock.patch.dict(export.CAPS, {"summary": 52, "full": 2}):
            with self.assertRaises(frappe.ValidationError) as cm:
                api.export_records(json.dumps({"boq": self.boq}), "summary")
            self.assertIn("53 records match", str(cm.exception))
            self.assertIn("at most 52", str(cm.exception))
            with self.assertRaises(frappe.ValidationError):
                api.export_records(json.dumps({"boq": self.boq}), "full")
            # at the cap: answered
            self.assertEqual(api.export_records(json.dumps({"boq": self.boq, "category_id": "cat_two"}), "summary")["row_count"], 13)
        with self.assertRaises(frappe.ValidationError):
            api.export_records(None, "everything")

    def test_t3_reprice_refuses_an_unknown_run_record(self):
        with self.assertRaises(frappe.DoesNotExistError):
            api.reprice_run_record("no-such-run")
