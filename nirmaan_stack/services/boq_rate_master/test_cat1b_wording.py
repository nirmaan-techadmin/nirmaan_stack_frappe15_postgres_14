"""CAT-1b (2026-11-26) -- HVAC v90: the HVAC wording names catalogue values through {{cat:...}} placeholders, and every reader fills them
identically (owner 2026-11-26 01:47 "a a a ok", QR-C-1 (a): "CAT-1b adds the TypeScript fill for the test readers (one parity test: TS fill
= Python fill on the asset) and converts the 533"; 11:15 "a", QR-C-2 (a): the prose texts converted, the 15 whole-value texts kept typed).

  T1  PARITY   the fixture __fixtures__/catalogueFillParity.json IS the Python fill: every placeholder form on a made-up catalogue (output
               + problems) and every placeholder text of v90 (sha256 of its filled text) re-derived here must equal it. The TypeScript
               fill is held to the SAME fixture by catalogueFill.parity.test.ts -- so TS fill == Python fill, byte for byte.
               A missing value / uid RAISES in the test readers' fill (fill_asset_for_tests), naming the place.
  T2  v90      = v89 + cat1bEdits.json exactly; each converted text fills back byte-equal to v89's; a planted undeclared change is
               not v90; the undo link (as_v89) gives v89's configs back and refuses a partial.
  T3  NO "{{"  in any SERVED config of v90 (the one merge), any request built from v90 through the merge, the test readers' output.
  T4  GATE     v90 = 0 refusals; a placeholder naming a removed value / a deactivated item is REFUSED with its place named (scratch).
  T5  G-PROSE  v90's typed mentions = the lowered allow-list (none up vs v89); a new typed mention in v90's wording is RED.
Pure (no database write); the live checks read only. Run: bench --site localhost run-tests --module
nirmaan_stack.services.boq_rate_master.test_cat1b_wording
"""
import copy
import hashlib
import json
import os

from frappe.tests.utils import FrappeTestCase

from nirmaan_stack.services.boq_rate_master import catalogue_gate, catalogue_lists, cat1b_fill_support, cat1b_undo_support, extraction

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
APP = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
FIX = os.path.join(APP, "frontend", "src", "pages", "boq-wizard", "rate-helper", "__fixtures__")
V89, V90 = "rate_master_hvac_all_v89.json", "rate_master_hvac_all_v90.json"


