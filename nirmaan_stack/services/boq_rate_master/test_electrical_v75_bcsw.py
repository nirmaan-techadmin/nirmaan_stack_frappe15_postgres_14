# Copyright (c) 2026, Nirmaan (Stratos Infra Technologies Pvt. Ltd.) and contributors
# For license information, please see license.txt

"""BCS-W: Electrical v75 = v74 with ONLY texts changed (owner R1 / R2 24 Nov 13:09 - 13:12; the approved mockup board 1 / 2;
Question 1 answers 1a / 2a, 2026-11-25 00:20).

What these protect, in plain words:
- v75 differs from v74 in text fields only - every item, rate, calculation step (but its explanation line), Pricing Input
  figure, config key and worked example is byte-equal; a file with one figure changed is refused;
- the generated cost calculations of v75 are what bcs_derive.py makes from v75's own price calculations (the drift test on
  v75), and no cost line on the FORMULA row repeats its price line before its own part;
- no Electrical text a pricer reads on the FORMULA row or the Pricing Inputs page carries an internal label (main's label
  kinds AND the Electrical list beside them); a line with "ruling (iv)" or "none_skips" is caught;
- no Electrical remark carries a worked rupee figure or a percentage typed in: each is a template the screen works out from
  the row's current values (the example item's own list price may stay written - it is the sum's starting figure).
Pure file reads: no database, nothing written.
"""
import copy
import importlib.util
import json
import os
import re

from frappe.tests.utils import FrappeTestCase

from nirmaan_stack.services.boq_rate_master import bcs_derive

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "data")
APP = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
V74 = os.path.join(DATA, "rate_master_electrical_all_v74.json")
V75 = os.path.join(DATA, "rate_master_electrical_all_v75.json")
PI_KIND = bcs_derive.PI_KIND


def _load(p):
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def _module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


MINT = _module("bcsw_mint_v75", os.path.join(APP, "scripts", "_instruments", "mint_electrical_v75_bcsw.py"))
PRICER_TEXTS = _module("bcsw_pricer_texts", os.path.join(APP, "scripts", "pricer_texts.py"))
with open(os.path.join(APP, "scripts", "electrical_text_labels.json"), encoding="utf-8") as _fh:
    ELEC_KINDS = [(k["id"], re.compile(k["re"])) for k in json.load(_fh)["kinds"]]
MARK = re.compile(r"\{(%[a-z_]+|rs10:[^}]+|rs2:[^}]+|rs:[^}]+|bcs)\}")


def labels(text):
    """main's label kinds (pricer_texts.labels, unchanged) + the Electrical list (answer 2a)."""
    return PRICER_TEXTS.labels(text) + ["%s:%s" % (k, m.group(0)) for k, rx in ELEC_KINDS for m in rx.finditer(text)]


def formula_lines(asset):
    """Every (category, rate column, side, line) the FORMULA row shows from the rate file: a step's own line, a band's own
    line, for a step that targets a catalogue column; side = cost for a *_bcs pipeline. (The stock phrases the screen adds for
    a step with no line of its own are in code, not here.)"""
    cols = {}
    for it in asset["items"]:
        cols.setdefault(it["kind"], set()).update(k for k, v in (it.get("rates") or {}).items() if v is not None)
    out = []
    for c in asset["category_configs"]:
        kinds = c.get("item_kinds") or (["cable", "termination"] if c["category_id"] == "wiring_cabling" else [])
        keys = set().union(*[cols.get(k if isinstance(k, str) else k.get("kind"), set()) for k in kinds]) if kinds else set()
        for pid, p in (c.get("pipelines") or {}).items():
            side = "cost" if "bcs" in pid.lower() else "price"
            for s in p.get("steps") or []:
                if s.get("target") in keys and s.get("explain"):
                    out.append((c["category_id"], s["target"], side, pid, s["explain"]))
                for b in s.get("bands") or []:
                    if b.get("target") in keys and (b.get("explain") or s.get("explain")):
                        out.append((c["category_id"], b["target"], side, pid, (s.get("explain") if side == "cost" else None) or b.get("explain") or s.get("explain")))
    return out


def repeats(asset):
    """[(category, column, cost line)] where a cost line repeats a price line of the same cell before its own part."""
    norm = lambda t: re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()
    lines = formula_lines(asset)
    price = {}
    for cat, col, side, _pid, t in lines:
        if side == "price":
            price.setdefault((cat, col), set()).add(norm(t))
    return [(cat, col, t) for cat, col, side, _pid, t in lines
            if side == "cost" and norm(t) not in price.get((cat, col), set())
            and any(len(p) > 12 and p in norm(t) for p in price.get((cat, col), set()))]


def remark_problems(text):
    """A fixed figure in a remark: a percentage typed in, or a rupee figure that is not the starting figure of one of the
    remark's own sums (the example's list price stays written; every worked figure is a mark)."""
    sums = " ".join(m.group(1) for m in MARK.finditer(text))
    starters = set(re.findall(r"\d+(?:\.\d+)?", sums))
    plain = MARK.sub(" ", text)
    out = ["percent:" + m.group(0) for m in re.finditer(r"(?<![\w.])\d+(?:\.\d+)?%", plain)]
    for m in re.finditer(r"\bRs\.?\s?(\d[\d,]*(?:\.\d+)?)", plain):
        fig = m.group(1).replace(",", "")
        if fig not in starters and str(float(fig)).rstrip("0").rstrip(".") not in {s.rstrip("0").rstrip(".") if "." in s else s for s in starters}:
            out.append("rupee:" + m.group(0))
    return out


