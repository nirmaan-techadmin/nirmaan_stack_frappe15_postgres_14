"""CAT-3 (2026-11-27) -- CATALOGUE LABELS made from each row's own values (owner 2026-11-26 00:11, R1; 00:53, R2; 01:16, R3).
Every check has a NEGATIVE. Nothing here writes to the database: every route is exercised at its read point or on an in-memory
payload, and a refused load refuses before its first write.

  T1+ LABEL = CODE LIST: for every label value, the catalogue values the rule labels on the LIVE catalogue equal, byte for byte,
      the literals today's code typed for that concept at 170abd4d7 (pinned below by file and line; the CAT-3 PF3 workbook reads
      them from `git show 170abd4d7:<file>` side by side), and the SKU counts agree. 0 rows flagged on the live catalogue.
  T1+ A NEW SKU by each route gets its labels with no input: the served read (Rate Master add / edit, CSV upload, Desk all land
      there), the exporter (rate-file mint) and the loader's check (rate-file load) all label from the row's own values.
  T1- An unknown spelling (a conductor the rule does not know, pole "3P+N") is SAVED AND PRICED AS BEFORE (its attributes and
      rates untouched) and FLAGGED (label_flags), never refused; a hand-edited label in a rate file is REFUSED at load (G-LABEL);
      code naming a label value no rule makes is RED (the scan), and `lv` refuses it at run time.
  T2  The moved readers: the poles ladder reads the label (a dormant 3+N SKU is found by rung 1; an unknown spelling is never a
      candidate); the corroborator agrees through the label exactly where the typed values agreed.
  T3b The served config's last step adds no cost key back (BCS reply (i)): a config with BCS cost keys, through a STUB
      withholding step and then `_serve_category_config`, carries none; the item helper adds only `labels` / `label_flags`.
  B4  THE PROMPT-WORD GUARD (owner 00:22): COPPER / ALUMINIUM / ARMOURED / UNARMOURED, the words the attribute prompt teaches,
      must each stay a catalogue value of `wiring_cabling`'s SKUs; RED on a scratch catalogue without one.
  FIX The vitest fixture (`__fixtures__/catalogueLabels.json`) equals the rule over the newest rate files, and its label values
      equal `catalogueLabels.ts`' LABEL_VALUES and the rule's own list.
Run: bench --site localhost run-tests --module nirmaan_stack.services.boq_rate_master.test_catalogue_labels
"""
import copy
import glob
import json
import os
import re

import frappe
from frappe.tests.utils import FrappeTestCase

from nirmaan_stack.services.boq_rate_master import catalogue_labels as CL
from nirmaan_stack.services.boq_rate_master import exporter, extraction, loader

HERE = os.path.dirname(os.path.abspath(CL.__file__))
APP = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
DATA = os.path.join(HERE, "data")
FIXTURE = os.path.join(APP, "frontend", "src", "pages", "boq-wizard", "rate-helper", "__fixtures__", "catalogueLabels.json")
TS_LABELS = os.path.join(APP, "frontend", "src", "pages", "boq-wizard", "rate-helper", "catalogueLabels.ts")
PROMPT = os.path.join(APP, "nirmaan_stack", "services", "boq_category", "prompts", "boq_rate_attr_extraction_prompt.md")

