"""SLICE 12e-1 -- HVAC v34 = v33 + THE PIPING CATALOGUE (owner rulings 2026-10-09; resume addendum 17:39).

What these tests protect, in plain English:

  TestSlice12e1AssetV34 (file-only, no DB)
    01  v34 is v33 plus Piping and NOTHING else: every v33 item is in v34 unchanged (by item_uid, both
        directions), every v33 config is in v34 unchanged (by category_id), every other top-level key is
        byte-identical. One category at a time (preamble block 17).
    02  the FORTY items are NAMED by family and size, and each carries the sheet's four figures exactly
        (Total BCS Supply, BCS Installation, supply markup, install markup), unit Mts, sheet provenance, a
        unique rmi- uid, the size in the sheet's own spelling and no inch attribute. Counts 13 / 13 / 8 / 6.
        Copper install is a flat 110 at every size (ruling); copper 31.7 carries 110 x (1 + 1.0) = 220.
    03  the two MS links are LIVE declarations in the config's `derived_rates` -- the same mechanism
        Insulation's 176 cells use -- on BOTH cost columns: MS 300 = 2 x MS 150; MS 250 = MS 150 + MS 100
        as a TWO-SOURCE list; and the stored values already satisfy them (what the loader re-checks).
    04  the config is DATA-ONLY: definitions for pipe_type + size_mm, pipelines {}, no list_spec -- so it
        is NOT eligible for pricing or extraction (the panel shows "coming soon", 12e-2 brings the rules).
    05  NEGATIVE: the validator refuses a Piping link that is not flattened (a term reading a derived
        cell) and the recompute refuses a link to a missing base -- a link that cannot be trusted is
        refused, never silently kept.
    06  the CURRENT asset (v35) is the newest HVAC asset on disk (derived from the directory, never a named
        future number).
    07  SLICE 12e-1b (owner 2026-10-10, "kept exactly as per the excel file", ruling option (a)): every one of
        the 40 Piping items carries `attributes.item_name` = its sheet column A text VERBATIM (by sheet row), the
        Piping config declares `item_name` FIRST as a plain choice over the four sheet texts in sheet order
        (label "Item", no attributes_from_spec, no selector / panel flag -- Insulation's `type` shape), and
        v35 differs from v34 by exactly that key and that definition. NEGATIVE: the same check REFUSES a
        Piping item whose name is missing, blank, or not one of the four sheet texts -- no validator in the
        loader checks that an item carries every declared attribute, so this test is the asset check.

  TestSlice12e1LiveLinks (the LIVE site, after the v35 load -- v34's forty rows plus their names)
    live_01  the grid's own write path (`update_rate_master_item`, rates_patch) on MS 150 BCS supply +10
             moves MS 300 by +20 and MS 250 by +10; restoring moves both back -- recorded and restored.
    live_02  the served items (what the Rate Master grid and every pricer reads) carry the 40 Piping rows
             with the sheet's figures, and the two MS rows are the category's only derived cells (stored, never projected).
    live_03  the rate file round trip: the category's own download previews against the live data as
             ZERO changes (the derived cells read as untouched).
"""
import copy
import json
import os
import re

import frappe
from frappe.tests.utils import FrappeTestCase

from nirmaan_stack.api.boq import rate_master
from nirmaan_stack.services.boq_rate_master import config_validation, extraction, loader

V33 = "rate_master_hvac_all_v33.json"
V34 = "rate_master_hvac_all_v34.json"
V35 = "rate_master_hvac_all_v35.json"   # 12e-1b: v34 + item_name on the 40 Piping items (+ its definition, first)
KIND = "hvac_piping_item"
CATEGORY = "hvac_piping"

# 12e-1b: the sheet's column A ("Item"), read 2026-10-10 from the same workbook: no merged cell, no blank, no trailing
# space; FOUR distinct texts, one per family, in sheet order. Rows 2-14 copper, 15-27 MS, 28-35 PVC, 36-41 CPVC.
SHEET_ITEM_TEXTS = ["Refrigerant Piping/Copper Piping", "Chilled Water Piping / MS Piping", "PVC Pipe", "CPVC Pipe"]
SHEET_ITEM_BY_ROW = {}
for _row in range(2, 42):
    SHEET_ITEM_BY_ROW[_row] = SHEET_ITEM_TEXTS[0 if _row <= 14 else 1 if _row <= 27 else 2 if _row <= 35 else 3]
