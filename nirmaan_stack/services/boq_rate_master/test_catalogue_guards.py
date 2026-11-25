"""CAT-1 (2026-11-26) -- THE GUARDS FOR FUTURE BUILDS (owner 2026-11-26 00:14, verbatim: "also we need to put guards that future builds
cant bypass these again" / "and the build follows this principle everytime"). Each is GREEN on the committed tree and RED on one
injected typed value in a NEW place.

  C1     the commit guard as a suite module: `scripts/residence_check.py` rule C1 over its scope (the BoQ / rate-master folders and
         the rate-master prompt files; QR-TEAM (a), owner 01:47) = 0 drift against `scripts/catalogue_allowlist.json`; a NEW code file
         typing a catalogue value fails, naming the file and the word; every frozen entry carries a reason and a ruling.
  PROSE  G-PROSE: config wording naming a multi-word catalogue value outside a placeholder = today's frozen count on the newest HVAC
         and Electrical files (QR-C-1 (a): CAT-1b converts them); a NEW typed mention fails.
  WORDS  the prompt-word guard (ANSWER 1 item 1; QR-SCOPE-1 (a)): COPPER / ALUMINIUM / ARMOURED / UNARMOURED in the attribute
         extraction prompt are catalogue values of the cable kinds; every allow-listed word of the other rate-master prompts is a
         catalogue value of the newest files. RED if one stops being one.
  SPEC   the spec_reader guard (QR-SCOPE-3 (a)): `spec_reader.ADP_FAMILIES` equals the ADP SKUs' families.
Run: bench --site localhost run-tests --module nirmaan_stack.services.boq_rate_master.test_catalogue_guards
"""
import copy
import importlib.util
import json
import os
import re
import sys
import tempfile
from pathlib import Path

from frappe.tests.utils import FrappeTestCase

from nirmaan_stack.services.boq_rate_master import catalogue_gate as CL   # G-PROSE lives in catalogue_gate
from nirmaan_stack.services.boq_rate_master import loader, spec_reader

DATA = os.path.join(os.path.dirname(loader.__file__), "data")
APP = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(loader.__file__))))
PROMPTS = os.path.join(APP, "nirmaan_stack/services/boq_category/prompts")


def _residence():
    sys.path.insert(0, os.path.join(APP, "scripts"))
    spec = importlib.util.spec_from_file_location("residence_check_cat1", os.path.join(APP, "scripts/residence_check.py"))
    m = importlib.util.module_from_spec(spec)
    sys.modules["residence_check_cat1"] = m      # a dataclass in it looks its module up here
    spec.loader.exec_module(m)
    return m


def _newest(prefix):
    fs = [f for f in os.listdir(DATA) if re.fullmatch(re.escape(prefix) + r"\d+\.json", f)]
    f = max(fs, key=lambda x: int(re.search(r"_v(\d+)\.json$", x).group(1)))
    with open(os.path.join(DATA, f), encoding="utf-8") as fh:
        return json.load(fh)