class TestV75TextOnly(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.v74, cls.v75 = _load(V74), _load(V75)

    def test_01_v75_is_v74_apart_from_text_fields(self):
        rows, ok = MINT.text_only(self.v74, self.v75)
        self.assertTrue(ok, "v75 differs from v74 in something other than a text field")
        self.assertEqual(sorted({r[0] for r in rows}), ["band", "remark", "step"])
        self.assertEqual(len(self.v75["items"]), len(self.v74["items"]))

    def test_02_NEGATIVE_one_figure_changed_is_refused(self):
        bad = copy.deepcopy(self.v75)
        pi = next(i for i in bad["items"] if i["kind"] == PI_KIND and i["attributes"]["item"] == "cable_arm")
        pi["rates"]["discount"] = 0.74
        self.assertFalse(MINT.text_only(self.v74, bad)[1])
        bad2 = copy.deepcopy(self.v75)
        st = bad2["category_configs"][0]["pipelines"]["tray_boq_supply"]["steps"]
        st[-1] = dict(st[-1], target="supply_markup_x")
        self.assertFalse(MINT.text_only(self.v74, bad2)[1])

    def test_03_the_edits_file_rebuilds_v75(self):
        rebuilt = bcs_derive.apply(MINT.apply_edits(self.v74), stored=MINT.apply_edits(self.v74))
        self.assertEqual(json.dumps(rebuilt, sort_keys=True), json.dumps(self.v75, sort_keys=True))

    def test_04_NEGATIVE_an_edit_whose_old_text_is_not_v74s_is_refused(self):
        e = MINT.edits()
        e["price_steps"][0] = dict(e["price_steps"][0], old="not the line v74 carries")
        with self.assertRaises(SystemExit):
            MINT.apply_edits(self.v74, e)


class TestV75CostLines(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.v75 = _load(V75)

    def test_01_drift_test_holds_on_v75(self):
        self.assertEqual(bcs_derive.drift(self.v75), [])

    def test_02_no_cost_line_repeats_its_price_line(self):
        self.assertEqual(repeats(self.v75), [])

    def test_03_NEGATIVE_a_cost_line_that_repeats_its_price_line_fails(self):
        bad = copy.deepcopy(self.v75)
        cfg = next(c for c in bad["category_configs"] if c["category_id"] == "popup_boxes")
        price = next(s for s in cfg["pipelines"]["popup_boq"]["steps"] if s.get("target") == "supply_per_module")["explain"]
        cost = next(s for s in cfg["pipelines"]["popup_bcs"]["steps"] if s.get("target") == "supply_per_module")
        cost["explain"] = price.rstrip(".") + "; our cost takes our share of the quote"
        self.assertEqual([(c, k) for c, k, _t in repeats(bad)], [("popup_boxes", "supply_per_module")])

    def test_04_the_v74_repeat_is_found_the_same_way(self):
        """the check is real: v74's pop-up cost line repeated its price line word for word (BCS-S1)."""
        self.assertIn(("popup_boxes", "supply_per_module"), [(c, k) for c, k, _t in repeats(_load(V74))])


class TestV75Labels(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.v75 = _load(V75)

    def test_01_no_internal_label_on_a_formula_line_or_a_remark(self):
        found = [(c, k, labels(t)) for c, k, _s, _p, t in formula_lines(self.v75) if labels(t)]
        for it in self.v75["items"]:
            if it["kind"] == PI_KIND:
                for leaf in ("name", "remarks"):
                    t = MARK.sub(" ", str(it["attributes"].get(leaf) or ""))
                    if labels(t):
                        found.append(("pricing_inputs", it["attributes"]["item"], labels(t)))
        self.assertEqual(found, [])

    def test_02_NEGATIVE_the_labels_board_1_names_are_caught(self):
        for t in ("ruling (iv) conduit prices as its own category does", "none_skips (type None) and qty 0",
                  "paired MCB added x1 UNLESS", "clearing None (owner, 2026-10-27, \"2 v1\")", "the wire install, ruling (a) 2026-08-10",
                  "*** THIS IS THE INVERSE OF THE ORIGINAL DESIGN", "used when thickness_sqmm <35"):
            self.assertTrue(labels(t), t)

    def test_03_the_v74_labels_are_found(self):
        v74_lines = [t for _c, _k, _s, _p, t in formula_lines(_load(V74)) if labels(t)]
        self.assertTrue(any("ruling (iv)" in t for t in v74_lines))


class TestV75LiveRemarks(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.pis = [i for i in _load(V75)["items"] if i["kind"] == PI_KIND]

    def test_01_no_remark_carries_a_fixed_figure(self):
        self.assertEqual([(i["attributes"]["item"], remark_problems(i["attributes"]["remarks"])) for i in self.pis
                          if remark_problems(i["attributes"]["remarks"])], [])

    def test_02_every_rupee_example_is_a_template_over_its_own_columns(self):
        tpl = [i for i in self.pis if MARK.search(i["attributes"]["remarks"])]
        self.assertGreaterEqual(sum(1 for i in tpl if re.search(r"\{rs\d*:", i["attributes"]["remarks"])), 33)
        for i in tpl:
            for m in MARK.finditer(i["attributes"]["remarks"]):
                names = set(re.findall(r"[a-z_]+", m.group(1).split(":", 1)[-1].lstrip("%"))) - {"rs", "rs2", "rs10", "bcs"}
                self.assertTrue(names <= set(k for k, v in i["rates"].items() if v is not None), (i["attributes"]["item"], m.group(0)))

    def test_03_NEGATIVE_a_remark_with_a_fixed_rupee_figure_fails(self):
        self.assertTrue(remark_problems("A 4-core cable lists at Rs 1,217/m and is quoted at Rs 411/m."))
        self.assertTrue(remark_problems("We buy cable at 75% off list."))
        self.assertEqual(remark_problems("A cable listed at Rs 1,217/m is quoted at Rs {rs:1217*(1-discount)}/m."), [])
