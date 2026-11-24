# Copyright (c) 2026, Nirmaan (Stratos Infra Technologies Pvt. Ltd.) and contributors
# For license information, please see license.txt

"""BCS-2b: Electrical v74 against v73, and the mint's EXACT GUARD.

What these protect, in plain words:
- v74 changes nothing a price is made from: every price calculation, every catalogue item, every Pricing Input, every worked
  example and every other key is byte-equal to v73; only the 13 supply cost calculations were replaced;
- each replaced cost calculation keeps its id and its output names, so every reader finds it as before; the installation cost
  rules (`tray_bcs_install`, and the installation parts of `misc_bcs` and `popup_bcs`) are v73's, byte for byte;
- no generated cost holds a typed number where its price reads a Pricing Input (the only zeros are the left-out markups);
- every cost line reads as a cost: "markup" appears only to say it is left out or replaced, the cable's round-up says units,
  and the miscellaneous line no longer reads "25% markup assumed";
- the mint refuses a file whose generated cost differs from v73's stored cost on any case (the exact guard).
"""
import copy
import importlib.util
import json
import os
import re

from frappe.tests.utils import FrappeTestCase

from nirmaan_stack.services.boq_rate_master import bcs_derive

DATA = os.path.join(os.path.dirname(__file__), "data")
APP = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
V73 = os.path.join(DATA, "rate_master_electrical_all_v73.json")
V74 = os.path.join(DATA, "rate_master_electrical_all_v74.json")
GENERATED = {(p["category"], p["cost"]) for p in bcs_derive.PAIRS}
canon = lambda o: json.dumps(o, sort_keys=True, separators=(",", ":"))


def _load(p):
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def _cats(asset):
    return {c["category_id"]: c for c in asset["category_configs"]}


class TestV74AgainstV73(FrappeTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.v73, cls.v74 = _load(V73), _load(V74)
        cls.c73, cls.c74 = _cats(cls.v73), _cats(cls.v74)

    def test_01_every_item_and_pricing_input_byte_equal(self):
        self.assertEqual([canon(i) for i in self.v73["items"]], [canon(i) for i in self.v74["items"]])

    def test_02_every_key_but_the_categories_byte_equal(self):
        self.assertEqual(list(self.v73), list(self.v74))
        for k in self.v73:
            if k != "category_configs":
                self.assertEqual(canon(self.v73[k]), canon(self.v74[k]), k)

    def test_03_every_price_pipeline_and_every_non_cost_key_byte_equal(self):
        self.assertEqual(list(self.c73), list(self.c74))
        for cat, x in self.c73.items():
            y = self.c74[cat]
            for k in set(x) | set(y):
                if k != "pipelines":
                    self.assertEqual(canon(x.get(k)), canon(y.get(k)), (cat, k))
            self.assertEqual(list(x["pipelines"]), list(y["pipelines"]), cat)
            for pid in x["pipelines"]:
                if (cat, pid) not in GENERATED:
                    self.assertEqual(canon(x["pipelines"][pid]), canon(y["pipelines"][pid]), (cat, pid))

    def test_04_exactly_the_13_supply_costs_were_replaced(self):
        moved = sorted(pid for cat, c in self.c73.items() for pid, pl in c["pipelines"].items() if canon(pl) != canon(self.c74[cat]["pipelines"][pid]))
        self.assertEqual(moved, sorted(cid for _, cid in GENERATED))
        self.assertEqual(len(moved), 13)

    def test_05_every_generated_pipeline_keeps_its_id_and_output_names(self):
        for cat, cid in GENERATED:
            self.assertIn(cid, self.c74[cat]["pipelines"])
            self.assertEqual(self.c74[cat]["pipelines"][cid]["output"], self.c73[cat]["pipelines"][cid]["output"], cid)

    def test_06_installation_rules_byte_equal_to_v73(self):
        self.assertEqual(canon(self.c73["cabletray_raceway"]["pipelines"]["tray_bcs_install"]),
                         canon(self.c74["cabletray_raceway"]["pipelines"]["tray_bcs_install"]))
        for cat, cid in (("miscellaneous", "misc_bcs"), ("popup_boxes", "popup_bcs")):
            old = self.c73[cat]["pipelines"][cid]["steps"]
            new = [canon(s) for s in self.c74[cat]["pipelines"][cid]["steps"]]
            chain = bcs_derive._install_chain(self.c73[cat]["pipelines"][cid], ["bcs_install"])
            self.assertTrue(chain, cid)
            for s in chain:
                self.assertIn(canon(s), new, (cid, s.get("result")))
                self.assertIn(s, old)

    def test_07_NEGATIVE_no_typed_number_where_the_price_reads_an_input(self):
        """every number a generated step carries is one its price (or v73's installation part) carries, or a left-out markup."""
        def numbers(steps):
            out = []
            for s in steps:
                for p in bcs_derive._param_dicts(s):
                    for k, v in p.items():
                        if isinstance(v, (int, float)) and not isinstance(v, bool):
                            out.append((s.get("step"), k, v))
            return sorted(out, key=repr)
        for p in bcs_derive.PAIRS:
            cat = self.c74[p["category"]]
            gen = numbers(cat["pipelines"][p["cost"]]["steps"])
            allowed = numbers(self.c73[p["category"]]["pipelines"][p["price"]]["steps"])
            allowed += numbers(bcs_derive._install_chain(self.c73[p["category"]]["pipelines"][p["cost"]], [o for o in self.c73[p["category"]]["pipelines"][p["cost"]]["output"] if o != p["cost_out"]]))
            zeros = [x for x in gen if x[2] == 0 and x not in allowed]
            rest = [x for x in gen if x not in allowed and x not in zeros]
            # a round-up whose digits the table re-points (the cable: tens -> units) is the one declared change of a number
            rest = [x for x in rest if not (x[0] == "roundup" and x[1] == "digits" and any(e["kind"] == bcs_derive.ROUNDUP_DIGITS and e["digits"] == x[2] for e in p["exceptions"]))]
            self.assertEqual(rest, [], p["cost"])
            # each zero is a markup the general rule left out: its price step read the markup from a Pricing Input
            price_markups = {k[: -len("_from_ctx")] for s in self.c73[p["category"]]["pipelines"][p["price"]]["steps"]
                             for d in bcs_derive._param_dicts(s) for k, v in d.items() if k.endswith("_from_ctx") and "supply_markup" in str(v)}
            for z in zeros:
                self.assertIn(z[1], price_markups, (p["cost"], z))

    def test_08_NEGATIVE_a_typed_discount_would_be_caught(self):
        v = copy.deepcopy(self.v74)
        jb = _cats(v)["junction_box_raceway"]["pipelines"]["jb_bcs"]
        s = [x for x in jb["steps"] if x.get("step") == "scale"][0]
        s["params"].pop("discount_from_ctx")
        s["params"]["discount"] = 0.1
        self.assertIn(("junction_box_raceway", "jb_bcs"), bcs_derive.drift(v))


class TestCostWording(FrappeTestCase):
    LEFT_OUT = re.compile(r"left out|in place of|no markup|does not read|cost-only", re.I)

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.c74 = _cats(_load(V74))
        cls.c73 = _cats(_load(V73))

    def _lines(self, cat, cid):
        chain = {canon(s) for s in bcs_derive._install_chain(self.c73[cat]["pipelines"][cid], [o for o in self.c73[cat]["pipelines"][cid]["output"] if not o.startswith("bcs_supply")])} if len(self.c73[cat]["pipelines"][cid]["output"]) > 1 else set()
        return [(s.get("step"), s.get("explain") or "") for s in self.c74[cat]["pipelines"][cid]["steps"] if canon(s) not in chain]

    def test_01_markup_is_named_only_to_say_it_is_left_out(self):
        for cat, cid in GENERATED:
            for step, line in self._lines(cat, cid):
                if step != "rate_ref" and re.search(r"markup", line, re.I):
                    self.assertRegex(line, self.LEFT_OUT, (cid, line))

    def test_02_the_cable_round_up_says_units(self):
        r = [s for s in self.c74["wiring_cabling"]["pipelines"]["cable_bcs"]["steps"] if s.get("step") == "roundup"]
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["params"]["digits"], 0)
        self.assertIn("units", r[0]["explain"])
        self.assertNotEqual(r[0]["explain"], "round up to tens")

    def test_03_NEGATIVE_misc_no_longer_reads_25_percent_markup_assumed(self):
        lines = " ".join(s.get("explain") or "" for s in self.c74["miscellaneous"]["pipelines"]["misc_bcs"]["steps"])
        self.assertNotIn("25% markup assumed", lines)
        self.assertIn("25% markup assumed", " ".join(s.get("explain") or "" for s in self.c73["miscellaneous"]["pipelines"]["misc_bcs"]["steps"]))
        self.assertIn("Miscellaneous supply BCS ratio", lines)

    def test_04_every_generated_pipeline_says_it_is_worked_out_from_the_price(self):
        for cat, cid in GENERATED:
            self.assertTrue(self.c74[cat]["pipelines"][cid]["note"].startswith(bcs_derive.PLAIN_LINE), cid)

    def test_05_no_figure_typed_into_a_cost_line(self):
        """the live value is the input's: a cost line names the input, never its number (R6)."""
        for cat, cid in GENERATED:
            for step, line in self._lines(cat, cid):
                if step == "rate_ref":
                    continue
                self.assertNotRegex(line, r"\d+\s*%", (cid, line))


