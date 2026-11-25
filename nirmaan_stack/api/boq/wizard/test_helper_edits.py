# Copyright (c) 2026, Nirmaan (Stratos Infra Technologies Pvt. Ltd.) and contributors
# For license information, please see license.txt

"""BCS-4: a field changed in a row's rate helper is saved for the row (api/boq/wizard/helper_edits.py).

(+) save / read / clear (one key, all keys); the round trip of P3b (a save from the Supply view, a second key from the BCS
    view, one current record, the old one superseded); an allowed profile saves.
(+) owner R-BCS-140 (replacing R-BCS-45 "a fresh run keeps it"): a Suggest run that writes a row REPLACES that row's saved
    edits -- the record is kept, frozen (is_current 0), never deleted.
(-) an edit writes no price and no cost (BoQ Cell Pricing and BoQ Row BCS Rate unchanged at every step); a new committed
    version reads no edit of the old one; a Suggest run keeps the edits of the rows it did not write, and a fail-closed pass
    (the AI did not run) keeps every edit; a locked sheet, a cell that is not committed, a sheet held by another editor, a
    user who may not price and a profile outside the set are refused, and a refusal writes nothing.

Fixture-only: fixture BoQs (purged at the end), committed sheets at versions 1 and 2. The Suggest cases drive the REAL worker
under the operation wrapper with the extraction edge faked and the AI client refusing (test_bcs.TestSuggestSwitchesBcsOn's
shape) -- no model call. Run with
`bench --site dev2.localhost run-tests --module nirmaan_stack.api.boq.wizard.test_helper_edits`.
"""

import uuid
from unittest import mock

import frappe
from frappe.tests.utils import FrappeTestCase

from nirmaan_stack.api.background_ops import get_status
from nirmaan_stack.api.boq import rate_master, rate_match
from nirmaan_stack.api.boq.test_rate_suggest import _insert_cat
from nirmaan_stack.api.boq.wizard.test_pricing import _categorise_fixture_eligible_rows
from nirmaan_stack.services import background_ops
from nirmaan_stack.services.boq_rate_master import extraction
from nirmaan_stack.services.test_operation_marker import new_request
from nirmaan_stack.api.boq.wizard import helper_edits
from nirmaan_stack.api.boq.wizard.helper_edits import (
    clear_row_helper_edits,
    get_row_helper_edits,
    save_row_helper_edit,
)
from nirmaan_stack.api.boq.wizard.pricing_lock import _LOCK_HELD_MARKER, acquire_or_refresh
from nirmaan_stack.api.boq.wizard.test_classify import _new_boq, _new_sheet, _node
from nirmaan_stack.api.boq.wizard.test_review_screen import _cleanup_project, _make_project
from nirmaan_stack.services.boq_fixture_teardown import purge_boq, purge_docs

_EDIT = "BoQ Row Helper Edit"
_PRICING = "BoQ Cell Pricing"
_BCS = "BoQ Row BCS Rate"
_LOCK_DT = "BoQ Sheet Pricing Lock"
_BOQ_SHEET = "BoQ Sheet"


