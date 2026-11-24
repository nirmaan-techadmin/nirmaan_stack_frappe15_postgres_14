# Copyright (c) 2026, Nirmaan (Stratos Infra Technologies Pvt. Ltd.) and contributors
# For license information, please see license.txt

"""BCS-2b: the generator of the Electrical supply cost calculations (`bcs_derive.py`) and the DRIFT TEST.

What these protect, in plain words:
- the generator's cost calculations, run by the product's own interpreter, give EXACTLY v73's hand-written costs on every worked
  example - with today's inputs and with inputs moved so that every exception has something to do;
- the one general rule and each of the six exception kinds is needed: switched off, a cost moves on at least one example;
- THE DRIFT TEST: the newest committed Electrical rate file's cost calculations are what the generator makes from that file's
  own price calculations - so a future rate file that changes a price step without regenerating its cost fails here.
The interpreter is bundled from the checkout with the esbuild already in `frontend/node_modules` and run by node (as the mints
do); nothing is written outside a temporary folder.
"""
import copy
import glob
import json
import os
import re
import subprocess
import tempfile

from frappe.tests.utils import FrappeTestCase

from nirmaan_stack.services.boq_rate_master import bcs_derive

DATA = os.path.join(os.path.dirname(__file__), "data")
APP = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
FE = os.path.join(APP, "frontend")
V73 = os.path.join(DATA, "rate_master_electrical_all_v73.json")
# inputs moved IN MEMORY so the latent exceptions show (BCS-D1 P1c): lighting's cost-only markup 0 -> 0.10, the cable-tray
# discount 0 -> 0.07 (every tray list price would otherwise land on whole rupees), the junction-box discount 0 -> 0.07
LATENT = {"lms_bcs": {"bcs_markup": 0.1}, "tray_discount": {"discount": 0.07}, "jb_discount": {"discount": 0.07}}

HARNESS = r'''
import { readFileSync } from "node:fs";
import { runPipeline } from "%(fe)s/src/pages/pricing/rate-master/ratePipelineInterpreter";
const spec = JSON.parse(readFileSync(process.argv[2], "utf8"));
const out: any[] = [];
for (const r of spec.runs) {
  const items = spec.items[r.items].map((i: any) => ({ ...i, discipline: "Electrical", attributes: { ...i.attributes, ...(i.brand ? { brand: i.brand } : {}) } }));
  let res: any;
  try { res = runPipeline(r.pid, spec.pipelines[r.pl], items, r.sel); } catch (e: any) { out.push({ status: "error", finals: null }); continue; }
  out.push({ status: res.status, finals: res.finals ?? null });
}
console.log(JSON.stringify(out));
'''


def latest_electrical():
    files = [p for p in glob.glob(os.path.join(DATA, "rate_master_electrical_all_v*.json")) if re.search(r"_v\d+\.json$", p)]
    return max(files, key=lambda p: int(re.search(r"_v(\d+)\.json$", p).group(1)))


def _load(p):
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def _patched_items(asset, patch):
    items = copy.deepcopy(asset["items"])
    for it in items:
        p = patch.get((it.get("attributes") or {}).get("item")) if str(it.get("kind")).endswith("_pricing_input") else None
        if p:
            it["rates"] = dict(it["rates"], **p)
    return items


def run_pipelines(items_sets, pipelines, runs):
    """The product's runPipeline on each run: {items: key of items_sets, pl: key of pipelines, pid, sel}."""
    node = sorted(glob.glob("/home/frappe/.nvm/versions/node/*/bin/node"))[-1]
    with tempfile.TemporaryDirectory(prefix="bcs2b_test_") as d:
        ts, js, spec = os.path.join(d, "h.ts"), os.path.join(d, "h.mjs"), os.path.join(d, "spec.json")
        with open(ts, "w") as fh:
            fh.write(HARNESS % {"fe": FE})
        with open(spec, "w") as fh:
            json.dump({"items": items_sets, "pipelines": pipelines, "runs": runs}, fh)
        env = dict(os.environ, PATH=os.path.dirname(node) + ":" + os.environ.get("PATH", ""))
        r = subprocess.run([os.path.join(FE, "node_modules/.bin/esbuild"), ts, "--bundle", "--platform=node", "--format=esm",
                            "--outfile=" + js, "--log-level=error"], cwd=FE, env=env, capture_output=True, text=True)
        if r.returncode:
            raise AssertionError("esbuild: " + r.stderr)
        r = subprocess.run([node, js, spec], env=env, capture_output=True, text=True)
        if r.returncode:
            raise AssertionError("interpreter: " + r.stderr[-2000:])
    return json.loads(r.stdout)


