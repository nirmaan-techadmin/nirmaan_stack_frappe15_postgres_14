"""CAT-3 (2026-11-28) -- HVAC v92 = v91 + the two one-item facts as item notes + the labels emitted (QR-NOTE (a), QR-NOTE-2 (a)). Every check
has a NEGATIVE. Files only (no database).

  V92+  v92 = v91 + cat3Edits.json exactly: items less `labels` / `item_notes` byte-identical, labels = the rule, notes on the two declared
        items only; configs differ at the two declared strings only.  V92- a planted extra change is seen.
  SRV+  every v92 config through the served merge = v91's, byte for byte (the two notes give back the words their placeholders replaced).
  SRV-  a note emptied makes the gate refuse that reference.
  UNDO  cat3_undo_support.as_v91 gives v91's configs back; a config holding neither string is refused.
Run: bench --site localhost run-tests --module nirmaan_stack.services.boq_rate_master.test_cat3_v92
"""
import copy
import json
import os

from frappe.tests.utils import FrappeTestCase

from nirmaan_stack.services.boq_rate_master import catalogue_gate, catalogue_labels, catalogue_lists, cat3_undo_support, loader

DATA = os.path.join(os.path.dirname(loader.__file__), "data")


def _load(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as fh:
        return json.load(fh)


def _canon(o):
    return json.dumps(o, sort_keys=True, ensure_ascii=False)


class TestV92(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.v91, cls.v92 = _load("rate_master_hvac_all_v91.json"), _load("rate_master_hvac_all_v92.json")
        cls.edits = cat3_undo_support.edits()

    def _diff(self, a, b):
        strip = lambda i: {k: v for k, v in i.items() if k not in ("labels", "item_notes")}   # noqa: E731
        items = [x for x, y in zip(a["items"], b["items"]) if _canon(strip(y)) != _canon(x)]
        back = copy.deepcopy(b["category_configs"])
        for c in back:
            c.update(cat3_undo_support.as_v91(c))
        cfgs = [x["category_id"] for x, y in zip(a["category_configs"], back) if _canon(x) != _canon(y)]
        return items, cfgs

    def test_v92_is_v91_plus_the_edits_exactly(self):
        self.assertEqual(len(self.v91["items"]), len(self.v92["items"]))
        self.assertEqual(self._diff(self.v91, self.v92), ([], []))
        for it in self.v92["items"]:
            self.assertEqual(it["labels"], catalogue_labels.labels_for(it["kind"], it["attributes"])[0], it["item_uid"])
        noted = {i["item_uid"]: i["item_notes"] for i in self.v92["items"] if i.get("item_notes")}
        self.assertEqual(noted, {u: e["item_notes"] for u, e in self.edits["items"].items()})
        self.assertEqual(sorted({e["c"] for e in self.edits["configs"]}), ["hvac_misc", "hvac_valve_package"])

    def test_a_planted_change_is_seen(self):
        bad = copy.deepcopy(self.v92)
        bad["items"][0]["rates"] = dict(bad["items"][0]["rates"], planted=1)
        cfg = next(c for c in bad["category_configs"] if c["category_id"] == "hvac_vrf")
        cfg["planted"] = True
        items, cfgs = self._diff(self.v91, bad)
        self.assertEqual((len(items), cfgs), (1, ["hvac_vrf"]))

    def _served(self, a):
        stored = [dict(c, discipline=a["discipline"]) for c in a["category_configs"]]
        built = catalogue_lists.build([dict(i, active=1) for i in a["items"]], stored)
        return {c["category_id"]: catalogue_lists.merge_config(c, built, "HVAC") for c in stored}, stored

    def test_every_config_serves_byte_identical_to_v91(self):
        s91, _ = self._served(self.v91)
        s92, _ = self._served(self.v92)
        self.assertEqual({k: _canon(v) for k, v in s92.items()}, {k: _canon(v) for k, v in s91.items()})

    def test_the_gate_passes_and_refuses_an_empty_note(self):
        _s, stored = self._served(self.v92)
        refusals = lambda items: [p for p in catalogue_gate.reference_problems(stored, items, "HVAC") if p["severity"] == "REFUSE"]   # noqa: E731
        self.assertEqual(refusals(self.v92["items"]), [])
        emptied = copy.deepcopy(self.v92["items"])
        for it in emptied:
            if it.get("item_notes"):
                it["item_notes"] = ""
        self.assertEqual(len(refusals(emptied)), 2)

    def test_undo_refuses_a_foreign_note_and_leaves_an_older_string(self):
        e = self.edits["configs"][0]
        cfg = copy.deepcopy(next(c for c in self.v92["category_configs"] if c["category_id"] == e["c"]))
        node = cfg
        for p in e["p"][:-1]:
            node = node[p]
        node[e["p"][-1]] = "an older file's own wording"
        self.assertEqual(cat3_undo_support.as_v91(cfg), cfg)          # an older string comes back as it is
        node[e["p"][-1]] = "{{note:rmi-someone-else}}"
        with self.assertRaises(AssertionError):                         # a foreign note placeholder is refused
            cat3_undo_support.as_v91(cfg)