class TestRowHelperEdits(FrappeTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = _make_project()
        cls.boq = _new_boq(cls.project.name, "Helper Edit BoQ")
        cls.sheet = "HelperEditFix "  # VERBATIM trailing space (#152)
        cls.cv = 1
        cls.sheet_row = _new_sheet(cls.boq, cls.sheet, cls.cv)
        p = _node(cls.boq, cls.sheet_row, "Preamble", 10, None, "SECTION", 1, level=0)
        _node(cls.boq, cls.sheet_row, "Line Item", 12, p, "MCB 32A SP C curve", 2, qty=4)
        _node(cls.boq, cls.sheet_row, "Line Item", 13, p, "MCB 16A SP C curve", 3, qty=2)
        frappe.db.commit()

    @classmethod
    def tearDownClass(cls):
        frappe.db.rollback()
        frappe.db.delete(_EDIT, {"boq": cls.boq})
        frappe.db.delete(_LOCK_DT, {"boq": cls.boq})
        purge_docs("BOQ Nodes", {"boq": cls.boq})
        purge_docs(_BOQ_SHEET, {"boq": cls.boq})
        frappe.db.commit()
        purge_boq(cls.boq)
        _cleanup_project(cls.project.name)
        super().tearDownClass()

    def setUp(self):
        frappe.set_user("Administrator")
        frappe.db.delete(_EDIT, {"boq": self.boq})
        frappe.db.delete(_LOCK_DT, {"boq": self.boq})
        frappe.db.set_value(_BOQ_SHEET, self.sheet_row, {"is_locked": 0, "is_current": 1}, update_modified=False)
        frappe.db.commit()

    def tearDown(self):
        frappe.set_user("Administrator")

    # -- helpers ---------------------------------------------------------------------------------------------------
    def _save(self, attr_id, value, from_kind, row=12, cv=None):
        return save_row_helper_edit(boq_name=self.boq, sheet_name=self.sheet, excel_row=row,
                                    committed_version=cv or self.cv, attr_id=attr_id, value=value, from_kind=from_kind)

    def _get(self, cv=None):
        return get_row_helper_edits(boq_name=self.boq, sheet_name=self.sheet, committed_version=cv or self.cv)["rows"]

    def _records(self, row=12, cv=None):
        return frappe.get_all(_EDIT, filters={"boq": self.boq, "sheet_name": self.sheet, "excel_row": row,
                                              "committed_version": cv or self.cv},
                              fields=["name", "edit_version", "is_current", "edits"], order_by="edit_version asc")

    @staticmethod
    def _price_and_cost_counts():
        """The two tables an edit must never write, counted whole (a write to ANY row would move them)."""
        return frappe.db.count(_PRICING), frappe.db.count(_BCS)

    # -- (+) save / read / clear -----------------------------------------------------------------------------------
    def test_save_then_read_carries_value_and_view(self):
        self._save("curve", "D", "supply")
        rows = self._get()
        self.assertEqual(list(rows), [12])
        self.assertEqual(rows[12]["curve"]["value"], "D")
        self.assertEqual(rows[12]["curve"]["from_kind"], "supply")
        self.assertEqual(rows[12]["curve"]["by"], "Administrator")

    def test_round_trip_second_key_supersedes_one_current(self):
        """P3b: supply then bcs_supply -> both keys, ONE current record, the first superseded (kept, is_current 0)."""
        before = self._price_and_cost_counts()
        self._save("curve", "D", "supply")
        self.assertEqual(self._price_and_cost_counts(), before)
        self._save("__shares__", '{"s1": {"added": true}}', "bcs_supply")
        self.assertEqual(self._price_and_cost_counts(), before)
        recs = self._records()
        self.assertEqual([(r.edit_version, r.is_current) for r in recs], [(1, 0), (2, 1)])
        rows = self._get()
        self.assertEqual(set(rows[12]), {"curve", "__shares__"})
        self.assertEqual(rows[12]["curve"]["from_kind"], "supply")
        self.assertEqual(rows[12]["__shares__"]["from_kind"], "bcs_supply")
        self.assertEqual(rows[12]["__shares__"]["value"], '{"s1": {"added": true}}')

    def test_same_value_same_view_writes_nothing(self):
        self._save("curve", "D", "supply")
        out = self._save("curve", "D", "supply")
        self.assertFalse(out["wrote"])
        self.assertEqual(len(self._records()), 1)

    def test_empty_text_is_a_value(self):
        """setAttr(id, "") overrides with empty -- stored as such, not dropped."""
        self._save("paired_mcb", "", "install")
        self.assertEqual(self._get()[12]["paired_mcb"]["value"], "")

    def test_clear_one_key_keeps_the_others(self):
        before = self._price_and_cost_counts()
        self._save("curve", "D", "supply")
        self._save("poles", "TP", "install")
        clear_row_helper_edits(boq_name=self.boq, sheet_name=self.sheet, excel_row=12,
                               committed_version=self.cv, attr_id="curve")
        self.assertEqual(set(self._get()[12]), {"poles"})
        self.assertEqual(sum(r.is_current for r in self._records()), 1)
        self.assertEqual(self._price_and_cost_counts(), before)

    def test_clear_last_key_ends_the_record(self):
        self._save("curve", "D", "supply")
        clear_row_helper_edits(boq_name=self.boq, sheet_name=self.sheet, excel_row=12,
                               committed_version=self.cv, attr_id="curve")
        self.assertEqual(self._get(), {})
        self.assertEqual(sum(r.is_current for r in self._records()), 0)

    def test_clear_all_ends_the_record(self):
        before = self._price_and_cost_counts()
        self._save("curve", "D", "supply")
        self._save("poles", "TP", "combined")
        out = clear_row_helper_edits(boq_name=self.boq, sheet_name=self.sheet, excel_row=12, committed_version=self.cv)
        self.assertTrue(out["wrote"])
        self.assertEqual(self._get(), {})
        self.assertEqual(sum(r.is_current for r in self._records()), 0)
        self.assertEqual(len(self._records()), 2)  # history kept, nothing deleted
        self.assertEqual(self._price_and_cost_counts(), before)

    def test_clear_with_nothing_saved_writes_nothing(self):
        out = clear_row_helper_edits(boq_name=self.boq, sheet_name=self.sheet, excel_row=13, committed_version=self.cv)
        self.assertFalse(out["wrote"])
        self.assertEqual(self._records(row=13), [])

    def test_rows_are_separate(self):
        self._save("curve", "D", "supply", row=12)
        self._save("curve", "B", "install", row=13)
        rows = self._get()
        self.assertEqual(rows[12]["curve"]["value"], "D")
        self.assertEqual(rows[13]["curve"]["value"], "B")

    # -- (-) never a price, never a cost ---------------------------------------------------------------------------
    def test_helper_edit_writes_no_price_or_cost(self):
        before = self._price_and_cost_counts()
        self._save("curve", "D", "supply")
        self._save("curve", "C", "bcs_supply")
        self._save("__items__", '{"0": {"brand": "X"}}', "combined")
        clear_row_helper_edits(boq_name=self.boq, sheet_name=self.sheet, excel_row=12,
                               committed_version=self.cv, attr_id="__items__")
        clear_row_helper_edits(boq_name=self.boq, sheet_name=self.sheet, excel_row=12, committed_version=self.cv)
        self.assertEqual(self._price_and_cost_counts(), before)
        self.assertEqual(frappe.db.count(_PRICING, {"boq": self.boq}), 0)
        self.assertEqual(frappe.db.count(_BCS, {"boq": self.boq}), 0)

    def test_module_names_no_price_or_cost_writer(self):
        """No code path from an edit to save_cell_price / save_row_bcs_rates: the module imports neither."""
        import ast
        import inspect

        tree = ast.parse(inspect.getsource(helper_edits))  # the CODE, not the docstrings that name what it never does
        imported, used, strings = set(), set(), set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                imported.add(node.module or "")
                imported.update(a.name for a in node.names)
            elif isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
            elif isinstance(node, ast.Name):
                used.add(node.id)
            elif isinstance(node, ast.Attribute):
                used.add(node.attr)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                strings.add(node.value)
        for writer in ("save_cell_price", "save_row_bcs_rates", "_write_cell_price_record"):
            self.assertNotIn(writer, imported | used)
        self.assertFalse([m for m in imported if m.endswith(".bcs") or m == "bcs"], imported)
        self.assertNotIn("BoQ Cell Pricing", strings)
        self.assertNotIn("BoQ Row BCS Rate", strings)

    def test_edits_not_carried_to_new_version(self):
        """Owner R4: a new committed version reads no edit of the old one."""
        self._save("curve", "D", "supply")
        # A re-commit: version 1's sheet row stops being current (one current BoQ Sheet per boq + sheet, uq_boq_sheet_current)
        frappe.db.set_value(_BOQ_SHEET, self.sheet_row, "is_current", 0, update_modified=False)
        frappe.db.delete(_LOCK_DT, {"boq": self.boq})
        frappe.db.commit()
        v2 = _new_sheet(self.boq, self.sheet, 2)
        n = frappe.new_doc("BOQ Nodes")
        n.update({"boq": self.boq, "sheet": v2, "node_type": "Line Item", "source_row_number": 12,
                  "description": "MCB 32A SP C curve", "sort_order": 1, "commit_version": 2, "is_current": 1, "qty": 4})
        n.insert(ignore_permissions=True)
        frappe.db.commit()
        try:
            self.assertEqual(self._get(cv=2), {})
            self.assertEqual(self._get(cv=1)[12]["curve"]["value"], "D")
            self._save("curve", "B", "install", cv=2)
            self.assertEqual(self._get(cv=2)[12]["curve"]["value"], "B")
            self.assertEqual(self._get(cv=1)[12]["curve"]["value"], "D")
        finally:
            frappe.db.rollback()
            frappe.db.delete(_EDIT, {"boq": self.boq, "committed_version": 2})
            frappe.db.delete(_LOCK_DT, {"boq": self.boq})
            frappe.db.delete("BOQ Nodes", {"name": n.name})
            frappe.db.delete(_BOQ_SHEET, {"name": v2})
            frappe.db.set_value(_BOQ_SHEET, self.sheet_row, "is_current", 1, update_modified=False)
            frappe.db.commit()

    # -- (-) refusals write nothing --------------------------------------------------------------------------------
    def _assert_refused_writes_nothing(self, call, exc=frappe.ValidationError, words=None):
        before = frappe.db.count(_EDIT, {"boq": self.boq})
        with self.assertRaises(exc) as cm:
            call()
        if words:
            self.assertIn(words, str(cm.exception))
        frappe.db.rollback()
        self.assertEqual(frappe.db.count(_EDIT, {"boq": self.boq}), before)

    def test_locked_sheet_refuses(self):
        self._save("curve", "D", "supply")
        frappe.db.set_value(_BOQ_SHEET, self.sheet_row, "is_locked", 1, update_modified=False)
        frappe.db.commit()
        self._assert_refused_writes_nothing(lambda: self._save("curve", "B", "install"))
        self._assert_refused_writes_nothing(lambda: clear_row_helper_edits(
            boq_name=self.boq, sheet_name=self.sheet, excel_row=12, committed_version=self.cv))
        frappe.db.set_value(_BOQ_SHEET, self.sheet_row, "is_locked", 0, update_modified=False)
        frappe.db.commit()
        self.assertEqual(self._get()[12]["curve"]["value"], "D")

    def test_cell_not_committed_refuses(self):
        self._assert_refused_writes_nothing(lambda: self._save("curve", "D", "supply", row=99),
                                            words="No committed cell")

    def test_sheet_held_by_another_editor_refuses(self):
        # BoQ Sheet Pricing Lock.locked_by is a Link to User: the competing holder is a REAL enabled user, seeded through
        # the lock engine itself (the house pattern of test_bcs.TestBcsRespectsTheSingleEditorLock).
        other = frappe.db.get_value("User", {"name": ["not in", ["Administrator", "Guest"]], "enabled": 1}, "name")
        self.assertTrue(other, "need a second real User to play the competing lock holder")
        acquire_or_refresh(self.boq, self.sheet, self.cv, other, frappe.utils.now_datetime())
        frappe.db.commit()
        self._assert_refused_writes_nothing(lambda: self._save("curve", "D", "supply"), words=_LOCK_HELD_MARKER)

    def test_user_without_pricing_role_refuses(self):
        """A user who may not price on the BoQ pages is refused on every endpoint (Guest stands in: no role profile)."""
        self._save("curve", "D", "supply")
        frappe.set_user("Guest")
        try:
            self._assert_refused_writes_nothing(lambda: self._save("curve", "B", "install"),
                                                exc=frappe.PermissionError, words="not permitted to change the rate helper")
            self._assert_refused_writes_nothing(lambda: clear_row_helper_edits(
                boq_name=self.boq, sheet_name=self.sheet, excel_row=12, committed_version=self.cv),
                exc=frappe.PermissionError)
            with self.assertRaises(frappe.PermissionError):
                self._get()
        finally:
            frappe.set_user("Administrator")
        self.assertEqual(self._get()[12]["curve"]["value"], "D")

    def _other_user(self):
        other = frappe.db.get_value("User", {"name": ["not in", ["Administrator", "Guest"]], "enabled": 1}, "name")
        self.assertTrue(other, "need a second real User to act as a non-admin pricer")
        return other

    def test_allowed_profile_saves(self):
        """(+) NOTE 2: a non-admin user whose role profile is in the wizard set saves."""
        other = self._other_user()
        with mock.patch.object(helper_edits, "_role_profile_of", return_value="Nirmaan Estimates Executive Profile"):
            frappe.set_user(other)
            try:
                out = self._save("curve", "D", "supply")
            finally:
                frappe.set_user("Administrator")
        self.assertTrue(out["wrote"])
        self.assertEqual(self._get()[12]["curve"]["by"], other)

    def test_profile_outside_the_set_refuses(self):
        """(-) NOTE 2: a profile outside the set (Billing opens the page) is refused with exactly these words."""
        self.assertNotIn("Nirmaan Billing Executive Profile", helper_edits._WIZARD_ROLE_PROFILES)
        other = self._other_user()
        with mock.patch.object(helper_edits, "_role_profile_of", return_value="Nirmaan Billing Executive Profile"):
            frappe.set_user(other)
            try:
                before = frappe.db.count(_EDIT, {"boq": self.boq})
                with self.assertRaises(frappe.PermissionError) as cm:
                    self._save("curve", "D", "supply")
                self.assertEqual(str(cm.exception), "You are not permitted to change the rate helper on this sheet.")
                self.assertNotIn("cost", str(cm.exception).lower())
                frappe.db.rollback()
                self.assertEqual(frappe.db.count(_EDIT, {"boq": self.boq}), before)
            finally:
                frappe.set_user("Administrator")

    def test_unknown_view_refuses(self):
        self._assert_refused_writes_nothing(lambda: self._save("curve", "D", "Supply"), words="from_kind")


def _extract_reads(rows, ai_status="ran"):
    """A faked extraction edge that read `rows` of the population [2, 3] (all of them = a complete run, fewer = a partial)."""
    def extract(boq, sheet_name, only_rows=None, **kwargs):
        return {
            "committed_version": 1, "ai_status": ai_status, "halt_reason": None if set(rows) == {2, 3} else "fixture halt",
            "complete": set(rows) == {2, 3},
            "results": [{"excel_row": r, "description": "d", "category_id": "x", "attributes": {"tag": {"value": f"r{r}"}}}
                        for r in rows],
            "attempted_rows": list(rows), "population_rows": [2, 3],
        }
    return extract


class TestSuggestRunReplacesHelperEdits(FrappeTestCase):
    """Owner R-BCS-140 (2026-11-26 00:37, "yes replcae"; replaces R-BCS-45): a fresh Suggest run REPLACES the saved helper
    edits of the rows it writes (they stay as history, not current); rows it does not write keep theirs. The REAL worker
    (`rate_master._suggest_worker`) runs under `background_ops.run`; the queue and the extraction edge are faked and the AI
    client REFUSES (`anthropic.Anthropic` raises), so no model is ever called."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = _make_project()
        cls.boq = _new_boq(cls.project.name, f"BCS4_{frappe.generate_hash(length=6)}")
        cls.sheet = "BCS4 replace "  # VERBATIM trailing space (#152)
        cls.sheet_doc = _new_sheet(cls.boq, cls.sheet, commit_version=1)
        header = _node(cls.boq, cls.sheet_doc, "Preamble", 1, None, "MADE-UP SECTION", 1)
        _node(cls.boq, cls.sheet_doc, "Line Item", 2, header, "made-up line two", 2, qty=1)
        _node(cls.boq, cls.sheet_doc, "Line Item", 3, header, "made-up line three", 3, qty=1)
        frappe.db.commit()
        _insert_cat(cls.boq, cls.sheet, 1, 2, "wiring_cabling", discipline="Electrical")
        _insert_cat(cls.boq, cls.sheet, 1, 3, "wiring_cabling", discipline="Electrical")
        _categorise_fixture_eligible_rows(cls.boq, cls.sheet, 1, discipline="Electrical")
        frappe.db.commit()

    @classmethod
    def tearDownClass(cls):
        frappe.db.rollback()
        for dt in (_EDIT, _LOCK_DT, "BoQ Rate Suggestion Run", _BCS, _PRICING, "BoQ Row Category", "BOQ Nodes", _BOQ_SHEET):
            try:
                frappe.db.delete(dt, {"boq": cls.boq})
                frappe.db.commit()
            except Exception as e:  # noqa: BLE001 -- report, keep cleaning the other scopes
                frappe.db.rollback()
                print(f"cleanup of {dt} failed: {e}")
        purge_boq(cls.boq)
        _cleanup_project(cls.project.name)
        super().tearDownClass()

    def setUp(self):
        frappe.set_user("Administrator")
        self.queued = []
        for dt in (_EDIT, _LOCK_DT, "BoQ Rate Suggestion Run"):
            frappe.db.delete(dt, {"boq": self.boq})
        frappe.db.set_value(_BOQ_SHEET, self.sheet_doc, "bcs_enabled", 0, update_modified=False)
        frappe.db.commit()
        for row in (2, 3):
            save_row_helper_edit(boq_name=self.boq, sheet_name=self.sheet, excel_row=row, committed_version=1,
                                 attr_id="thickness_sqmm", value="2.5", from_kind="supply")
        frappe.db.delete(_LOCK_DT, {"boq": self.boq})  # the run's owner is another request; the pricing lock plays no part
        frappe.db.commit()

    def tearDown(self):
        frappe.set_user("Administrator")
        frappe.cache().delete_value(rate_master._s_marker_key(self.boq, self.sheet))
        new_request()

    def _run(self, extract):
        """Press Suggest and run the queued operation as a worker does; returns its status record."""
        op_id = str(uuid.uuid4())
        new_request()
        with mock.patch.object(frappe, "enqueue", side_effect=lambda method, **kw: self.queued.append(kw)):
            rate_master.start_suggest(boq=self.boq, sheet_name=self.sheet, op_id=op_id)
            frappe.db.commit()
        job = next(j for j in self.queued if j["op_id"] == op_id)
        before = (frappe.db.count(_BCS, {"boq": self.boq}), frappe.db.count(_PRICING, {"boq": self.boq}))
        with mock.patch.object(extraction, "run_extraction", side_effect=extract), \
                mock.patch("anthropic.Anthropic", side_effect=AssertionError("BCS-4 tests never call the model")), \
                mock.patch.object(rate_match, "match_enabled", return_value=False), \
                mock.patch.object(frappe, "enqueue", side_effect=lambda method, **kw: self.queued.append(kw)):
            frappe.set_user("Guest")
            new_request()
            background_ops.run(op_id=job["op_id"], work=job["work"], work_kwargs=job["work_kwargs"])
        frappe.set_user("Administrator")
        new_request()
        self.assertEqual((frappe.db.count(_BCS, {"boq": self.boq}), frappe.db.count(_PRICING, {"boq": self.boq})), before,
                         "a Suggest run never writes a price or a cost")
        return get_status(op_id=op_id)

    def _current(self, row):
        return frappe.get_all(_EDIT, filters={"boq": self.boq, "sheet_name": self.sheet, "excel_row": row,
                                              "committed_version": 1, "is_current": 1}, pluck="name")

    def _all(self, row):
        return frappe.get_all(_EDIT, filters={"boq": self.boq, "sheet_name": self.sheet, "excel_row": row,
                                              "committed_version": 1}, fields=["name", "is_current", "edits"])

    def test_new_run_replaces_saved_edit(self):
        """(+) R-BCS-140: a complete run that read rows 2 and 3 leaves neither with a current edit; both records still exist,
        frozen (history, never deleted); the page's read returns nothing for the sheet."""
        status = self._run(_extract_reads([2, 3]))
        self.assertEqual(status["state"], "finished", status.get("error"))
        self.assertEqual(status["result"]["status"], "success")
        for row in (2, 3):
            self.assertEqual(self._current(row), [])
            kept = self._all(row)
            self.assertEqual(len(kept), 1)
            self.assertEqual(kept[0].is_current, 0)
            self.assertIn("thickness_sqmm", kept[0].edits)
        self.assertEqual(get_row_helper_edits(boq_name=self.boq, sheet_name=self.sheet, committed_version=1)["rows"], {})

    def test_new_run_keeps_edits_on_rows_it_did_not_write(self):
        """(-) R-BCS-140: a run that wrote row 2 only (here a partial run: it halted before row 3) replaces row 2's edit and
        leaves row 3's current and unchanged."""
        status = self._run(_extract_reads([2]))
        self.assertEqual(status["state"], "finished", status.get("error"))
        self.assertEqual(status["result"]["status"], "partial")
        self.assertEqual(self._current(2), [])
        self.assertEqual(len(self._current(3)), 1)
        rows = get_row_helper_edits(boq_name=self.boq, sheet_name=self.sheet, committed_version=1)["rows"]
        self.assertEqual(list(rows), [3])
        self.assertEqual(rows[3]["thickness_sqmm"]["value"], "2.5")

    def test_fail_closed_run_keeps_every_edit(self):
        """(-) Question 3 (a): a pass whose AI did not run (settings off / no key) writes all-null rows but read nothing --
        every edit stays current."""
        status = self._run(_extract_reads([2, 3], ai_status="disabled"))
        self.assertEqual(status["state"], "finished", status.get("error"))
        for row in (2, 3):
            self.assertEqual(len(self._current(row)), 1)

    def test_replace_helper_alone_never_raises_and_counts(self):
        """The helper on its own: freezes only the given rows' current records, returns the count, and swallows an error
        (a side effect must never fail the run) -- logged once."""
        self.assertEqual(helper_edits.supersede_edits_for_rows(self.boq, self.sheet, [3], 1), 1)
        self.assertEqual(self._current(3), [])
        self.assertEqual(len(self._current(2)), 1)
        self.assertEqual(helper_edits.supersede_edits_for_rows(self.boq, self.sheet, [], 1), 0)
        with mock.patch.object(frappe, "get_all", side_effect=RuntimeError("fixture: the read failed")), \
                mock.patch("frappe.log_error") as log_error:
            self.assertEqual(helper_edits.supersede_edits_for_rows(self.boq, self.sheet, [2], 1), 0)
        self.assertEqual(log_error.call_count, 1)
        self.assertEqual(len(self._current(2)), 1)