# THE CODE LISTS each label replaces, as typed at 170abd4d7 (file:line), PINNED: the literals in those lines ARE the list.
CODE_LISTS_AT_170abd4d7 = {
    # itemListPricing.ts:1567-1568 (readCableKindWords) + extraction.py:3562-3563 (_MATERIAL_RE)
    ("conductor", "al"): {"ALUMINIUM"},
    ("conductor", "cu"): {"COPPER"},
    # itemListPricing.ts:1564-1565 + extraction.py:3566-3567 (_INSULATION_RE) + itemListRuleOrder.ts:2171
    ("armour", "unarmoured"): {"UNARMOURED"},
    ("armour", "armoured"): {"ARMOURED"},
    # extraction.py:2621 / :2623 (pole_plus_neutral_families: stated / counted / named pole)
    ("poles", "1"): {"SP"}, ("poles", "2"): {"DP"}, ("poles", "3"): {"TP"}, ("poles", "4"): {"FP"},
    # itemListPricing.ts:4730 (CLOTH_CLADDING) and :4731 (CLOTH_ON_ALUMINIUM's values)
    ("cloth_cladding", "cloth"): {"Glass Cloth with paint"},
    ("cloth_cladding", "cloth_on_aluminium"): {"24G Aluminium with Glass Cloth", "26G Aluminium with Glass Cloth"},
}
# itemListPricing.ts:4731 -- CLOTH_ON_ALUMINIUM {gauge: value}
CLOTH_ON_ALUMINIUM_AT_170abd4d7 = {"24": "24G Aluminium with Glass Cloth", "26": "26G Aluminium with Glass Cloth"}
# the dormant named poles (extraction.py:2621 / :2623 named_pole): carried by no SKU today
DORMANT_AT_170abd4d7 = {("poles", "3+N"): "TPN", ("poles", "1+N"): "SPN"}
PROMPT_WORDS = ("COPPER", "ALUMINIUM", "ARMOURED", "UNARMOURED")


def _served(discipline):
    from nirmaan_stack.api.boq import rate_master
    return rate_master.get_rate_master_items(discipline=discipline)["items"]


def _newest(pat):
    files = sorted(glob.glob(os.path.join(DATA, pat)), key=lambda p: int(re.search(r"_v(\d+)", p).group(1)))
    with open(files[-1], encoding="utf-8") as fh:
        return json.load(fh)