def compare(asset, generated, patch=None):
    """[(category, cost id, example id)] where `generated` {(cat, cost id): pipeline} does NOT give exactly the stored cost
    of `asset` on a worked example of the category (every output, status alike)."""
    cats = {c["category_id"]: c for c in asset["category_configs"]}
    items = {"i": _patched_items(asset, patch or {})}
    pipelines, runs, keys = {}, [], []
    for (cat, cid), pl in generated.items():
        pipelines["s|" + cid] = cats[cat]["pipelines"][cid]
        pipelines["g|" + cid] = pl
        for g in asset["goldens"].get(cat, cats[cat].get("goldens") or []):
            keys.append((cat, cid, g["id"]))
            runs.append({"items": "i", "pl": "s|" + cid, "pid": cid, "sel": g["attrs"]})
            runs.append({"items": "i", "pl": "g|" + cid, "pid": cid, "sel": g["attrs"]})
    res = run_pipelines(items, pipelines, runs)
    bad = []
    for n, k in enumerate(keys):
        a, b = res[2 * n], res[2 * n + 1]
        outs = cats[k[0]]["pipelines"][k[1]]["output"]
        if a["status"] != b["status"] or any((a["finals"] or {}).get(o) != (b["finals"] or {}).get(o) for o in outs):
            bad.append(k)
    return bad


class TestGeneratedEqualsV73(FrappeTestCase):
    """(+) the generator's output, run by the interpreter, equals v73's stored cost on the worked examples."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.v73 = _load(V73)
        cls.gen = bcs_derive.generate_all(cls.v73)

    def test_01_every_pair_equals_v73_on_every_worked_example(self):
        self.assertEqual(len(self.gen), 13)
        self.assertEqual(compare(self.v73, self.gen), [])

    def test_02_equal_too_with_the_latent_inputs_moved(self):
        self.assertEqual(compare(self.v73, self.gen, LATENT), [])

    def test_03_every_cost_reads_the_same_pricing_inputs_as_v73(self):
        cats = {c["category_id"]: c for c in self.v73["category_configs"]}
        refs = lambda pl: sorted({(s["ref"]["item"], s["target"]) for s in pl["steps"] if s.get("step") == "rate_ref"})
        for (cat, cid), pl in self.gen.items():
            self.assertEqual(refs(pl), refs(cats[cat]["pipelines"][cid]), cid)


class TestEachRuleIsNeeded(FrappeTestCase):
    """(-) the general rule, and each exception kind, switched off -> a different cost on at least one worked example."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.v73 = _load(V73)

    def _differs(self, **kw):
        return compare(self.v73, bcs_derive.generate_all(self.v73, **kw), LATENT)

    def test_01_NEGATIVE_the_general_rule_off_moves_every_category_with_a_markup(self):
        bad = {cid for _, cid, _ in self._differs(general_rule=False)}
        # misc has no supply markup in its price; every other cost moves when a markup is NOT left out
        self.assertEqual(bad, {cid for _, cid in [(p["category"], p["cost"]) for p in bcs_derive.PAIRS]} - {"misc_bcs"})

    def test_02_NEGATIVE_each_exception_kind_is_needed(self):
        expect = {bcs_derive.WASTAGE: {"pw_bcs", "cable_bcs"}, bcs_derive.DROP_ROUNDUP: {"tray_bcs", "jb_bcs", "lms_bcs", "popup_bcs", "cable_bcs"},
                  bcs_derive.ROUNDUP_DIGITS: {"cable_bcs"}, bcs_derive.DROP_STAGE_ROUND: {"indsock_bcs"},
                  bcs_derive.RATIO: {"misc_bcs", "popup_bcs"}, bcs_derive.COST_MARKUP: {"lms_bcs"}}
        for kind, cids in expect.items():
            with self.subTest(kind=kind):
                bad = {cid for _, cid, _ in self._differs(without=(kind,))}
                self.assertTrue(bad, "%s removed changed no cost" % kind)
                self.assertTrue(bad <= cids, (kind, bad))

    def test_03_NEGATIVE_the_negative_control_cable_wastage_dropped(self):
        bad = {cid for _, cid, _ in self._differs(break_="cable_wastage")}
        self.assertEqual(bad, {"pw_bcs", "cable_bcs"})