class TestC1CommitGuard(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.R = _residence()

    def test_c1_01_green_on_the_tree(self):
        self.assertEqual(self.R.catalogue_words_unfrozen(), [])

    def test_c1_02_every_frozen_entry_has_a_reason_and_a_ruling(self):
        frozen = json.load(open(os.path.join(APP, self.R.CATALOGUE_ALLOWLIST), encoding="utf-8"))
        self.assertTrue(frozen)
        for path, lits in frozen.items():
            for lit, e in lits.items():
                self.assertTrue(e.get("count", 0) > 0 and str(e.get("reason", "")).strip() and str(e.get("ruling", "")).strip(),
                                (path, lit))

    def test_c1_03_red_on_a_new_file_typing_a_catalogue_word(self):
        vocab = self.R.catalogue_vocabulary()
        word = "Ball Valve" if "Ball Valve" in vocab else sorted(v for v in vocab if " " in v)[0]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "newHelper.ts"
            p.write_text(f'export const pick = (x: string) => x === "{word}";\n', encoding="utf-8")
            found = self.R.catalogue_words_found(extra=[p], vocab=vocab)
            drift = self.R.catalogue_word_drift(found, json.load(open(os.path.join(APP, self.R.CATALOGUE_ALLOWLIST), encoding="utf-8")))
        self.assertEqual(len(drift), 1, drift)
        self.assertIn("newHelper.ts", drift[0])
        self.assertIn(word, drift[0])

    def test_c1_04_red_on_one_more_word_in_an_allow_listed_file_and_on_a_stale_count(self):
        frozen = json.load(open(os.path.join(APP, self.R.CATALOGUE_ALLOWLIST), encoding="utf-8"))
        found = self.R.catalogue_words_found()
        path = next(iter(sorted(found)))
        lit = next(iter(sorted(found[path])))
        more = copy.deepcopy(found); more[path][lit] += 1
        self.assertTrue(any("typed" in x and path in x for x in self.R.catalogue_word_drift(more, frozen)))
        fewer = copy.deepcopy(found); fewer[path][lit] -= 1
        self.assertTrue(any("fewer" in x for x in self.R.catalogue_word_drift(fewer, frozen)))

    def test_c1_05_scoped_to_the_boq_folders_and_not_yet_in_the_hook(self):
        # QR-HOOK (2026-11-26 03:47): the hook registration waits for the owner (it needs a residence_baseline.json entry, which the
        # CAT-1 brief forbids editing) -- this suite module is the guard meanwhile; the line below flips when C1 joins CHECKS
        self.assertEqual([c for c in self.R.CHECKS if c.rule == "C1"], [])
        self.assertTrue(all(d.startswith(("nirmaan_stack/api/boq", "nirmaan_stack/services/boq_rate", "frontend/src/pages/boq-wizard",
                                          "frontend/src/pages/pricing")) for d in self.R.CATALOGUE_CODE_DIRS))


class TestGProse(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with open(os.path.join(os.path.dirname(CL.__file__), CL.PROSE_ALLOWLIST), encoding="utf-8") as fh:
            cls.frozen = json.load(fh)["paths"]
        cls.H, cls.E = _newest("rate_master_hvac_all_v"), _newest("rate_master_electrical_all_v")

    def _found(self, *assets):
        out = {}
        for a in assets:
            out.update(CL.prose_mentions(a["category_configs"], a["items"]))
        return out

    def test_prose_01_green_today(self):
        self.assertEqual(CL.prose_drift(self._found(self.H, self.E), self.frozen), [])

    def test_prose_02_red_on_a_new_typed_mention_and_green_as_a_placeholder(self):
        h = copy.deepcopy(self.H)
        valve = next(c for c in h["category_configs"] if c["category_id"] == "hvac_valve_package")
        valve["notes"] = (valve.get("notes") or "") + " A Sluice / Gate Valve is priced as written."
        red = CL.prose_drift(self._found(h, self.E), self.frozen)
        self.assertTrue(red and all("hvac_valve_package > notes" in x for x in red), red)
        valve["notes"] = valve["notes"].replace("Sluice / Gate Valve", "{{cat:family=Sluice / Gate Valve}}")
        self.assertEqual([x for x in CL.prose_drift(self._found(h, self.E), self.frozen) if "notes" in x], [])


class TestPromptWords(FrappeTestCase):
    def test_words_01_the_cable_hint_words_are_catalogue_values(self):
        text = open(os.path.join(PROMPTS, "boq_rate_attr_extraction_prompt.md"), encoding="utf-8").read()
        e = _newest("rate_master_electrical_all_v")
        carried = {v for i in e["items"] if i["kind"] in ("cable", "termination") for v in (i.get("attributes") or {}).values()
                   if isinstance(v, str)}
        for w in ("COPPER", "ALUMINIUM", "ARMOURED", "UNARMOURED"):
            self.assertIn(w, text, w)
            self.assertIn(w, carried, f"{w} is no longer a catalogue value of the cable kinds - update the prompt")

    def test_words_02_negative_a_word_the_catalogue_drops_is_caught(self):
        e = _newest("rate_master_electrical_all_v")
        for i in e["items"]:
            for k, v in list((i.get("attributes") or {}).items()):
                if v == "ARMOURED":
                    i["attributes"][k] = "STEEL ARMOURED"
        carried = {v for i in e["items"] if i["kind"] in ("cable", "termination") for v in (i.get("attributes") or {}).values()
                   if isinstance(v, str)}
        self.assertNotIn("ARMOURED", carried)

    def test_words_03_every_allow_listed_prompt_word_is_a_catalogue_value(self):
        R = _residence()
        vocab = {v.strip().lower() for v in R.catalogue_vocabulary()}
        frozen = json.load(open(os.path.join(APP, R.CATALOGUE_ALLOWLIST), encoding="utf-8"))
        prompts = [p for p in frozen if p.endswith((".md", ".txt"))]
        self.assertTrue(prompts)
        for p in prompts:
            for w in frozen[p]:
                self.assertIn(w.strip().lower(), vocab, (p, w))


class TestSpecReaderFamilies(FrappeTestCase):
    def test_spec_01_adp_families_equal_the_adp_skus_families(self):
        h = _newest("rate_master_hvac_all_v")
        adp = next(c for c in h["category_configs"] if c["category_id"] == "hvac_adp")
        kind, fam = adp["list_spec"]["pricing"]["kind"], adp["list_spec"]["family_attribute_id"]
        skus = {i["attributes"].get(fam) for i in h["items"] if i["kind"] == kind}
        self.assertEqual(set(spec_reader.ADP_FAMILIES), skus)
        self.assertEqual(len(spec_reader.ADP_FAMILIES), len(set(spec_reader.ADP_FAMILIES)))

    def test_spec_02_negative_a_family_the_catalogue_adds_is_caught(self):
        h = _newest("rate_master_hvac_all_v")
        adp = next(c for c in h["category_configs"] if c["category_id"] == "hvac_adp")
        kind, fam = adp["list_spec"]["pricing"]["kind"], adp["list_spec"]["family_attribute_id"]
        donor = copy.deepcopy(next(i for i in h["items"] if i["kind"] == kind))
        donor["attributes"][fam] = "CAT1 new diffuser"
        skus = {i["attributes"].get(fam) for i in h["items"] + [donor] if i["kind"] == kind}
        self.assertNotEqual(set(spec_reader.ADP_FAMILIES), skus)