class TestLabelEqualsCodeList(FrappeTestCase):
    """T1+ : the rule reproduces every code list on the LIVE catalogue (served items), byte for byte."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.items = _served("Electrical") + _served("HVAC")

    def test_every_label_value_labels_exactly_the_code_list(self):
        got, counts = {}, {}
        for it in self.items:
            for lid, lv in (it.get("labels") or {}).items():
                if lid == "cladding_gauge":
                    continue
                got.setdefault((lid, lv), set()).add(it["attributes"][CL.rule(lid)["from_attr"]])
                counts[(lid, lv)] = counts.get((lid, lv), 0) + 1
        for key, code in CODE_LISTS_AT_170abd4d7.items():
            self.assertEqual(got.get(key, set()), code, key)
            # the SKU set: every live row carrying a code-list value of this label's attribute and scope carries the label
            r = CL.rule(key[0])
            carriers = [it for it in self.items if it["kind"] in r["scope_kinds"] and it["attributes"].get(r["from_attr"]) in code]
            self.assertEqual(counts.get(key, 0), len(carriers), key)
            self.assertTrue(carriers, key)
        # nothing else is labelled with a fixed value (no label value the code lists did not have, apart from the dormant ones)
        self.assertEqual(set(got) - set(CODE_LISTS_AT_170abd4d7), set())

    def test_cloth_on_aluminium_gauge_map_equals_the_code_map(self):
        m = {}
        for it in self.items:
            lab = it.get("labels") or {}
            if lab.get("cloth_cladding") == "cloth_on_aluminium":
                m.setdefault(lab.get("cladding_gauge"), set()).add(it["attributes"]["cladding"])
        self.assertEqual({g: sorted(v) for g, v in m.items()}, {g: [v] for g, v in CLOTH_ON_ALUMINIUM_AT_170abd4d7.items()})

    def test_dormant_named_poles_are_labelled_and_carried_by_no_row(self):
        for key, spelling in DORMANT_AT_170abd4d7.items():
            self.assertEqual(CL.label_of_value("poles", spelling), key[1])
            self.assertFalse([it for it in self.items if (it.get("labels") or {}).get("poles") == key[1]], key)

    def test_no_live_row_is_flagged(self):
        flagged = [(it["item_uid"], it["label_flags"]) for it in self.items if it.get("label_flags")]
        self.assertEqual(flagged, [])

    def test_every_served_item_carries_labels_and_flags_keys(self):
        self.assertTrue(all("labels" in it and "label_flags" in it for it in self.items))


class TestNewSkuGetsLabels(FrappeTestCase):
    """T1+ / T1- : a new SKU is labelled by the rule with no input, by every route; an unknown spelling is flagged, never refused."""

    def _cable(self, material, insulation):
        live = next(it for it in _served("Electrical") if it["kind"] == "cable")
        it = copy.deepcopy(live)
        it.update({"item_uid": "rmi-cat3-scratch", "name": "cat3-scratch"})
        it["attributes"] = dict(it["attributes"], material=material, insulation=insulation, core=3.5, thickness_sqmm=400)
        it.pop("labels", None), it.pop("label_flags", None)
        return it

    def test_served_read_labels_a_new_cable_size(self):
        from nirmaan_stack.api.boq import rate_master
        it = self._cable("ALUMINIUM", "ARMOURED")
        rate_master._serve_items([it])
        self.assertEqual(it["labels"], {"conductor": "al", "armour": "armoured"})
        self.assertEqual(it["label_flags"], [])

    def test_a_new_cloth_gauge_and_a_new_pole_spelling_by_the_rule(self):
        self.assertEqual(CL.labels_for("hvac_insulation_item", {"cladding": "22G Aluminium with Glass Cloth"})[0],
                         {"cloth_cladding": "cloth_on_aluminium", "cladding_gauge": "22"})
        self.assertEqual(CL.labels_for("db_switchgear_item", {"pole": "TPN"}), ({"poles": "3+N"}, []))

    def test_exporter_emits_the_rule_labels(self):
        row = {"kind": "cable", "brand": None, "unit": "Mtr", "attributes": json.dumps({"material": "COPPER", "insulation": "UNARMOURED"}),
               "rates": "{}", "source_sheet": "s", "source_row": 1, "item_uid": "rmi-cat3-scratch"}
        self.assertEqual(exporter._item_payload(row)["labels"], {"conductor": "cu", "armour": "unarmoured"})

    def test_loader_accepts_a_new_sku_whose_labels_the_rule_made(self):
        it = self._cable("ALUMINIUM", "ARMOURED")
        it.update({"source": {"sheet": "s", "row": 1}, "labels": CL.labels_for("cable", it["attributes"])[0]})
        loader._validate_items([it])   # no refusal

    def test_unknown_spellings_are_saved_priced_as_before_and_flagged(self):
        from nirmaan_stack.api.boq import rate_master
        it = self._cable("COPPER CLAD ALUMINIUM", "ARMOURED")
        before = copy.deepcopy({k: it[k] for k in ("attributes", "rates", "kind", "brand", "unit")})
        rate_master._serve_items([it])
        self.assertEqual(it["labels"], {"armour": "armoured"})
        self.assertEqual([f["label"] for f in it["label_flags"]], ["conductor"])
        self.assertEqual({k: it[k] for k in before}, before)   # nothing the matcher or a price reads moved
        sw = {"kind": "db_switchgear_item", "attributes": {"device": "MCB", "pole": "3P+N", "amp_a": 32, "curve": "C"}}
        rate_master._serve_items([sw])
        self.assertEqual(sw["labels"], {})
        self.assertEqual(sw["label_flags"][0]["label"], "poles")
        # ... and the loader never refuses it for that (a flag is not a refusal)
        sw.update({"rates": {}, "source": {"sheet": "s", "row": 1}, "labels": {}})
        loader._validate_items([sw])

    def test_a_partial_label_with_no_case_is_no_label_and_no_flag(self):
        self.assertEqual(CL.labels_for("hvac_insulation_item", {"cladding": "Aluminium Foil"}), ({}, []))

    def test_a_hand_edited_label_is_refused_at_load(self):
        it = self._cable("ALUMINIUM", "ARMOURED")
        it.update({"source": {"sheet": "s", "row": 1}, "labels": {"conductor": "cu", "armour": "armoured"}})
        with self.assertRaises(frappe.ValidationError) as cm:
            loader._validate_items([it])
        self.assertIn("labels differ", str(cm.exception.args) + str(getattr(cm.exception, "title", "")) + str(frappe.local.message_log))

    def test_an_older_file_without_labels_loads(self):
        it = self._cable("ALUMINIUM", "ARMOURED")
        it.update({"source": {"sheet": "s", "row": 1}})
        it.pop("labels", None)
        loader._validate_items([it])


class TestLabelValueGuard(FrappeTestCase):
    """T1- : code naming a label value no rule makes is RED (the scan) and refused at run time (`lv`)."""

    SCAN_DIRS = ("nirmaan_stack/services/boq_rate_master", "nirmaan_stack/api/boq",
                 "frontend/src/pages/boq-wizard", "frontend/src/pages/pricing")
    PY = re.compile(r"""\blv\(\s*["']([a-z_]+)["']\s*,\s*["']([^"']+)["']\s*\)""")
    TS = re.compile(r"""\blabelValue\(\s*["']([a-z_]+)["']\s*,\s*["']([^"']+)["']\s*\)""")

    def _scan(self, text):
        return [(m.group(1), m.group(2)) for rx in (self.PY, self.TS) for m in rx.finditer(text)
                if (m.group(1), m.group(2)) not in CL.all_label_values()]

    def test_every_label_value_named_in_code_is_made_by_a_rule(self):
        bad, seen = [], 0
        for d in self.SCAN_DIRS:
            for root, _dirs, files in os.walk(os.path.join(APP, d)):
                if "node_modules" in root:
                    continue
                for f in files:
                    if f.endswith((".py", ".ts", ".tsx")) and not f.startswith("test_") and ".test." not in f:
                        text = open(os.path.join(root, f), encoding="utf-8").read()
                        seen += len(self.PY.findall(text)) + len(self.TS.findall(text))
                        bad += [(f,) + b for b in self._scan(text)]
        self.assertEqual(bad, [])
        self.assertGreaterEqual(seen, 12)   # the readers really name labels this way (vacuity: the scan sees them)

    def test_a_planted_value_no_rule_makes_is_red(self):
        self.assertEqual(self._scan('x = lv("conductor", "tinned copper")'), [("conductor", "tinned copper")])
        self.assertEqual(self._scan('const y = labelValue("poles", "5");'), [("poles", "5")])
        with self.assertRaises(ValueError):
            CL.lv("conductor", "tinned copper")


class TestMovedReaders(FrappeTestCase):
    """T2 : the moved Python readers pick the same rows through the labels."""

    def _catalog(self, extra=None):
        base = {
            "32A SP MCB C": {"device": "MCB", "pole": "SP", "amp_a": 32, "curve": "C"},
            "32A DP MCB C": {"device": "MCB", "pole": "DP", "amp_a": 32, "curve": "C"},
            "32A TP MCB C": {"device": "MCB", "pole": "TP", "amp_a": 32, "curve": "C"},
            "32A FP MCB C": {"device": "MCB", "pole": "FP", "amp_a": 32, "curve": "C"},
        }
        base.update(extra or {})
        return base

    def _row(self, text):
        return {"description": text, "anc_headers": [], "notes": ""}

    def test_tpn_text_ladders_tp_to_fp_through_the_label(self):
        out = {"a": {"value": "32A TP MCB C"}}
        ch = extraction.apply_pole_plus_neutral_ladder(out, self._row("32A TPN MCB C curve"), self._catalog())
        self.assertEqual(out["a"]["value"], "32A FP MCB C")
        self.assertEqual(ch[0]["to"], "32A FP MCB C")

    def test_a_dormant_tpn_sku_is_found_by_rung_1(self):
        cat = self._catalog({"32A TPN MCB C": {"device": "MCB", "pole": "TPN", "amp_a": 32, "curve": "C"}})
        out = {"a": {"value": "32A TP MCB C"}}
        ch = extraction.apply_pole_plus_neutral_ladder(out, self._row("32A TPN MCB C curve"), cat)
        self.assertEqual(out["a"]["value"], "32A TPN MCB C")
        self.assertEqual(ch[0].get("rung"), 1)

    def test_an_unknown_pole_spelling_is_never_a_candidate(self):
        cat = {"32A X MCB C": {"device": "MCB", "pole": "3P+N", "amp_a": 32, "curve": "C"},
               "32A FP MCB C": {"device": "MCB", "pole": "FP", "amp_a": 32, "curve": "C"}}
        out = {"a": {"value": "32A X MCB C"}}
        self.assertEqual(extraction.apply_pole_plus_neutral_ladder(out, self._row("32A TPN MCB C curve"), cat), [])
        self.assertEqual(out["a"]["value"], "32A X MCB C")

    def test_corroborator_agrees_through_the_label(self):
        cells = {"material": {"value": "COPPER"}, "insulation": {"value": "ARMOURED"}, "core": {"value": 3}}
        extraction._corroborate(self._row("3C x 2.5 sqmm Cu armoured cable"), cells)
        self.assertEqual({k: v["corroborated"] for k, v in cells.items()}, {"material": True, "insulation": True, "core": True})
        cells = {"material": {"value": "ALUMINIUM"}, "insulation": {"value": "UNARMOURED"}}
        extraction._corroborate(self._row("copper armoured cable"), cells)
        self.assertEqual({k: v["corroborated"] for k, v in cells.items()}, {"material": False, "insulation": False})
        cells = {"material": {"value": "COPPER CLAD ALUMINIUM"}}
        extraction._corroborate(self._row("copper cable"), cells)
        self.assertFalse(cells["material"]["corroborated"])   # an unlabelled value never corroborates


class TestServedConfigAddsNoCostKey(FrappeTestCase):
    """T3b (BCS reply (i)) : after a role filter removed the cost keys, the served config's last step adds none back."""

    COST = re.compile(r"bcs|cost", re.I)

    def _stub_withhold(self, cfg):
        def strip(node):
            if isinstance(node, dict):
                return {k: strip(v) for k, v in node.items() if not self.COST.search(k)}
            if isinstance(node, list):
                return [strip(x) for x in node]
            return node
        return strip(cfg)

    def _keys(self, node, out=None):
        out = set() if out is None else out
        if isinstance(node, dict):
            for k, v in node.items():
                out.add(k)
                self._keys(v, out)
        elif isinstance(node, list):
            for x in node:
                self._keys(x, out)
        return out

    def test_the_helper_puts_no_cost_key_back(self):
        from nirmaan_stack.api.boq import rate_master
        row = frappe.get_all("BoQ Rate Category Config", filters={"discipline": "Electrical", "category_id": "wiring_cabling", "active": 1},
                             fields=["name", "discipline", "category_id", "config"], limit=1)[0]
        cfg = json.loads(row["config"]) if isinstance(row["config"], str) else row["config"]
        cfg = copy.deepcopy(cfg)
        cfg["bcs_default_margin"] = {"supply": 0.1}
        cfg.setdefault("pipelines", {})["bcs_cost"] = {"steps": [{"step": "lookup"}]}
        withheld = self._stub_withhold(cfg)
        self.assertFalse([k for k in self._keys(withheld) if self.COST.search(k)])
        served = rate_master._serve_category_config(dict(row, config=withheld))["config"]
        self.assertFalse([k for k in self._keys(served) if self.COST.search(k)])
        # NEGATIVE (the check can see a cost key): without the stub, one is served
        unfiltered = rate_master._serve_category_config(dict(row, config=copy.deepcopy(cfg)))["config"]
        self.assertTrue([k for k in self._keys(unfiltered) if self.COST.search(k)])

    def test_the_item_helper_adds_only_labels(self):
        from nirmaan_stack.api.boq import rate_master
        it = {"kind": "cable", "attributes": {"material": "COPPER", "insulation": "ARMOURED"}, "rates": {"supply": 1}}
        before = set(it)
        rate_master._serve_items([it])
        self.assertEqual(set(it) - before, {"labels", "label_flags"})


class TestPromptWordGuard(FrappeTestCase):
    """B4 (owner 2026-11-26 00:22): the attribute prompt's hint words must stay catalogue values of wiring_cabling."""

    @staticmethod
    def problems(words, prompt_text, items, kinds):
        carried = {str(v) for it in items if it.get("kind") in kinds for v in (it.get("attributes") or {}).values()}
        out = []
        for w in words:
            if not re.search(r"\b%s\b" % re.escape(w), prompt_text):
                out.append("%s: not in the prompt any more (update the guard with the prompt)" % w)
            elif w not in carried:
                out.append("%s: the prompt teaches it but no active wiring_cabling SKU carries it" % w)
        return out

    def _ctx(self):
        cfg = frappe.get_all("BoQ Rate Category Config", filters={"discipline": "Electrical", "category_id": "wiring_cabling", "active": 1},
                             fields=["config"], limit=1)[0]["config"]
        cfg = json.loads(cfg) if isinstance(cfg, str) else cfg
        kinds = set(cfg.get("item_kinds") or [])
        for pl in (cfg.get("pipelines") or {}).values():   # a legacy config names its kinds in its match steps
            for st in pl.get("steps") or []:
                k = (st.get("params") or {}).get("kind")
                if st.get("step") == "match_master_row" and isinstance(k, str):
                    kinds.add(k)
        with open(PROMPT, encoding="utf-8") as fh:
            return fh.read(), _served("Electrical"), kinds

    def test_every_prompt_word_is_a_catalogue_value(self):
        text, items, kinds = self._ctx()
        self.assertTrue(kinds)
        self.assertEqual(self.problems(PROMPT_WORDS, text, items, kinds), [])

    def test_red_when_a_word_stops_being_a_catalogue_value(self):
        text, items, kinds = self._ctx()
        scratch = copy.deepcopy(items)
        for it in scratch:
            for k, v in list((it.get("attributes") or {}).items()):
                if v == "UNARMOURED":
                    it["attributes"][k] = "UN-ARMOURED"
        self.assertEqual(len(self.problems(PROMPT_WORDS, text, scratch, kinds)), 1)


class TestFixtureEqualsRule(FrappeTestCase):
    """FIX : the vitest fixture is the rule's own output; the TS label values are the rule's."""

    def test_fixture_equals_the_rule_over_the_newest_files(self):
        with open(FIXTURE, encoding="utf-8") as fh:
            fx = json.load(fh)
        items = _newest("rate_master_hvac_all_v*.json")["items"] + _newest("rate_master_electrical_all_v*.json")["items"]
        self.assertEqual(fx["rules"], json.loads(json.dumps(CL.value_label_map(items))))
        want = {}
        for lid, lv in CL.all_label_values():
            want.setdefault(lid, set()).add(lv)
        self.assertEqual({k: set(v) for k, v in fx["label_values"].items()}, want)

    def test_ts_label_values_equal_the_rule(self):
        text = open(TS_LABELS, encoding="utf-8").read()
        block = re.search(r"export const LABEL_VALUES = \{(.*?)\} as const;", text, re.S).group(1)
        ts = {m.group(1): set(re.findall(r'"([^"]+)"', m.group(2))) for m in re.finditer(r"(\w+): \[([^\]]*)\]", block)}
        want = {}
        for lid, lv in CL.all_label_values():
            want.setdefault(lid, set()).add(lv)
        self.assertEqual(ts, want)


class TestServedItemValues(FrappeTestCase):
    """T3 (owner 2026-11-26 00:06, R7; ANSWER 1 QR-C-P2 (a)): the Rate Master Add-row lists read `item_values`, served BESIDE
    the config -- every value the category's grid items carry (VRF brand from the row) -- while the config itself (and so
    `attribute_definitions`, the panel and the rules page) is byte-identical to what it was served before."""

    def _serve(self, discipline, cid):
        from nirmaan_stack.api.boq import rate_master
        return rate_master.get_rate_category_config(discipline=discipline, category_id=cid)

    def _grid_values(self, discipline, cfg, attr):
        from nirmaan_stack.services.boq_rate_master import catalogue_lists as CLS
        kinds = CLS.rate_master_kinds(cfg)
        out = set()
        for it in _served(discipline):
            if it["kind"] in kinds:
                v = it.get("brand") if attr == "brand" and "brand" not in it["attributes"] else it["attributes"].get(attr)
                if v not in (None, ""):
                    out.add(v)
        return out

    def test_vrf_and_vav_lists_are_what_the_items_carry(self):
        for disc, cid, attrs in (("HVAC", "hvac_vrf", ("item", "item_detail", "brand")), ("HVAC", "hvac_vav_box", ("vav_item", "item_name"))):
            r = self._serve(disc, cid)
            for attr in attrs:
                want = self._grid_values(disc, r["config"], attr)
                self.assertTrue(want, (cid, attr))
                self.assertEqual(set(r["item_values"].get(attr) or []), want, (cid, attr))
            # the drift CAT-D1 E8 P2 measured is real: the definition lists FEWER values than the items carry
            defs = {d["id"]: set(d.get("values") or []) for d in r["config"]["attribute_definitions"]}
            first = attrs[0]
            self.assertTrue(set(r["item_values"][first]) - defs.get(first, set()), (cid, first))

    def test_the_config_is_served_exactly_as_before(self):
        from nirmaan_stack.services.boq_rate_master import catalogue_lists as CLS
        for disc, cid in (("HVAC", "hvac_vrf"), ("Electrical", "wiring_cabling"), ("HVAC", "hvac_valve_package")):
            row = frappe.get_all("BoQ Rate Category Config", filters={"discipline": disc, "category_id": cid, "active": 1},
                                 fields=["config"], limit=1)[0]
            stored = json.loads(row["config"]) if isinstance(row["config"], str) else row["config"]
            served = self._serve(disc, cid)
            self.assertEqual(served["config"], CLS.serve_config(disc, copy.deepcopy(stored), fresh=True), cid)
            self.assertNotIn("item_values", served["config"])

    def test_the_row_gains_only_item_values(self):
        r = self._serve("HVAC", "hvac_vrf")
        self.assertEqual(set(r) - {"name", "discipline", "category_id", "config", "source_workbook", "import_batch"}, {"item_values"})

    def test_an_unknown_category_serves_no_values(self):
        from nirmaan_stack.services.boq_rate_master import catalogue_lists as CLS
        self.assertEqual(CLS.served_item_values("HVAC", "no_such_category"), {})


class TestTsLabelFrom(FrappeTestCase):
    """The TS display map (`catalogueLabels.ts` LABEL_FROM, used only to show the row's own value on a chip) = the rule's from_attr;
    CAPTURE_LABELS = the rules whose value is a capture."""

    def test_label_from_equals_the_rule(self):
        text = open(TS_LABELS, encoding="utf-8").read()
        block = re.search(r"export const LABEL_FROM = \{(.*?)\} as const;", text, re.S).group(1)
        ts = dict(re.findall(r"(\w+): \"([^\"]+)\"", block))
        self.assertEqual(ts, {r["id"]: r["from_attr"] for r in CL.LABEL_RULES})
        cap = set(re.findall(r'"([a-z_]+)"', re.search(r"CAPTURE_LABELS[^=]*= new Set\(\[(.*?)\]\)", text, re.S).group(1)))
        self.assertEqual(cap, {r["id"] for r in CL.LABEL_RULES if any(lv == "{1}" for _rx, lv in r["cases"])})