class TestDrift(FrappeTestCase):
    """THE DRIFT TEST (P3c): the newest committed Electrical file regenerates to itself."""

    def test_01_the_newest_electrical_file_has_no_drift(self):
        asset = _load(latest_electrical())
        self.assertEqual(bcs_derive.drift(asset), [], os.path.basename(latest_electrical()))

    def test_02_NEGATIVE_a_price_step_changed_with_the_cost_left_stale_is_drift(self):
        asset = _load(latest_electrical())
        cat = [c for c in asset["category_configs"] if c["category_id"] == "junction_box_raceway"][0]
        step = [s for s in cat["pipelines"]["jb_boq"]["steps"] if s.get("step") == "match_master_row"][0]
        step["explain"] = "a price step edited after the mint"
        self.assertEqual(bcs_derive.drift(asset), [("junction_box_raceway", "jb_bcs")])
        cat["pipelines"]["jb_boq"]["steps"].insert(1, {"step": "scale", "target": "list_price", "result": "list_price", "params": {"f": 1.1}, "formula": "base*f"})
        self.assertIn(("junction_box_raceway", "jb_bcs"), bcs_derive.drift(asset))

    def test_03_NEGATIVE_a_stored_cost_edited_by_hand_is_drift(self):
        asset = _load(latest_electrical())
        cat = [c for c in asset["category_configs"] if c["category_id"] == "wiring_cabling"][0]
        r = [s for s in cat["pipelines"]["cable_bcs"]["steps"] if s.get("step") == "roundup"][0]
        r["params"] = dict(r["params"], digits=-1)
        self.assertEqual(bcs_derive.drift(asset), [("wiring_cabling", "cable_bcs")])


class TestGeneratorRefuses(FrappeTestCase):
    """(-) the generator refuses a price shape an exception does not fit, and a price sentence left in a cost step."""

    def test_01_NEGATIVE_a_round_up_that_is_not_there(self):
        asset = _load(V73)
        cat = [c for c in asset["category_configs"] if c["category_id"] == "junction_box_raceway"][0]
        cat["pipelines"]["jb_boq"]["steps"] = [s for s in cat["pipelines"]["jb_boq"]["steps"] if not (s.get("step") == "roundup" and s.get("target") == "supply")]
        pair = [p for p in bcs_derive.PAIRS if p["cost"] == "jb_bcs"][0]
        with self.assertRaises(bcs_derive.GenerationError):
            bcs_derive.generate(asset, pair)

    def test_02_NEGATIVE_a_price_sentence_left_in_a_cost_step(self):
        asset = _load(V73)
        cat = [c for c in asset["category_configs"] if c["category_id"] == "earthing"][0]
        step = [s for s in cat["pipelines"]["earthing_boq"]["steps"] if s.get("step") == "match_master_row"][0]
        step["explain"] = "plus the company markup"
        pair = [p for p in bcs_derive.PAIRS if p["cost"] == "earthing_bcs"][0]
        with self.assertRaises(bcs_derive.GenerationError):
            bcs_derive.generate(asset, pair)

    def test_03_the_exceptions_table_uses_only_the_six_kinds(self):
        kinds = {e["kind"] for p in bcs_derive.PAIRS for e in p["exceptions"]}
        self.assertEqual(kinds, set(bcs_derive.EXCEPTION_KINDS))
        self.assertNotIn("tray_bcs_install", {p["cost"] for p in bcs_derive.PAIRS})