def _load(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        return json.load(f)


def _canon(o):
    return json.dumps(o, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _sha(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _strings(node, path=""):
    if isinstance(node, str):
        yield path, node
    elif isinstance(node, dict):
        for k, v in node.items():
            yield from _strings(v, f"{path}.{k}" if path else k)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _strings(v, f"{path}[{i}]")


class TestCat1bWording(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.v89, cls.v90 = _load(V89), _load(V90)
        with open(os.path.join(FIX, "catalogueFillParity.json"), encoding="utf-8") as f:
            cls.fx = json.load(f)
        with open(os.path.join(FIX, "cat1bEdits.json"), encoding="utf-8") as f:
            cls.edits = json.load(f)
        cls.stored90 = [dict(c, discipline="HVAC") for c in cls.v90["category_configs"]]
        cls.built90 = catalogue_lists.build([dict(i, active=1) for i in cls.v90["items"]], cls.stored90)

    # ── T1 parity ────────────────────────────────────────────────────────────────────────────────────────────────────
    def test_t1_01_every_placeholder_form_equals_the_fixture(self):
        built = catalogue_lists.build(self.fx["forms"]["items"], [])
        self.assertGreaterEqual(len(self.fx["forms"]["cases"]), 30)
        for c in self.fx["forms"]["cases"]:
            probs = []
            self.assertEqual(catalogue_lists.fill_text(c["s"], built, probs, "case"), c["out"], c["s"])
            self.assertEqual([p[1] for p in probs], c["problems"], c["s"])
        # the forms cover the refusals too: a missing value, a missing / inactive item, four malformed shapes
        self.assertGreaterEqual(sum(1 for c in self.fx["forms"]["cases"] if c["problems"]), 10)

    def test_t1_02_every_v90_placeholder_text_equals_the_fixture(self):
        self.assertEqual(self.fx["asset"]["file"], V90)
        got = []
        for c in self.v90["category_configs"]:
            for path, s in _strings(c):
                if catalogue_lists.PLACEHOLDER_RE.search(s):
                    probs = []
                    got.append({"c": c["category_id"], "where": path, "sha256": _sha(catalogue_lists.fill_text(s, self.built90, probs, path))})
                    self.assertEqual(probs, [], path)
        self.assertEqual(len(got), self.fx["asset"]["count"])
        self.assertEqual(got, self.fx["asset"]["texts"])

    def test_t1_03_the_test_readers_fill_raises_on_a_missing_value_or_item(self):
        a = copy.deepcopy(self.v90)
        cfg = next(c for c in a["category_configs"] if c["category_id"] == "hvac_valve_package")
        cfg["notes"] = "{{cat:valve_type=No Such Valve}} and {{item:rmi-no-such-item}}"
        with self.assertRaises(AssertionError) as cm:
            cat1b_fill_support.fill_asset_for_tests(a)
        self.assertIn("hvac_valve_package.notes", str(cm.exception))
        self.assertIn("2 placeholder(s)", str(cm.exception))
        # positive: v90 fills with no problem and no brace; a file without a placeholder comes back as the same object
        filled = cat1b_fill_support.fill_asset_for_tests(self.v90)
        self.assertNotIn("{{", _canon(filled["category_configs"]))
        self.assertIs(cat1b_fill_support.fill_asset_for_tests(self.v89), self.v89)

    # ── T2 v90 = v89 + the edits ─────────────────────────────────────────────────────────────────────────────────────
    def test_t2_01_v90_is_v89_plus_the_edits_and_fills_back_to_v89(self):
        self.assertEqual(_canon(self.v90["items"]), _canon(self.v89["items"]))
        self.assertEqual(self.edits["pricing_inputs"], {})
        filled = cat1b_fill_support.fill_asset_for_tests(self.v90)
        for a, b in zip(self.v89["category_configs"], filled["category_configs"]):
            self.assertEqual(_canon(a), _canon(b), a["category_id"])
        # every edit's own text fills back to its `from`
        cfg = {c["category_id"]: c for c in self.v90["category_configs"]}
        for e in self.edits["configs"]:
            node = cfg[e["c"]]
            for p in e["p"]:
                node = node[p]
            self.assertEqual(node, e["to"])
            self.assertEqual(catalogue_lists.fill_text(node, self.built90), e["from"], (e["c"], e["p"]))
        self.assertEqual((len(self.edits["configs"]), sum(e["n"] for e in self.edits["configs"])),
                         (self.edits["counts"]["texts"], self.edits["counts"]["placeholders"]))

    def test_t2_02_the_undo_link_gives_v89_back_and_refuses_a_partial_or_planted_change(self):
        for a, b in zip(self.v89["category_configs"], self.v90["category_configs"]):
            self.assertEqual(_canon(cat1b_undo_support.as_v89(copy.deepcopy(b))), _canon(a), a["category_id"])
            self.assertEqual(_canon(cat1b_undo_support.as_v89(copy.deepcopy(a))), _canon(a), a["category_id"])  # v89 comes back as it is
        e = self.edits["configs"][0]
        part = copy.deepcopy(next(c for c in self.v90["category_configs"] if c["category_id"] == e["c"]))
        node = part
        for p in e["p"][:-1]:
            node = node[p]
        node[e["p"][-1]] = e["from"] + " (planted)"       # one text neither v89's nor v90's
        with self.assertRaises(AssertionError):
            cat1b_undo_support.as_v89(part)
        # a planted change elsewhere is not v90: undo + fill no longer equal v89
        planted = copy.deepcopy(self.v90)
        planted["category_configs"][0]["notes"] = (planted["category_configs"][0].get("notes") or "") + " planted"
        back = cat1b_fill_support.fill_asset_for_tests(planted)
        self.assertNotEqual(_canon(back["category_configs"][0]), _canon(self.v89["category_configs"][0]))

    def test_t2_03_the_15_whole_value_texts_stay_typed(self):
        kept = self.edits["counts"]["kept_whole_value"]
        self.assertEqual(len(kept), 15)
        edited = {(e["c"],) for e in self.edits["configs"]}
        self.assertTrue(edited)
        flat = {c["category_id"] + "." + p: s for c in self.v90["category_configs"] for p, s in _strings(c)}
        for w in kept:
            self.assertIn(w, flat, w)
            self.assertNotIn("{{", flat[w], w)

    # ── T3 no braces anywhere a reader looks ─────────────────────────────────────────────────────────────────────────
    def test_t3_01_served_configs_and_requests_carry_no_braces(self):
        merged = {c["category_id"]: catalogue_lists.merge_config(c, self.built90, "HVAC") for c in self.stored90}
        for cid, m in merged.items():
            self.assertNotIn("{{cat:", _canon(m), cid)
            self.assertNotIn("{{item:", _canon(m), cid)
        cfgs = {("HVAC", cid): m for cid, m in merged.items()}
        n = 0
        for c in self.stored90:
            if not extraction.config_is_eligible(c, cfgs):
                continue
            ctx = extraction._group_context(cfgs, "HVAC", c["category_id"])
            t = extraction.batch_prompt_content(ctx["prompt"], ctx["defs"], [], synonyms=ctx["synonyms"], defaults=ctx["defaults"],
                                                none_guidance=ctx["none_guidance"], slot_spec=ctx["slot_spec"],
                                                resolution_rules=ctx["resolution_rules"], rules=ctx["rules"], items_spec=ctx["items_spec"])
            self.assertNotIn("{{cat:", t, c["category_id"])
            n += 1
        self.assertGreaterEqual(n, 7)

    def test_t3_02_the_raw_v90_file_does_carry_placeholders(self):
        # negative half: the test above would pass vacuously on a file with no placeholders
        raw = _canon(self.v90["category_configs"])
        self.assertEqual(raw.count("{{cat:"), self.edits["counts"]["placeholders"])

    # ── T4 the gate ──────────────────────────────────────────────────────────────────────────────────────────────────
    def test_t4_01_gate_green_on_v90_and_refuses_a_renamed_value_or_a_deactivated_item(self):
        self.assertEqual([p for p in catalogue_gate.reference_problems(self.stored90, self.v90["items"], "HVAC") if p["severity"] == "REFUSE"], [])
        e = next(x for x in self.edits["configs"] if "{{cat:nrv_type=Dual Plate" in x["to"])
        items = copy.deepcopy(self.v90["items"])
        for it in items:
            if (it.get("attributes") or {}).get("nrv_type") == "Dual Plate":
                it["attributes"]["nrv_type"] = "Dual-Plate"     # a value renamed in the catalogue (scratch)
        refused = [p for p in catalogue_gate.reference_problems(self.stored90, items, "HVAC") if p["severity"] == "REFUSE"]
        self.assertTrue(any(p["config"] == e["c"] and "Dual Plate" in p["message"] for p in refused), refused[:3])
        # a deactivated item named by {{item:<uid>}} (scratch wording) is refused with its place
        uid = self.v90["items"][0]["item_uid"]
        stored = copy.deepcopy(self.stored90)
        stored[0]["notes"] = "priced as {{item:%s}}" % uid
        items2 = [dict(i, active=0) if i["item_uid"] == uid else i for i in self.v90["items"]]
        refused2 = [p for p in catalogue_gate.reference_problems(stored, items2, "HVAC") if p["severity"] == "REFUSE"]
        self.assertTrue(any(uid in p["message"] and p["config"] == stored[0]["category_id"] for p in refused2), refused2[:3])

    # ── T5 G-PROSE ───────────────────────────────────────────────────────────────────────────────────────────────────
    def test_t5_01_prose_counts_went_down_and_a_new_typed_mention_is_red(self):
        stored89 = [dict(c, discipline="HVAC") for c in self.v89["category_configs"]]
        p89 = catalogue_gate.prose_mentions(stored89, self.v89["items"])
        p90 = catalogue_gate.prose_mentions(self.stored90, self.v90["items"])
        self.assertEqual([(k, v) for k, d in p90.items() for v, n in d.items() if n > (p89.get(k) or {}).get(v, 0)], [])
        self.assertLess(sum(sum(d.values()) for d in p90.values()), sum(sum(d.values()) for d in p89.values()))
        with open(os.path.join(HERE, catalogue_gate.PROSE_ALLOWLIST), encoding="utf-8") as f:
            frozen = {k: v for k, v in json.load(f)["paths"].items() if k.startswith("hvac_")}
        self.assertEqual(catalogue_gate.prose_drift(p90, frozen), [])
        # a new typed mention in v90's wording is red
        stored = copy.deepcopy(self.stored90)
        val = sorted(v for d in p89.values() for v in d)[0]
        stored[0]["notes"] = (stored[0].get("notes") or "") + " also a " + val + " here"
        drift = catalogue_gate.prose_drift(catalogue_gate.prose_mentions(stored, self.v90["items"]), frozen)
        self.assertTrue(any("new mention" in x for x in drift), drift)
