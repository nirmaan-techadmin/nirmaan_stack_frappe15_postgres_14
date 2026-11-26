# Copyright (c) 2026, Nirmaan (Stratos Infra Technologies Pvt. Ltd.) and contributors
# For license information, please see license.txt

"""BCS-5: the BoQ summary's stored inputs and its server half (api/boq/wizard/boq_summary.py).

What each test protects:
(+) get / save / supersede / back to system figure: the area, the ticks and both installation parts are stored per BoQ, one
    current record, every earlier field carried; "" puts a part back to the system's figure.
(+) the floor-cutting rule on a worked-example-shaped fixture: a Yes tray row of a ticked sheet that the BoQ charges for and
    that is measured in a length counts (qty x the live Rs per metre); the helper edit's reading beats the Suggest run's.
(+) the length guard: a "Nos." row is mentioned-not-added, a "Rmt." row counts; LENGTH_UNITS holds every match_text length
    spelling except "mt" (Question 1, point 1 = (b)).
(-) an uncharged Yes row is not counted (mentioned, with its reason); a row with no reading is only counted.
(-) a non-cost user (Procurement, PMO) is refused on get and save, with the BCS cost words, and nothing is written.
(-) the summary writes no price and no cost: BoQ Cell Pricing, BoQ Row BCS Rate and BoQ Row Helper Edit counts are unchanged.
(+) the revision carry copies the area and both overrides and maps the ticks (an unmapped tick drops), through
    confirm_revision_mapping; (-) a source with no record copies nothing.

Fixture-only (fixture BoQs, purged at the end). The Suggest population is faked at the extraction edge (assemble_population),
so no classifier, rate file or model is involved. The Pricing Inputs are read LIVE (read only) and compared with the database's
own values. Run with `bench --site dev2.localhost run-tests --module nirmaan_stack.api.boq.wizard.test_boq_summary`.
"""

import json
from unittest import mock

import frappe
from frappe.tests.utils import FrappeTestCase

from nirmaan_stack.api.boq.wizard import boq_summary
from nirmaan_stack.api.boq.wizard.boq_summary import (
    LENGTH_UNITS,
    carry_summary_inputs,
    get_boq_summary_inputs,
    is_length_unit,
    save_boq_summary_inputs,
)
from nirmaan_stack.api.boq.wizard.test_bcs3_role_check import PMO, PROCUREMENT, _AsUser
from nirmaan_stack.api.boq.wizard.test_classify import _new_boq, _new_sheet, _node
from nirmaan_stack.api.boq.wizard.test_review_screen import _cleanup_project, _make_project
from nirmaan_stack.services.boq_fixture_teardown import purge_boq, purge_docs

_STORE = "BoQ Summary Inputs"
_POP = "nirmaan_stack.services.boq_rate_master.extraction.assemble_population"
EA, EB, HV, SP = "Elec A ", "Elec B", "HVAC", "Spec"  # "Elec A " keeps its trailing space VERBATIM (#152)


def _live_amount(item):
    """The active Pricing Input's rates.amount, read straight from the database (the figure the summary must use)."""
    for r in frappe.get_all("BoQ Rate Master Item", filters={"active": 1}, fields=["attributes", "rates"]):
        a = json.loads(r.attributes) if isinstance(r.attributes, str) else (r.attributes or {})
        if a.get("item") == item:
            return float((json.loads(r.rates) if isinstance(r.rates, str) else r.rates)["amount"])
    return None


def _pop(rows):
    return [{"excel_row": er, "category_id": cat, "discipline": disc} for er, cat, disc in rows]


POPULATION = {
    EA: _pop([(248, "cabletray_raceway", "Electrical"), (249, "cabletray_raceway", "Electrical"),
              (250, "cabletray_raceway", "Electrical"), (251, "cabletray_raceway", "Electrical"),
              (252, "cabletray_raceway", "Electrical"), (253, "cabletray_raceway", "Electrical"),
              (260, "wiring_cabling", "Electrical")]),
    EB: _pop([(300, "cabletray_raceway", "Electrical"), (301, "db_switchgear", "Electrical")]),
    HV: _pop([(400, "hvac_ducting", "HVAC"), (401, "hvac_ducting", "HVAC"), (402, "cabletray_raceway", "Electrical")]),
}


def _fake_population(boq, sheet_name):
    return 1, [dict(r) for r in POPULATION.get(sheet_name, [])]


