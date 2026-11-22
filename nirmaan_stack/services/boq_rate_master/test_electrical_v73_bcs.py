# Copyright (c) 2026, Nirmaan (Stratos Infra Technologies Pvt. Ltd.) and contributors
# For license information, please see license.txt

"""BCS-2 -- Electrical v73's file and the two config keys it brings. Reads asset files and calls pure functions only: no row is
created, changed or deleted, so there is nothing to clean up.

What it protects: no BoQ price pipeline moved from v72 to v73; the new costs exist and refuse like the price; the Rs 42 input is
there under its exact name and marked for the BoQ summary; a margin is a live reference, never a number."""

import copy
import json
import os

import frappe
from frappe.tests.utils import FrappeTestCase

from nirmaan_stack.services.boq_rate_master import config_validation, csv_exporter, csv_importer

DATA = os.path.join(os.path.dirname(__file__), "data")
KIND = "electrical_pricing_input"
FT2 = "elec_bcs_install_per_sqft"


def _asset(version):
    with open(os.path.join(DATA, "rate_master_electrical_all_v%d.json" % version), encoding="utf-8") as fh:
        return json.load(fh)


def _canon(value):
    return json.dumps(value, sort_keys=True)


class TestElectricalV73Bcs(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.v72, cls.v73 = _asset(72), _asset(73)
        cls.c72 = {c["category_id"]: c for c in cls.v72["category_configs"]}
        cls.c73 = {c["category_id"]: c for c in cls.v73["category_configs"]}
        cls.rates = {(i["kind"], i["attributes"]["item"]): i["rates"] for i in cls.v73["items"] if i["kind"] == KIND}

    def _steps(self, cat, pid, step):
        return [s for s in self.c73[cat]["pipelines"][pid]["steps"] if s["step"] == step]

    # ---- the file ----
    def test_01_every_v72_boq_pipeline_is_byte_equal_in_v73(self):
        n = 0
        for cat, cfg in self.c72.items():
            for pid, pl in cfg["pipelines"].items():
                if "bcs" in pid:
                    continue
                n += 1
                self.assertEqual(_canon(pl), _canon(self.c73[cat]["pipelines"][pid]), (cat, pid))
        self.assertGreater(n, 12, "every category has at least one price pipeline")

    def test_02_only_the_declared_cost_pipelines_moved(self):
        moved, new = set(), set()
        for cat, cfg in self.c73.items():
            for pid, pl in cfg["pipelines"].items():
                old = self.c72[cat]["pipelines"].get(pid)
                if old is None:
                    new.add(pid)
                elif _canon(old) != _canon(pl):
                    moved.add(pid)
        self.assertEqual(moved, {"cable_bcs", "popup_bcs", "db_buildup_bcs", "swsock_bcs"})
        self.assertEqual(new, {"jb_bcs", "indsock_bcs"})

    def test_03_every_v72_item_is_unchanged_and_one_is_added(self):
        self.assertEqual([_canon(i) for i in self.v72["items"]], [_canon(i) for i in self.v73["items"][:-1]])
        self.assertEqual(self.v73["items"][-1]["attributes"]["item"], FT2)

    def test_04_jb_and_indsock_costs_never_round(self):
        for cat, pid in (("junction_box_raceway", "jb_bcs"), ("industrial_sockets", "indsock_bcs")):
            self.assertEqual(self._steps(cat, pid, "roundup"), [], pid)
            for s in self._steps(cat, pid, "component_ref"):
                self.assertEqual([st.get("round") for st in s["rate_stages"]], [None], (pid, s["name"]))

    def test_05_the_cost_sums_refuse_with_the_price_sides_own_words(self):
        for cat, price, cost in (("db_switchgear", "db_buildup_supply", "db_buildup_bcs"), ("switches_sockets", "swsock_boq", "swsock_bcs")):
            want = self._steps(cat, price, "sum_components")[0]["none_refusal"]
            self.assertTrue(want)
            self.assertEqual(self._steps(cat, cost, "sum_components")[0]["none_refusal"], want)
        # point wiring's price side carries no such sentence (both its sides stop at circuit_fit), so none was invented
        self.assertNotIn("none_refusal", self._steps("point_wiring", "pw_boq_supply", "sum_components")[0])
        self.assertNotIn("none_refusal", self._steps("point_wiring", "pw_boq_install", "sum_components")[0])
        self.assertNotIn("none_refusal", self._steps("point_wiring", "pw_bcs", "sum_components")[0])

    def test_06_NEGATIVE_no_cost_output_name_collides_with_a_price_output(self):
        for cat, cfg in self.c73.items():
            price = {o for pid, p in cfg["pipelines"].items() if "bcs" not in pid for o in p["output"]}
            cost = {o for pid, p in cfg["pipelines"].items() if "bcs" in pid for o in p["output"]}
            self.assertEqual(price & cost, set(), cat)
            self.assertTrue(all(o.startswith("bcs_") for o in cost), (cat, cost))

    def test_07_every_discount_a_new_cost_reads_is_one_its_price_reads(self):
        for cat, price, cost in (("junction_box_raceway", "jb_boq", "jb_bcs"), ("industrial_sockets", "indsock_boq", "indsock_bcs"),
                                 ("wiring_cabling", "cable_boq", "cable_bcs"), ("popup_boxes", "popup_boq", "popup_bcs")):
            def discounts(pid):
                return {s["ref"]["item"] for s in self._steps(cat, pid, "rate_ref") if s["target"] == "discount"}
            self.assertTrue(discounts(cost), (cat, cost))
            self.assertEqual(discounts(cost), discounts(price), (cat, cost))

    # ---- the Rs 42 input ----
    def test_08_the_rs_42_input_under_its_exact_name_and_marked(self):
        hit = [i for i in self.v73["items"] if i["attributes"].get("item") == FT2]
        self.assertEqual(len(hit), 1)
        self.assertEqual(hit[0]["attributes"]["name"], "Electrical installation cost per sq ft (BCS)")
        self.assertEqual(hit[0]["rates"], {"amount": 42.0})   # owner 4b: the rupee column Electrical already has, never `rate`
        self.assertEqual(hit[0]["unit"], "Rs per sq ft")
        self.assertEqual(self.c73["electrical_pricing_inputs"]["summary_inputs"], [FT2])

    def test_09_its_used_by_line_reads_boq_summary(self):
        n, cats = csv_exporter.pricing_input_used_by(self.c73)[FT2]
        self.assertEqual(csv_exporter.pricing_input_used_by_text(n, cats), "BoQ summary")

    def test_10_NEGATIVE_without_the_mark_it_is_not_used_and_other_inputs_keep_their_text(self):
        bare = copy.deepcopy(self.c73)
        del bare["electrical_pricing_inputs"]["summary_inputs"]
        before, after = csv_exporter.pricing_input_used_by(bare), csv_exporter.pricing_input_used_by(self.c73)
        self.assertNotIn(FT2, before)
        self.assertEqual({k: v for k, v in after.items() if k != FT2}, before)
        self.assertEqual(csv_exporter.pricing_input_used_by_text(2, ["a", "BoQ summary"]), "BoQ summary, a (2 uses)")

    def test_11_an_input_the_summary_reads_cannot_be_deleted_and_an_unread_one_can(self):
        used = csv_exporter.pricing_input_used_by(self.c73)
        self.assertIn("BoQ summary", csv_importer.refuse_if_in_use(FT2, used, "deactivate"))
        self.assertIsNone(csv_importer.refuse_if_in_use("no_such_input", used, "deactivate"))

    # ---- bcs_default_margin / summary_inputs validation ----
    def test_12_the_whole_file_validates_and_every_margin_resolves(self):
        for c in self.v73["category_configs"]:
            config_validation._validate_config(dict(c, discipline="Electrical"))
        self.assertEqual(config_validation.bcs_problems(self.v73["category_configs"], self.rates), [])

    def test_13_NEGATIVE_a_margin_that_is_a_number_or_names_no_input_is_refused(self):
        base = {"components": ["x"], "ref": {"kind": KIND, "item": "indsock"}, "field": "supply_markup"}
        bad = [
            0.25, {"entries": []}, {"entries": [0.25]}, {"entries": [dict(base, value=0.25)]}, {"entries": [dict(base, field="margin")]},
            {"entries": [dict(base, ref={"kind": "junction_box", "item": "indsock"})]}, {"entries": [dict(base, ref={"kind": KIND, "item": ""})]},
            {"entries": [dict(base, components=[])]}, {"entries": [dict(base, when={})]}, {"entries": [base], "default": 0.25},
        ]
        for m in bad:
            with self.assertRaises(frappe.ValidationError, msg=str(m)):
                config_validation._validate_bcs_keys({"bcs_default_margin": m})
        config_validation._validate_bcs_keys({"bcs_default_margin": {"entries": [base]}})

    def test_14_NEGATIVE_a_margin_on_a_missing_input_a_missing_field_or_a_zero_ratio_is_named(self):
        def found(item, field, rates):
            cfg = {"category_id": "c", "bcs_default_margin": {"entries": [{"ref": {"kind": KIND, "item": item}, "field": field}]}}
            return config_validation.bcs_problems([cfg], rates)

        rates = {(KIND, "a"): {"discount": 0.3}, (KIND, "b"): {"ratio": 0}, (KIND, "c"): {"supply_markup": 0.4}}
        self.assertIn("not an active Pricing Input", found("zzz", "supply_markup", rates)[0])
        self.assertIn("no usable 'supply_markup'", found("a", "supply_markup", rates)[0])
        self.assertIn("no usable 'ratio'", found("b", "ratio", rates)[0])
        self.assertEqual(found("c", "supply_markup", rates), [])

    def test_15_NEGATIVE_summary_inputs_must_be_a_list_of_real_ids(self):
        for bad in ("x", [], [1], ["a", "a"], [""]):
            with self.assertRaises(frappe.ValidationError, msg=str(bad)):
                config_validation._validate_bcs_keys({"summary_inputs": bad})
        problems = config_validation.bcs_problems([{"category_id": "c", "summary_inputs": ["nope"]}], self.rates)
        self.assertIn("'nope' is not an active Pricing Input", problems[0])

    def test_16_NEGATIVE_a_config_without_the_keys_is_untouched(self):
        config_validation._validate_bcs_keys({})
        self.assertEqual(config_validation.bcs_problems([{"category_id": "c"}], self.rates), [])

    def test_17_the_import_gate_calls_the_check_and_refuses_before_any_write(self):
        """`validate_delegated_sections` is the ONE call the loader and the config editor make; given the items of the payload it
        reads no live Pricing Input. A margin naming a missing input must stop it."""
        good = [dict(copy.deepcopy(c), discipline="Electrical") for c in self.v73["category_configs"]]
        config_validation.validate_delegated_sections(good, self.v73["items"], label="t")
        bad = copy.deepcopy(good)
        [c for c in bad if c["category_id"] == "junction_box_raceway"][0]["bcs_default_margin"]["entries"][0]["ref"]["item"] = "no_such_input"
        with self.assertRaises(frappe.ValidationError) as cm:
            config_validation.validate_delegated_sections(bad, self.v73["items"], label="t")
        self.assertIn("no_such_input", str(cm.exception))