ITEM_NAME_DEFINITION = {"id": "item_name", "label": "Item", "type": "choice", "values": SHEET_ITEM_TEXTS}

# The owner's workbook, sheet "Piping", read 2026-10-09 (HVAC_BOQ_BCS PRICING_ Nitesh Edits v3.xlsx, mtime
# 2026-10-08 21:40): (pipe_type, size_mm, Total BCS Supply, BCS Installation, supply markup, install markup).
SHEET = [
    ("Copper", 47.6, 3120.0, 110.0, 0.5, 1.0), ("Copper", 41.3, 2795.0, 110.0, 0.5, 1.0), ("Copper", 38.1, 2587.0, 110.0, 0.5, 1.0),
    ("Copper", 34.9, 2382.0, 110.0, 0.5, 1.0), ("Copper", 31.7, 1950.0, 110.0, 0.5, 1.0), ("Copper", 28.6, 1625.0, 110.0, 0.5, 1.0),
    ("Copper", 25.4, 1495.0, 110.0, 0.5, 1.0), ("Copper", 22.2, 1209.0, 110.0, 0.5, 1.0), ("Copper", 19.1, 1060.0, 110.0, 0.5, 1.0),
    ("Copper", 15.9, 865.0, 110.0, 0.5, 1.0), ("Copper", 12.7, 624.0, 110.0, 0.5, 1.0), ("Copper", 9.5, 286.0, 110.0, 0.5, 1.0),
    ("Copper", 6.4, 260.0, 110.0, 0.5, 1.0),
    ("MS", 300.0, 4480.0, 1200.0, 0.5, 0.4), ("MS", 250.0, 3744.0, 1000.0, 0.5, 0.4), ("MS", 200.0, 3200.0, 800.0, 0.5, 0.4),
    ("MS", 150.0, 2240.0, 600.0, 0.5, 0.4), ("MS", 125.0, 2080.0, 500.0, 0.5, 0.4), ("MS", 100.0, 1504.0, 400.0, 0.5, 0.4),
    ("MS", 80.0, 960.0, 300.0, 0.5, 0.4), ("MS", 65.0, 800.0, 250.0, 0.5, 0.4), ("MS", 50.0, 656.0, 200.0, 0.5, 0.4),
    ("MS", 40.0, 480.0, 150.0, 0.5, 0.4), ("MS", 32.0, 400.0, 125.0, 0.5, 0.4), ("MS", 25.0, 320.0, 100.0, 0.5, 0.4),
    ("MS", 19.0, 304.0, 80.0, 0.5, 0.4),
    ("PVC", 150.0, 808.0, 120.0, 0.5, 0.4), ("PVC", 100.0, 352.0, 100.0, 0.5, 0.4), ("PVC", 75.0, 200.0, 80.0, 0.5, 0.4),
    ("PVC", 65.0, 176.0, 60.0, 0.5, 0.4), ("PVC", 50.0, 168.0, 40.0, 0.5, 0.4), ("PVC", 40.0, 144.0, 30.0, 0.5, 0.4),
    ("PVC", 32.0, 112.0, 20.0, 0.5, 0.4), ("PVC", 25.0, 80.0, 20.0, 0.5, 0.4),
    ("CPVC", 75.0, 512.0, 80.0, 0.5, 0.4), ("CPVC", 65.0, 448.0, 60.0, 0.5, 0.4), ("CPVC", 50.0, 384.0, 40.0, 0.5, 0.4),
    ("CPVC", 40.0, 336.0, 30.0, 0.5, 0.4), ("CPVC", 32.0, 272.0, 20.0, 0.5, 0.4), ("CPVC", 25.0, 160.0, 20.0, 0.5, 0.4),
]
FAMILY_COUNTS = {"Copper": 13, "MS": 13, "PVC": 8, "CPVC": 6}


def _asset_path(filename):
    return os.path.join(os.path.dirname(loader.__file__), "data", filename)