class TestBoqSummary(FrappeTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = _make_project()
        frappe.db.set_value("Projects", cls.project.name, "carpet_area", 13765, update_modified=False)
        cls.boq = _new_boq(cls.project.name, "Summary BoQ")
        cls.other = _new_boq(cls.project.name, "Summary BoQ revision")
        cls.docs = {}
        for order, (name, treat) in enumerate(((EA, "data"), (EB, "data"), (HV, "data"), (SP, "master_preamble")), start=1):
            doc = _new_sheet(cls.boq, name, 1)
            frappe.db.set_value("BoQ Sheet", doc, {"sheet_order": order, "treat_as": treat}, update_modified=False)
            cls.docs[name] = doc
        # Elec A: 248 Mtrs. 30 / 249 Rmt. 40 / 250 Nos. 4 / 251 uncharged / 252 no reading / 253 reading No; Elec B: 300 Mtrs 20
        for er, unit, qty in ((248, "Mtrs.", 30), (249, "Rmt.", 40), (250, "Nos.", 4), (251, "Mtrs", 10), (252, "Mtrs", 5),
                              (253, "Mtrs", 7)):
            n = _node(cls.boq, cls.docs[EA], "Line Item", er, None, f"floor trunking row {er}", er, qty=qty)
            frappe.db.set_value("BOQ Nodes", n, "unit", unit, update_modified=False)
        n = _node(cls.boq, cls.docs[EB], "Line Item", 300, None, "floor trunking B", 1, qty=20)
        frappe.db.set_value("BOQ Nodes", n, "unit", "Mtrs", update_modified=False)
        for sheet, er, kind in ((EA, 248, "install_rate"), (EA, 249, "install_rate"), (EA, 250, "install_rate"),
                                (EA, 251, "supply_rate"), (EA, 252, "install_rate"), (EA, 253, "install_rate"),
                                (EB, 300, "combined_rate")):
            frappe.get_doc({"doctype": "BoQ Cell Pricing", "boq": cls.boq, "sheet_name": sheet, "excel_row": er,
                            "col_letter": "G", "committed_version": 1, "pricing_version": 1, "rate_kind": kind,
                            "rate": 500, "is_current": 1}).insert(ignore_permissions=True)
        for sheet, results in ((EA, [(248, "Yes"), (249, "No"), (250, "Yes"), (251, "Yes"), (253, "No")]), (EB, [(300, "Yes")])):
            frappe.get_doc({"doctype": "BoQ Rate Suggestion Run", "boq": cls.boq, "sheet_name": sheet, "committed_version": 1,
                            "status": "complete", "ai_status": "ran", "active": 1,
                            "results": json.dumps([{"excel_row": er, "category_id": "cabletray_raceway",
                                                    "attributes": {"floor_cutting": {"value": v}}} for er, v in results])
                            }).insert(ignore_permissions=True)
        # The saved helper edit outranks the run: row 249 reads Yes although the run said No.
        frappe.get_doc({"doctype": "BoQ Row Helper Edit", "boq": cls.boq, "sheet_name": EA, "excel_row": 249,
                        "committed_version": 1, "edit_version": 1, "is_current": 1,
                        "edits": json.dumps({"floor_cutting": {"value": "Yes", "from_kind": "supply"}})}
                       ).insert(ignore_permissions=True)
        frappe.db.commit()
        cls.install_rate = _live_amount("elec_bcs_install_per_sqft")
        cls.tray_rate = _live_amount("tray_cutting_amount")

    @classmethod
    def tearDownClass(cls):
        frappe.db.rollback()
        for boq in (cls.boq, cls.other):
            for dt in (_STORE, "BoQ Row Helper Edit", "BoQ Rate Suggestion Run", "BoQ Cell Pricing"):
                try:
                    frappe.db.delete(dt, {"boq": boq})
                    frappe.db.commit()
                except Exception:  # noqa: BLE001 -- report, never strand the rest
                    frappe.db.rollback()
                    print(f"cleanup failed: {dt} {boq}")
            purge_docs("BOQ Nodes", {"boq": boq})
            purge_docs("BoQ Sheet", {"boq": boq})
            frappe.db.commit()
            purge_boq(boq)
        _cleanup_project(cls.project.name)
        super().tearDownClass()

    def setUp(self):
        frappe.set_user("Administrator")
        frappe.db.delete(_STORE, {"boq": ["in", [self.boq, self.other]]})
        frappe.db.commit()
        self.p = mock.patch(_POP, side_effect=_fake_population)
        self.p.start()

    def tearDown(self):
        self.p.stop()
        frappe.set_user("Administrator")

    def _records(self, boq=None):
        return frappe.get_all(_STORE, filters={"boq": boq or self.boq}, order_by="input_version asc",
                              fields=["input_version", "is_current", "area_sqft"])

    @staticmethod
    def _counts():
        return tuple(frappe.db.count(dt) for dt in ("BoQ Cell Pricing", "BoQ Row BCS Rate", "BoQ Row Helper Edit"))

    # -- (+) get with no record --------------------------------------------------------------------------------------
    def test_get_without_record_lists_priceable_sheets_and_default_ticks(self):
        out = get_boq_summary_inputs(boq=self.boq)
        self.assertFalse(out["has_record"])
        self.assertEqual([s["sheet_name"] for s in out["sheets"]], [EA, EB, HV])  # Spec (general specs) not listed
        self.assertEqual(out["default_ticks"], [EA, EB])  # HVAC: 1 of 3 Suggest rows Electrical -> not ticked
        self.assertEqual(out["ticked"], [EA, EB])
        self.assertEqual(out["carpet_area"], 13765)
        self.assertEqual(out["rates"], {"install_per_sqft": self.install_rate, "tray_cutting": self.tray_rate})
        self.assertIsNone(out["area_sqft"])
        self.assertIsNone(out["installation"]["total"])  # no area: the screen asks for it

    # -- (+) / (-) the floor rule ------------------------------------------------------------------------------------
    def test_floor_rule_caught_mentioned_and_no_reading(self):
        floor = get_boq_summary_inputs(boq=self.boq)["floor"]
        self.assertEqual([(r["sheet_name"], r["excel_row"]) for r in floor["caught"]], [(EA, 248), (EA, 249), (EB, 300)])
        self.assertEqual(floor["metres"], 90)
        self.assertEqual(floor["system_amount"], 90 * self.tray_rate)
        reasons = {r["excel_row"]: r["reason"] for r in floor["mentioned"]}
        self.assertEqual(set(reasons), {250, 251})
        self.assertIn("not a length", reasons[250])  # Nos.
        self.assertIn("does not charge", reasons[251])  # uncharged Yes row: not counted
        self.assertEqual(floor["no_reading_rows"], 1)  # row 252 (253 reads No: not a Yes, not counted at all)

    def test_unticked_sheet_rows_are_not_counted(self):
        save_boq_summary_inputs(boq=self.boq, covered_sheets=json.dumps([EA]))
        floor = get_boq_summary_inputs(boq=self.boq)["floor"]
        self.assertEqual([r["excel_row"] for r in floor["caught"]], [248, 249])
        self.assertEqual(floor["metres"], 70)

    def test_length_guard(self):
        for unit in ("Rmt.", "Mtrs.", "MTS", "Mts.", "Rmtrs", "m", "R.M.T", "Metre", "RM"):
            self.assertTrue(is_length_unit(unit), unit)
        for unit in ("Nos.", "Nos", "Sqm", "", None, "mt", "MT", "Kg", "Set"):
            self.assertFalse(is_length_unit(unit), unit)

    def test_length_units_hold_every_match_text_length_spelling_but_mt(self):
        from nirmaan_stack.services.boq_rate_match.match_text import _UNITS

        folded = {u.replace(".", "").replace(" ", "") for u in _UNITS["rmt"]} - {"mt"}
        self.assertEqual(folded - LENGTH_UNITS, set())
        self.assertNotIn("mt", LENGTH_UNITS)

    # -- (+) get / save / supersede / back to system figure ----------------------------------------------------------
    def test_save_supersede_edit_remove_and_back_to_system(self):
        before = self._counts()
        out = save_boq_summary_inputs(boq=self.boq, area_sqft="20000")
        inst = out["installation"]
        self.assertEqual(inst["area_part_system"], 20000 * self.install_rate)
        self.assertEqual(inst["total"], 20000 * self.install_rate + 90 * self.tray_rate)
        self.assertFalse(inst["area_part_changed"] or inst["floor_part_changed"])
        out = save_boq_summary_inputs(boq=self.boq, area_cost_override="750000")
        self.assertEqual((out["installation"]["area_part"], out["installation"]["area_part_changed"]), (750000, True))
        self.assertEqual(out["area_sqft"], 20000)  # carried
        out = save_boq_summary_inputs(boq=self.boq, floor_cut_override="0")  # removed
        self.assertEqual((out["installation"]["floor_part"], out["installation"]["floor_part_changed"]), (0, True))
        self.assertEqual(out["installation"]["total"], 750000)
        out = save_boq_summary_inputs(boq=self.boq, area_cost_override="", floor_cut_override="")  # back to system figure
        inst = out["installation"]
        self.assertFalse(inst["area_part_changed"] or inst["floor_part_changed"])
        self.assertEqual(inst["total"], 20000 * self.install_rate + 90 * self.tray_rate)
        recs = self._records()
        self.assertEqual([(r.input_version, r.is_current) for r in recs], [(1, 0), (2, 0), (3, 0), (4, 1)])
        self.assertFalse(save_boq_summary_inputs(boq=self.boq, area_sqft="20000")["wrote"])  # nothing changed
        self.assertEqual(len(self._records()), 4)
        self.assertEqual(self._counts(), before)

    def test_three_part_states_survive_a_desk_style_save(self):
        """Question 3 (a): Check 0 = system figure, Check 1 + figure = edited, Check 1 + 0 = removed - and a document-layer save
        (as Desk makes) keeps all three (Frappe writes a blank Currency as 0, which is why the Check exists)."""
        save_boq_summary_inputs(boq=self.boq, area_sqft="20000", area_cost_override="500", floor_cut_override="0")

        def desk_save_then_read():
            name = frappe.get_all(_STORE, filters={"boq": self.boq, "is_current": 1}, pluck="name")[0]
            frappe.get_doc(_STORE, name).save(ignore_permissions=True)
            frappe.db.commit()
            return get_boq_summary_inputs(boq=self.boq)["installation"]

        inst = desk_save_then_read()
        self.assertEqual((inst["area_part"], inst["area_part_changed"]), (500, True))  # edited
        self.assertEqual((inst["floor_part"], inst["floor_part_changed"]), (0, True))  # removed
        save_boq_summary_inputs(boq=self.boq, area_cost_override="")
        inst = desk_save_then_read()
        self.assertEqual((inst["area_part"], inst["area_part_changed"]), (20000 * self.install_rate, False))  # system figure
        self.assertEqual((inst["floor_part"], inst["floor_part_changed"]), (0, True))

    def test_ticks_and_area_clear(self):
        save_boq_summary_inputs(boq=self.boq, area_sqft="500", covered_sheets=json.dumps([HV, EA]))
        out = get_boq_summary_inputs(boq=self.boq)
        self.assertEqual(out["ticked"], [EA, HV])  # sheet order, not the order sent
        self.assertEqual(out["covered_sheets"], [EA, HV])
        out = save_boq_summary_inputs(boq=self.boq, covered_sheets="", area_sqft="")
        self.assertEqual(out["ticked"], [EA, EB])  # back to the default ticks
        self.assertIsNone(out["area_sqft"])
        self.assertIsNone(save_boq_summary_inputs(boq=self.boq, area_sqft="0")["area_sqft"])  # 0 sq ft = not entered

    def test_bad_inputs_are_refused_and_write_nothing(self):
        for kwargs in ({"area_sqft": "-1"}, {"area_sqft": "abc"}, {"covered_sheets": json.dumps(["Nope"])},
                       {"covered_sheets": json.dumps([SP])}, {"area_cost_override": "x"}, {"floor_cut_override": "-5"}):
            with self.assertRaises(frappe.ValidationError, msg=str(kwargs)):
                save_boq_summary_inputs(boq=self.boq, **kwargs)
            frappe.db.rollback()
        self.assertEqual(self._records(), [])

    # -- (-) who may see and change it -------------------------------------------------------------------------------
    def test_non_cost_user_is_refused_on_get_and_save(self):
        for user in (PROCUREMENT, PMO):
            with _AsUser(user):
                with self.assertRaises(frappe.PermissionError) as cm:
                    get_boq_summary_inputs(boq=self.boq)
                self.assertIn("Only Admin and Estimates users may see or change BCS cost.", str(cm.exception))
                with self.assertRaises(frappe.PermissionError):
                    save_boq_summary_inputs(boq=self.boq, area_sqft="1000")
            frappe.db.rollback()
        self.assertEqual(self._records(), [])

    # -- (-) no price, no cost --------------------------------------------------------------------------------------
    def test_summary_writes_no_price_or_cost(self):
        before = self._counts()
        get_boq_summary_inputs(boq=self.boq)
        self.assertEqual(self._counts(), before)
        for kwargs in ({"area_sqft": "1234"}, {"covered_sheets": json.dumps([EB])}, {"area_cost_override": "1"},
                       {"floor_cut_override": "0"}, {"area_cost_override": "", "floor_cut_override": ""}):
            save_boq_summary_inputs(boq=self.boq, **kwargs)
            self.assertEqual(self._counts(), before, kwargs)
        source = open(boq_summary.__file__, encoding="utf-8").read()
        for writer in ("save_cell_price", "save_row_bcs_rates", "save_row_helper_edit", "set_value(\"BoQ Cell Pricing"):
            self.assertNotIn(writer, source)

    # -- the revision carry ------------------------------------------------------------------------------------------
    def test_carry_maps_ticks_drops_unmapped_and_copies_area_and_overrides(self):
        save_boq_summary_inputs(boq=self.boq, area_sqft="20000", covered_sheets=json.dumps([EA, EB]),
                                area_cost_override="750000", floor_cut_override="0")
        res = carry_summary_inputs(self.boq, self.other, {EA: "Elec A rev", HV: "HVAC"})
        self.assertEqual(res, {"copied": True, "dropped_ticks": [EB], "ticks": ["Elec A rev"]})
        rec = frappe.get_all(_STORE, filters={"boq": self.other, "is_current": 1},
                             fields=["area_sqft", "covered_sheets", "area_cost_override", "area_cost_overridden",
                                     "floor_cut_override", "floor_cut_overridden"])
        self.assertEqual(len(rec), 1)
        r = rec[0]
        self.assertEqual((r.area_sqft, r.area_cost_override, r.area_cost_overridden, r.floor_cut_override,
                          r.floor_cut_overridden), (20000, 750000, 1, 0, 1))
        cov = json.loads(r.covered_sheets) if isinstance(r.covered_sheets, str) else r.covered_sheets
        self.assertEqual(cov, {"sheets": ["Elec A rev"]})

    def test_carry_from_a_source_with_no_record_copies_nothing(self):
        self.assertEqual(carry_summary_inputs(self.boq, self.other, {EA: EA}),
                         {"copied": False, "dropped_ticks": [], "ticks": None})
        self.assertEqual(self._records(self.other), [])


class TestCarryThroughConfirmRevisionMapping(FrappeTestCase):
    """The carry rides confirm_revision_mapping (the one place both revision entry paths end), in its transaction."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from nirmaan_stack.api.boq.wizard.test_revision_entry import _commit_sheet, _make_boq
        from nirmaan_stack.api.boq.wizard.test_revision_entry import _make_project as make_project

        cls.project = make_project()
        cls.original = _make_boq(cls.project.name, origin="upload", boq_name="BCS5 ORIG")
        _commit_sheet(cls.original.name, sheet="Electrical", version=1)
        _commit_sheet(cls.original.name, sheet="Lighting", version=1)

    @classmethod
    def tearDownClass(cls):
        from nirmaan_stack.api.boq.wizard.test_revision_mapping import _cleanup_all

        frappe.db.rollback()
        for b in frappe.get_all("BOQs", filters={"project": cls.project.name}, pluck="name"):
            frappe.db.delete(_STORE, {"boq": b})
        frappe.db.commit()
        _cleanup_all(cls.project.name)
        super().tearDownClass()

    def test_confirm_carries_area_overrides_and_mapped_ticks(self):
        from nirmaan_stack.api.boq.wizard.revision import confirm_revision_mapping
        from nirmaan_stack.api.boq.wizard.test_revision_mapping import _READ_TABS, _make_revision

        boq_summary._supersede(self.original.name, [], {"area_sqft": 9000, "covered_sheets": ["Electrical", "Lighting"],
                                                        "area_part": 400000, "floor_part": None})
        frappe.db.commit()
        rev = _make_revision(self.project.name, self.original.name)
        mapping = [{"sheet_name": "Electrical", "source_sheet_name": "Electrical"},
                   {"sheet_name": "Lighting v2", "source_sheet_name": None, "declared_new": True}]
        with mock.patch(_READ_TABS, return_value=["Electrical", "Lighting v2"]):
            res = confirm_revision_mapping(rev.name, mapping)
        self.assertEqual(res["summary_inputs"], {"copied": True, "dropped_ticks": ["Lighting"], "ticks": ["Electrical"]})
        rec = frappe.get_all(_STORE, filters={"boq": rev.name, "is_current": 1},
                             fields=["area_sqft", "area_cost_override", "area_cost_overridden", "floor_cut_overridden"])
        self.assertEqual([(r.area_sqft, r.area_cost_override, r.area_cost_overridden, r.floor_cut_overridden) for r in rec],
                         [(9000, 400000, 1, 0)])