def _mint():
    spec = importlib.util.spec_from_file_location("mint74", os.path.join(APP, "scripts", "_instruments", "mint_electrical_v74_bcs2b.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class TestExactGuard(FrappeTestCase):
    """THE EXACT GUARD (P3b) on fixtures: v74 passes; a fixture with one generated step changed is refused."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.mint = _mint()
        cls.v73, cls.v74 = _load(V73), _load(V74)

    def test_01_v74_passes_the_exact_guard(self):
        diffs, n, counts = self.mint.exact_guard(self.v73, self.v74)
        self.assertEqual(diffs, [])
        self.assertGreater(n, 1600)
        self.assertEqual(set(counts), {cid for _, cid in GENERATED})

    def test_02_NEGATIVE_one_generated_step_changed_is_refused(self):
        bad = copy.deepcopy(self.v74)
        cable = _cats(bad)["wiring_cabling"]["pipelines"]["cable_bcs"]
        r = [s for s in cable["steps"] if s.get("step") == "roundup"][0]
        r["params"] = dict(r["params"], digits=-1)      # tens again: the rounding the cost must NOT have
        diffs, _, counts = self.mint.exact_guard(self.v73, bad)
        self.assertTrue(diffs)
        self.assertGreater(counts["cable_bcs"]["differ"], 0)
        self.assertEqual(sum(c["differ"] for k, c in counts.items() if k != "cable_bcs"), 0)

    def test_03_NEGATIVE_a_refusal_lost_is_refused(self):
        bad = copy.deepcopy(self.v74)
        sw = _cats(bad)["switches_sockets"]["pipelines"]["swsock_bcs"]
        [s for s in sw["steps"] if s.get("step") == "sum_components"][0].pop("none_refusal")
        diffs, _, counts = self.mint.exact_guard(self.v73, bad)
        self.assertGreater(counts["swsock_bcs"]["differ"], 0)