def _read(filename):
    with open(_asset_path(filename), "r", encoding="utf-8") as fh:
        return json.load(fh)


def _norm(obj):
    return json.dumps(obj, sort_keys=True, default=str)


def _piping(asset):
    return [it for it in asset["items"] if it["kind"] == KIND]


def _by_key(items):
    return {(it["attributes"]["pipe_type"], float(it["attributes"]["size_mm"])): it for it in items}


class TestSlice12e1AssetV34(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.v33 = _read(V33)
        cls.v34 = _read(V34)
        cls.v35 = _read(V35)   # 12e-1b: the CURRENT asset; v34 stays read for the v34 -> v35 comparison
        cls.cfg = next(c for c in cls.v35["category_configs"] if c["category_id"] == CATEGORY)

    def test_01_v34_is_v33_plus_piping_and_nothing_else(self):
        # 12e-1b: the current asset is v35 = v34 + item_name; this pin stays the record of the v33 -> v34 mint,
        # so v35 is compared to v34 with the ONE key and the ONE definition normalised (never deleted), and
        # then v35's non-Piping content to v33 exactly as before.
        a34 = {it["item_uid"]: _norm(it) for it in self.v34["items"]}
        b35 = {}
        for it in self.v35["items"]:
            it = copy.deepcopy(it)
            if it["kind"] == KIND:
                self.assertIn("item_name", it["attributes"], "12e-1b: every Piping item carries item_name")
                del it["attributes"]["item_name"]
            b35[it["item_uid"]] = _norm(it)
        self.assertEqual(a34, b35, "v35 minus item_name == v34, item by item, both directions")
        c34 = {c["category_id"]: _norm(c) for c in self.v34["category_configs"]}
        c35 = {}
        for c in self.v35["category_configs"]:
            c = copy.deepcopy(c)
            if c["category_id"] == CATEGORY:
                self.assertEqual(c["attribute_definitions"][0]["id"], "item_name", "12e-1b: the name definition is FIRST")
                c["attribute_definitions"] = c["attribute_definitions"][1:]
            c35[c["category_id"]] = _norm(c)
        self.assertEqual(c34, c35, "v35 minus the item_name definition == v34, config by config")
        for k in set(self.v34) | set(self.v35):
            if k in ("items", "category_configs"):
                continue
            self.assertEqual(_norm(self.v34.get(k)), _norm(self.v35.get(k)), "top-level key %r unchanged v34 -> v35" % k)
        # the 12e-1 record: the current asset is v33 + Piping and nothing else
        a = {it["item_uid"]: _norm(it) for it in self.v33["items"]}
        b = {it["item_uid"]: _norm(it) for it in self.v35["items"] if it["kind"] != KIND}
        self.assertEqual(sorted(a), sorted(b), "every non-Piping uid of v34 is a v33 uid and vice versa")
        self.assertEqual([u for u in a if a[u] != b[u]], [], "every v33 item is carried byte-equal")
        self.assertEqual(len(self.v33["items"]), 335)
        self.assertEqual(len(self.v35["items"]), 375)
        self.assertFalse(any(it["kind"] == KIND for it in self.v33["items"]), "v33 has no Piping item")
        ca = {c["category_id"]: _norm(c) for c in self.v33["category_configs"]}
        cb = {c["category_id"]: _norm(c) for c in self.v35["category_configs"] if c["category_id"] != CATEGORY}
        self.assertEqual(ca, cb, "the nine v33 configs are carried byte-equal; only hvac_piping is new")
        self.assertEqual(len(self.v35["category_configs"]), 10)
        for k in set(self.v33) | set(self.v35):
            if k in ("items", "category_configs"):
                continue
            self.assertEqual(_norm(self.v33.get(k)), _norm(self.v35.get(k)), "top-level key %r unchanged" % k)

    def test_02_the_forty_items_are_named_and_carry_the_sheets_four_figures(self):
        items = _piping(self.v35)
        self.assertEqual(len(items), 40)
        by = _by_key(items)
        self.assertEqual(len(by), 40, "no two items share (family, size)")
        counts = {}
        for fam, size, sup, inst, sm, im in SHEET:
            it = by.get((fam, size))
            self.assertIsNotNone(it, "%s %s is in the asset" % (fam, size))
            self.assertEqual(it["rates"], {"cost_supply": sup, "cost_install": inst, "supply_markup": sm, "install_markup": im},
                             "%s %s carries the sheet's four figures" % (fam, size))
            self.assertEqual(it["unit"], "Mts")
            self.assertIsNone(it["brand"])
            self.assertEqual(it["source"]["sheet"], "Piping")
            self.assertTrue(2 <= it["source"]["row"] <= 41)
            self.assertEqual(sorted(it["attributes"]), ["item_name", "pipe_type", "size_mm"], "no inch attribute, nothing beyond name + type + size (12e-1b: + item_name)")
            self.assertRegex(it["item_uid"], r"^rmi-[0-9a-f]{12}$")
            counts[fam] = counts.get(fam, 0) + 1
        self.assertEqual(counts, FAMILY_COUNTS)
        self.assertEqual(len({it["item_uid"] for it in items}), 40, "uids unique")
        self.assertEqual(len({it["item_uid"] for it in self.v35["items"]}), 375, "unique across the whole asset")
        # the rulings, by name
        self.assertTrue(all(by[("Copper", s)]["rates"]["cost_install"] == 110.0 for s in (6.4, 9.5, 12.7, 15.9, 19.1, 22.2, 25.4, 28.6, 31.7, 34.9, 38.1, 41.3, 47.6)))
        c317 = by[("Copper", 31.7)]["rates"]
        self.assertEqual(c317["cost_install"] * (1 + c317["install_markup"]), 220.0, "copper 31.7 install = 220 (owner), from the sheet's own 110 x (1 + 1.0)")
        self.assertEqual(by[("Copper", 31.7)]["rates"]["cost_supply"], 1950.0)

    def test_03_the_two_ms_links_are_live_declarations_on_both_cost_columns(self):
        by = _by_key(_piping(self.v35))
        uid = lambda size: by[("MS", size)]["item_uid"]
        dr = self.cfg["derived_rates"]
        self.assertEqual(sorted(dr), sorted([uid(300.0), uid(250.0)]), "exactly the two MS rows are derived")
        for key in ("cost_supply", "cost_install"):
            self.assertEqual(dr[uid(300.0)][key], [{"from": {"item_uid": uid(150.0), "rate_key": key}, "multiplier": 2.0, "constant": 0.0}])
            self.assertEqual(dr[uid(250.0)][key], [{"from": {"item_uid": uid(150.0), "rate_key": key}, "multiplier": 1.0, "constant": 0.0},
                                                   {"from": {"item_uid": uid(100.0), "rate_key": key}, "multiplier": 1.0, "constant": 0.0}])
        # the stored figures already satisfy the links -- the loader's post-load check would refuse otherwise
        by_uid = {it["item_uid"]: {"rates": it["rates"]} for it in self.v35["items"]}
        self.assertEqual(config_validation.derived_rate_updates([self.cfg], by_uid), {})
        want = config_validation.recompute_derived_values([self.cfg], by_uid)
        self.assertEqual(want[(uid(300.0), "cost_supply")], 4480.0)
        self.assertEqual(want[(uid(300.0), "cost_install")], 1200.0)
        self.assertEqual(want[(uid(250.0), "cost_supply")], 3744.0)
        self.assertEqual(want[(uid(250.0), "cost_install")], 1000.0)
        config_validation._validate_derived_rates(self.cfg)   # flattened, acyclic, well-shaped

    def test_04_the_config_is_data_only_and_not_eligible(self):
        self.assertEqual(self.cfg["item_kinds"], [KIND])
        self.assertEqual(self.cfg["pipelines"], {})
        self.assertNotIn("list_spec", self.cfg)
        self.assertEqual([d["id"] for d in self.cfg["attribute_definitions"]], ["item_name", "pipe_type", "size_mm"])   # 12e-1b: the name, FIRST
        self.assertEqual(self.cfg["attribute_definitions"][1]["values"], ["Copper", "MS", "PVC", "CPVC"])
        sizes = sorted({float(it["attributes"]["size_mm"]) for it in _piping(self.v35)})
        self.assertEqual(self.cfg["attribute_definitions"][2]["values"], sizes, "the size vocabulary is exactly the 27 stocked sizes")
        self.assertFalse(extraction.has_runnable_pricing_rules(self.cfg))
        configs = {c["category_id"]: c for c in self.v35["category_configs"]}
        self.assertFalse(extraction.config_is_eligible(self.cfg, configs), "never priced on a BoQ row, never extracted")
        config_validation._validate_config(dict(self.cfg, discipline="HVAC"))
        self.assertNotIn("helper_message", self.cfg, "no message of its own: the panel shows the generic coming-soon card")

    def test_05_NEGATIVE_an_unflattened_or_dangling_link_is_refused(self):
        by = _by_key(_piping(self.v35))
        uid = lambda size: by[("MS", size)]["item_uid"]
        bad = copy.deepcopy(self.cfg)
        # MS 250 reading MS 300 (itself derived) -- not flattened
        bad["derived_rates"][uid(250.0)]["cost_supply"] = [{"from": {"item_uid": uid(300.0), "rate_key": "cost_supply"}, "multiplier": 0.5, "constant": 0.0}]
        with self.assertRaises(frappe.ValidationError):
            config_validation._validate_derived_rates(bad)
        # a link to a base that does not exist
        dangling = copy.deepcopy(self.cfg)
        dangling["derived_rates"][uid(300.0)]["cost_supply"] = [{"from": {"item_uid": "rmi-000000000000", "rate_key": "cost_supply"}, "multiplier": 2.0, "constant": 0.0}]
        by_uid = {it["item_uid"]: {"rates": it["rates"]} for it in self.v35["items"]}
        with self.assertRaises(config_validation.DerivedRateError):
            config_validation.recompute_derived_values([dangling], by_uid)

    def test_06_v34_is_the_newest_hvac_asset_on_disk(self):
        # 12e-1b: INVERTED under mechanical authority -- v35 (v34 + item_name) is now the newest; v34 stays on disk
        d = os.path.dirname(_asset_path(V35))
        ns = [int(m.group(1)) for f in os.listdir(d) for m in [re.match(r"rate_master_hvac_all_v(\d+)\.json$", f)] if m]
        self.assertNotEqual(max(ns), 34, "12e-1b: v34 is no longer the newest")
        self.assertEqual(max(ns), 35)
        self.assertTrue(os.path.exists(_asset_path(V34)), "v34 stays on disk as the 12e-1 record")
        self.assertFalse(os.path.exists(_asset_path("rate_master_hvac_all_v%d.json" % (max(ns) + 1))))

    @staticmethod
    def _check_piping_names(items, cfg):
        """THE ASSET CHECK (12e-1b): every Piping item carries `attributes.item_name`, non-blank, equal to its sheet
        row's column A text, and one of the four sheet texts; the config declares `item_name` FIRST as a plain
        choice over exactly those texts in sheet order, with no spec flag. Raises AssertionError otherwise."""
        pip = [it for it in items if it["kind"] == KIND]
        assert len(pip) == 40, "40 Piping items, found %d" % len(pip)
        for it in pip:
            name = it["attributes"].get("item_name")
            assert isinstance(name, str) and name.strip(), "Piping item %s has no item_name" % it["item_uid"]
            assert name in SHEET_ITEM_TEXTS, "Piping item %s carries a name that is not on the sheet: %r" % (it["item_uid"], name)
            assert name == SHEET_ITEM_BY_ROW[it["source"]["row"]], "Piping item %s (row %d): %r is not that row's column A" % (
                it["item_uid"], it["source"]["row"], name)
            assert list(it["attributes"].keys())[0] == "item_name", "item_name is the first attribute key on %s" % it["item_uid"]
        d = cfg["attribute_definitions"][0]
        assert {k: d[k] for k in ("id", "label", "type", "values")} == ITEM_NAME_DEFINITION, "the first definition is the Item choice: %r" % d
        assert "selector" not in d and "panel" not in d, "a plain attribute like Insulation's `type`: no selector / panel flag"
        assert cfg.get("attributes_from_spec") is not True, "never a spec-read category"
        return True

    def test_07_every_piping_item_carries_its_sheet_name_verbatim_and_a_nameless_or_foreign_name_is_refused(self):
        # POSITIVE: the committed v35 passes the check; the 40 names are the sheet's column A, row by row
        self.assertTrue(self._check_piping_names(self.v35["items"], self.cfg))
        names = sorted({it["attributes"]["item_name"] for it in _piping(self.v35)}, key=SHEET_ITEM_TEXTS.index)
        self.assertEqual(names, SHEET_ITEM_TEXTS)
        counts = {t: sum(1 for it in _piping(self.v35) if it["attributes"]["item_name"] == t) for t in SHEET_ITEM_TEXTS}
        self.assertEqual(list(counts.values()), [13, 13, 8, 6])
        self.assertEqual(self.cfg["attribute_definitions"][0]["label"], "Item", "the sheet's own header")
        # v34 did NOT carry the key (the thing 12e-1b adds), and the check says so
        with self.assertRaises(AssertionError):
            self._check_piping_names(self.v34["items"], next(c for c in self.v34["category_configs"] if c["category_id"] == CATEGORY))
        # NEGATIVE: a Piping item with a MISSING name is refused
        items = copy.deepcopy(self.v35["items"])
        victim = next(it for it in items if it["kind"] == KIND)
        del victim["attributes"]["item_name"]
        with self.assertRaises(AssertionError):
            self._check_piping_names(items, self.cfg)
        # NEGATIVE: a BLANK name is refused
        items = copy.deepcopy(self.v35["items"])
        next(it for it in items if it["kind"] == KIND)["attributes"]["item_name"] = "   "
        with self.assertRaises(AssertionError):
            self._check_piping_names(items, self.cfg)
        # NEGATIVE: a FOREIGN name (not on the sheet) is refused, as is a sheet text on the wrong row
        items = copy.deepcopy(self.v35["items"])
        next(it for it in items if it["kind"] == KIND)["attributes"]["item_name"] = "Copper pipe"
        with self.assertRaises(AssertionError):
            self._check_piping_names(items, self.cfg)
        items = copy.deepcopy(self.v35["items"])
        row2 = next(it for it in items if it["kind"] == KIND and it["source"]["row"] == 2)
        row2["attributes"]["item_name"] = "PVC Pipe"
        with self.assertRaises(AssertionError):
            self._check_piping_names(items, self.cfg)
        # NEGATIVE: a config that does not declare the name first, or declares it spec-read, is refused
        cfg = copy.deepcopy(self.cfg)
        cfg["attribute_definitions"] = cfg["attribute_definitions"][1:] + cfg["attribute_definitions"][:1]
        with self.assertRaises(AssertionError):
            self._check_piping_names(self.v35["items"], cfg)
        cfg = copy.deepcopy(self.cfg)
        cfg["attributes_from_spec"] = True
        with self.assertRaises(AssertionError):
            self._check_piping_names(self.v35["items"], cfg)


class TestSlice12e1LiveLinks(FrappeTestCase):
    """LIVE site, after `loader.load_rate_master(v35, replace=True)` (12e-1b; v34 before it). Every write is restored."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        rows = frappe.get_all("BoQ Rate Master Item", filters={"discipline": "HVAC", "kind": KIND, "active": 1},
                              fields=["name", "item_uid", "attributes", "rates"])
        cls.live = {}
        for r in rows:
            a = r["attributes"] if isinstance(r["attributes"], dict) else json.loads(r["attributes"] or "{}")
            rt = r["rates"] if isinstance(r["rates"], dict) else json.loads(r["rates"] or "{}")
            cls.live[(a.get("pipe_type"), float(a.get("size_mm")))] = {"name": r["name"], "uid": r["item_uid"], "rates": rt}
        if len(cls.live) != 40:
            raise AssertionError("the LIVE site does not carry the 40 Piping items (found %d) -- load v35 first" % len(cls.live))

    @staticmethod
    def _rates(uid):
        r = frappe.get_all("BoQ Rate Master Item", filters={"discipline": "HVAC", "item_uid": uid, "active": 1}, fields=["name", "rates"])
        assert len(r) == 1, "exactly one active row per uid: %s" % uid
        rt = r[0]["rates"]
        return r[0]["name"], (rt if isinstance(rt, dict) else json.loads(rt or "{}"))

    def test_live_01_the_grid_write_path_moves_ms_300_by_twice_and_ms_250_by_once_and_restores(self):
        ms150, ms100, ms300, ms250 = (self.live[("MS", s)] for s in (150.0, 100.0, 300.0, 250.0))
        base = self._rates(ms150["uid"])[1]["cost_supply"]
        before300 = self._rates(ms300["uid"])[1]["cost_supply"]
        before250 = self._rates(ms250["uid"])[1]["cost_supply"]
        self.assertEqual(before300, 2 * base)
        self.assertEqual(before250, base + self._rates(ms100["uid"])[1]["cost_supply"])

        def restore():
            name, _ = self._rates(ms150["uid"])
            rate_master.update_rate_master_item(name=name, rates_patch=json.dumps({"cost_supply": base}))
            frappe.db.commit()
        self.addCleanup(restore)

        name, _ = self._rates(ms150["uid"])
        out = rate_master.update_rate_master_item(name=name, rates_patch=json.dumps({"cost_supply": base + 10}))   # the grid's write
        frappe.db.commit()
        self.assertTrue(out.get("ok"))
        self.assertEqual(self._rates(ms150["uid"])[1]["cost_supply"], base + 10)
        self.assertEqual(self._rates(ms300["uid"])[1]["cost_supply"], before300 + 20, "MS 300 follows +20")
        self.assertEqual(self._rates(ms250["uid"])[1]["cost_supply"], before250 + 10, "MS 250 follows +10")
        self.assertEqual(self._rates(ms300["uid"])[1]["cost_install"], 1200.0, "install untouched by a supply edit")
        restore()
        self.assertEqual(self._rates(ms150["uid"])[1]["cost_supply"], base)
        self.assertEqual(self._rates(ms300["uid"])[1]["cost_supply"], before300, "MS 300 back")
        self.assertEqual(self._rates(ms250["uid"])[1]["cost_supply"], before250, "MS 250 back")

    def test_live_02_the_served_payload_carries_the_forty_rows_with_the_sheets_figures(self):
        served = rate_master.get_rate_master_items(discipline="HVAC", kind=KIND)
        self.assertEqual(served["count"], 40)
        by = {(it["attributes"]["pipe_type"], float(it["attributes"]["size_mm"])): it for it in served["items"]}
        for fam, size, sup, inst, sm, im in SHEET:
            self.assertEqual(by[(fam, size)]["rates"], {"cost_supply": sup, "cost_install": inst, "supply_markup": sm, "install_markup": im})
            self.assertEqual(by[(fam, size)]["unit"], "Mts")
        # `computed_rates` is the cladding DISPLAY projection only (12d-2F); a Piping derived cell is a STORED figure the
        # loader / write paths keep in step, so no Piping uid is projected -- the grid marks it from the config's
        # derived_rates instead
        piping_uids = {it["item_uid"] for it in served["items"]}
        self.assertEqual([u for u in served["computed_rate_keys"] if u in piping_uids], [])
        cfg = rate_master.get_rate_category_config(discipline="HVAC", category_id=CATEGORY)["config"]
        self.assertEqual(sorted(cfg["derived_rates"]), sorted([by[("MS", 300.0)]["item_uid"], by[("MS", 250.0)]["item_uid"]]))

    def test_live_03_the_categorys_rate_file_previews_as_zero_changes(self):
        export = rate_master.export_rate_master_csv(discipline="HVAC", category_id=CATEGORY, fmt="csv")
        self.assertEqual(export["row_count"], 40)
        plan = rate_master.preview_rate_master_csv(discipline="HVAC", content_base64=export["content_base64"], category_id=CATEGORY)
        self.assertEqual(plan["errors"], [])
        counts = plan["counts"]
        self.assertEqual((counts.get("rates_changed", 0), counts.get("items_added", 0), counts.get("other_changed", 0)), (0, 0, 0))
        self.assertEqual(counts.get("unchanged"), 40)
