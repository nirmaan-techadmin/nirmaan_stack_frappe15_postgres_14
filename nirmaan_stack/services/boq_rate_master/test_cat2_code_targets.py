"""CAT-2 (2026-11-27) -- THE CODE TARGETS (owner 2026-11-26 00:10 / 01:16, R1; ANSWER to CAT2-4 QR-FORM). Every check has a NEGATIVE.

A catalogue value a code rule picks as ONE target is named in the config, `list_spec.code_targets.<role>` = {attr, value | values,
section?}, and the load gate refuses a role no active SKU of its scope carries, naming the place -- instead of a helper silently missing
it. `paint_row.family` (an existing key) is checked the same way. The values here are picked FROM the committed asset's own SKUs (never
typed), so the module types no catalogue word.

  T1+  a code_targets block naming carried values (own kinds, a delegated section's kinds, a values list) and v90's paint_row.family:
       0 refusals; config_validation accepts the shape.
  T1-  a value no SKU carries (a rename), the carrier deactivated (removed from the active items), an attribute the scope's SKUs do not
       carry (STRICT), a section that is not delegated, paint_row.family renamed: each REFUSED with the config and the path named.
  SHAPE config_validation refuses: value AND values, neither, an empty list, a duplicate, a non-snake_case role, a non-object.
Run: bench --site localhost run-tests --module nirmaan_stack.services.boq_rate_master.test_cat2_code_targets
"""
import copy
import json
import os

import frappe
from frappe.tests.utils import FrappeTestCase

from nirmaan_stack.services.boq_rate_master import catalogue_gate as CG
from nirmaan_stack.services.boq_rate_master import config_validation, loader

DATA = os.path.join(os.path.dirname(loader.__file__), "data")
V90 = "rate_master_hvac_all_v90.json"
VALVE, DUCT = "hvac_valve_package", "hvac_ducting"


def _asset(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as fh:
        a = json.load(fh)
    for c in a["category_configs"]:
        c["discipline"] = a["discipline"]
    return a


def _refusals(configs, items):
    return [p for p in CG.reference_problems(configs, items, "HVAC") if p["severity"] == CG.REFUSE]


class TestCodeTargets(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.a = _asset(V90)
        cls.by = {c["category_id"]: c for c in cls.a["category_configs"]}
        v = cls.by[VALVE]
        fam = v["list_spec"]["family_attribute_id"]
        own = sorted({i["attributes"][fam] for i in cls.a["items"] if i["kind"] in v["item_kinds"] and isinstance(i["attributes"].get(fam), str)})
        sec = [s for s in v["list_spec"]["sections"] if s.get("category_id")][0]
        tgt = cls.by[sec["category_id"]]
        tfam = tgt["list_spec"]["family_attribute_id"]
        sec_vals = sorted({i["attributes"][tfam] for i in cls.a["items"] if i["kind"] in tgt["item_kinds"] and isinstance(i["attributes"].get(tfam), str)})
        cls.fam, cls.own, cls.sec, cls.tfam, cls.sec_vals = fam, own, sec, tfam, sec_vals
        cls.block = {"one": {"attr": fam, "value": own[0]}, "pair": {"attr": fam, "values": own[1:3]},
                     "in_section": {"section": sec["id"], "attr": tfam, "value": sec_vals[0]}}

    def _with(self, block, cid=VALVE):
        configs = copy.deepcopy(self.a["category_configs"])
        for c in configs:
            if c["category_id"] == cid:
                c["list_spec"]["code_targets"] = copy.deepcopy(block)
        return configs

    def test_t1_positive_carried_targets_pass(self):
        self.assertEqual(_refusals(self.a["category_configs"], self.a["items"]), [], "v90 itself (paint_row.family checked) refuses nothing")
        configs = self._with(self.block)
        self.assertEqual(_refusals(configs, self.a["items"]), [])
        by = {c["category_id"]: c for c in configs}
        refs = [r for r in CG.code_target_refs(by[VALVE], by) if r[4] is None]
        self.assertEqual(len(refs), 4)                                   # one + the two of the list + the section's one
        self.assertIs(refs[-1][3], by[self.sec["category_id"]])          # the section's role is checked against ITS category
        config_validation._validate_config(by[VALVE])                    # the shape is accepted
        duct = by[DUCT]
        self.assertEqual([r[:3] for r in CG.code_target_refs(duct, by) if r[4] is None],
                         [("list_spec.pricing.paint_row.family", "item", duct["list_spec"]["pricing"]["paint_row"]["family"])])

    def test_t1_negative_renamed_value_refused_with_the_place(self):
        b = copy.deepcopy(self.block)
        b["one"]["value"] = self.own[0] + " (renamed)"
        r = _refusals(self._with(b), self.a["items"])
        self.assertEqual([(p["config"], p["path"]) for p in r], [(VALVE, "list_spec.code_targets.one.value")])
        self.assertIn("no active SKU carries it", r[0]["message"])
        b = copy.deepcopy(self.block)
        b["pair"]["values"][1] = "x" + b["pair"]["values"][1]
        self.assertEqual([p["path"] for p in _refusals(self._with(b), self.a["items"])], ["list_spec.code_targets.pair.values[1]"])

    def test_t1_negative_deactivated_carrier_refused(self):
        sec_kind = self.by[self.sec["category_id"]]["item_kinds"]
        items = [i for i in self.a["items"] if not (i["kind"] in sec_kind and i["attributes"].get(self.tfam) == self.sec_vals[0])]
        r = _refusals(self._with(self.block), items)
        self.assertIn((VALVE, "list_spec.code_targets.in_section.value"), [(p["config"], p["path"]) for p in r])
        self.assertIn("of %s carries it" % self.sec["category_id"], [p for p in r if p["path"].endswith("in_section.value")][0]["message"])

    def test_t1_negative_strict_attribute_and_section(self):
        b = {"one": {"attr": "no_such_attribute", "value": self.own[0]}}
        self.assertEqual([p["path"] for p in _refusals(self._with(b), self.a["items"])], ["list_spec.code_targets.one.value"])
        b = {"one": {"section": "nowhere", "attr": self.fam, "value": self.own[0]}}
        r = _refusals(self._with(b), self.a["items"])
        self.assertEqual([p["path"] for p in r], ["list_spec.code_targets.one"])
        self.assertIn("no delegated section", r[0]["message"])

    def test_t1_negative_paint_row_family_renamed(self):
        configs = copy.deepcopy(self.a["category_configs"])
        for c in configs:
            if c["category_id"] == DUCT:
                c["list_spec"]["pricing"]["paint_row"]["family"] += " (renamed)"
        self.assertEqual([(p["config"], p["path"]) for p in _refusals(configs, self.a["items"])],
                         [(DUCT, "list_spec.pricing.paint_row.family")])

    def test_shape_refused_by_config_validation(self):
        bad = [{"one": {"attr": self.fam, "value": self.own[0], "values": [self.own[1]]}}, {"one": {"attr": self.fam}},
               {"one": {"attr": self.fam, "values": []}}, {"one": {"attr": self.fam, "values": [self.own[0], self.own[0]]}},
               {"One": {"attr": self.fam, "value": self.own[0]}}, {"one": "x"}, [], {}, {"one": {"attr": self.fam, "value": self.own[0], "x": 1}}]
        for b in bad:
            c = copy.deepcopy(self.by[VALVE])
            c["list_spec"]["code_targets"] = b
            with self.assertRaises(frappe.ValidationError, msg=repr(b)):
                config_validation._validate_config(c)
