"""CAT-2 (2026-11-27) -- HVAC v91 (owner 2026-11-26 00:10 / 01:16, R1 / R5; ANSWER to CAT2-4 QR-FORM). Every check has a NEGATIVE.

  V91   v91 = v90 + cat2Edits.json exactly (the mint's own transformation: one `list_spec.code_targets` block on each of four configs,
        nothing else; every item byte-identical); a planted undeclared change is not v91.
  GATE  the reference gate refuses nothing on v91 and checks every code target (STRICT); a v91 code target renamed is refused by path.
  T5    every eligible HVAC category's whole request through THE ONE MERGE is byte-identical on v90 and v91, and no request carries '{{'
        -- the new key reaches no model request (a planted key that DID reach the request text would differ: shown by the NEGATIVE).
  UNDO  cat2_undo_support.as_v90 gives v90's config back from v91's; v90 comes back as it is; a different block raises.
Run: bench --site localhost run-tests --module nirmaan_stack.services.boq_rate_master.test_cat2_v91
"""
import copy
import json
import os

from frappe.tests.utils import FrappeTestCase

from nirmaan_stack.services.boq_rate_master import catalogue_gate as CG
from nirmaan_stack.services.boq_rate_master import catalogue_lists as CL
from nirmaan_stack.services.boq_rate_master import cat2_undo_support, extraction, loader

DATA = os.path.join(os.path.dirname(loader.__file__), "data")
APP = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(loader.__file__))))
V90, V91 = "rate_master_hvac_all_v90.json", "rate_master_hvac_all_v91.json"
EDITS = os.path.join(APP, "frontend/src/pages/boq-wizard/rate-helper/__fixtures__/cat2Edits.json")


def _asset(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as fh:
        a = json.load(fh)
    for c in a["category_configs"]:
        c["discipline"] = a["discipline"]
    return a


def _canon(o):
    return json.dumps(o, sort_keys=True, ensure_ascii=False)


def _requests(asset):
    stored = asset["category_configs"]
    built = CL.build([dict(i, active=1) for i in asset["items"]], stored)
    cfgs = {(c["discipline"], c["category_id"]): CL.merge_config(c, built, "HVAC") for c in stored}
    out = {}
    for c in stored:
        k = (c["discipline"], c["category_id"])
        if not extraction.config_is_eligible(c, cfgs):
            continue
        ctx = extraction._group_context(cfgs, *k)
        out[c["category_id"]] = extraction.batch_prompt_content(
            ctx["prompt"], ctx["defs"], [], synonyms=ctx["synonyms"], defaults=ctx["defaults"], none_guidance=ctx["none_guidance"],
            slot_spec=ctx["slot_spec"], resolution_rules=ctx["resolution_rules"], rules=ctx["rules"], items_spec=ctx["items_spec"])
    return out


class TestHvacV91(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.v90, cls.v91 = _asset(V90), _asset(V91)
        with open(EDITS, encoding="utf-8") as fh:
            cls.K = json.load(fh)

    def _apply(self, base):
        out = copy.deepcopy(base)
        by = {e["c"]: e for e in self.K["configs"]}
        for c in out["category_configs"]:
            e = by.get(c["category_id"])
            if e:
                self.assertEqual(e["p"], ["list_spec", "code_targets"])
                self.assertNotIn("code_targets", c["list_spec"])
                c["list_spec"]["code_targets"] = copy.deepcopy(e["to"])
        return out

    def test_v91_is_v90_plus_the_edits_exactly(self):
        self.assertEqual(self.K["pricing_inputs"], {})
        self.assertEqual(_canon(self.v91["items"]), _canon(self.v90["items"]))
        self.assertEqual(_canon(self._apply(self.v90)["category_configs"]), _canon(self.v91["category_configs"]))
        self.assertEqual(sorted(c["category_id"] for c in self.v91["category_configs"] if "code_targets" in c.get("list_spec", {})),
                         sorted(e["c"] for e in self.K["configs"]))
        planted = copy.deepcopy(self.v91)
        planted["category_configs"][0].setdefault("notes", [])
        planted["category_configs"][0]["notes"] = list(planted["category_configs"][0]["notes"]) + ["planted"]
        self.assertNotEqual(_canon(self._apply(self.v90)["category_configs"]), _canon(planted["category_configs"]))

    def test_gate_checks_every_code_target(self):
        stored = self.v91["category_configs"]
        self.assertEqual([CG.format_problem(p) for p in CG.reference_problems(stored, self.v91["items"], "HVAC") if p["severity"] == CG.REFUSE], [])
        by = {c["category_id"]: c for c in stored}
        refs = [r for c in stored for r in CG.code_target_refs(c, by) if r[4] is None]
        self.assertEqual(len(refs), self.K["counts"]["values"] + 1)          # + paint_row.family
        bad = copy.deepcopy(stored)
        cid, role = self.K["configs"][-1]["c"], sorted(self.K["configs"][-1]["to"])[0]
        for c in bad:
            if c["category_id"] == cid:
                t = c["list_spec"]["code_targets"][role]
                if "value" in t:
                    t["value"] += " (renamed)"
                else:
                    t["values"][0] += " (renamed)"
        got = [(p["config"], p["path"]) for p in CG.reference_problems(bad, self.v91["items"], "HVAC") if p["severity"] == CG.REFUSE]
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0][0], cid)
        self.assertTrue(got[0][1].startswith("list_spec.code_targets.%s." % role), got)

    def test_t5_requests_byte_identical_and_no_braces(self):
        a, b = _requests(self.v90), _requests(self.v91)
        self.assertEqual(sorted(a), sorted(b))
        self.assertGreaterEqual(len(b), 7)
        self.assertEqual([k for k in a if a[k] != b[k]], [])
        self.assertEqual([k for k in b if "{{" in b[k]], [])
        # NEGATIVE: the comparison sees a change that DOES reach a request (a definition's question text on one eligible config)
        planted = copy.deepcopy(self.v91)
        cid = sorted(b)[0]
        for c in planted["category_configs"]:
            if c["category_id"] == cid:
                d = c["list_spec"]["attribute_definitions"][0]
                d["label"] = str(d.get("label", "")) + " planted"
        self.assertNotEqual(_requests(planted)[cid], b[cid])

    def test_undo_as_v90(self):
        for a, b in zip(self.v90["category_configs"], self.v91["category_configs"]):
            self.assertEqual(_canon(cat2_undo_support.as_v90(copy.deepcopy(b))), _canon(a), a["category_id"])
            self.assertEqual(_canon(cat2_undo_support.as_v90(copy.deepcopy(a))), _canon(a), a["category_id"])
        other = copy.deepcopy(next(c for c in self.v91["category_configs"] if "code_targets" in c.get("list_spec", {})))
        other["list_spec"]["code_targets"] = {"x": {"attr": "a", "value": "b"}}
        with self.assertRaises(AssertionError):
            cat2_undo_support.as_v90(other)
