"""CAT-1 (2026-11-26) -- THE CATALOGUE LISTS: rebuilt from the catalogue, stamped, merged at both read points, wording placeholders
filled (`catalogue_lists.py`; owner 2026-11-24 18:42 - 19:38, 2026-11-26 00:06 / 00:10). Every check has a NEGATIVE half.

  T1  the rebuild on v88 (+ the On-Off declaration) equals today's list for every class-(a) question; without the declaration exactly
      the Valve `operation` list moves (NEGATIVE); a SKU added with a new value -> offered, a value's last SKU removed -> gone, the config
      order kept, the leading-space Insulation family kept; a NEW category (a Valve clone on its own kind) is covered with no code change.
  T2  the stamp: CAT-D0 D3b's seven cases move / do not move exactly as designed.
  T3  the merge + fill: a placeholder is filled exactly (|lower, |trim, {{item:}} by uid, a renamed SKU shows its new name), an
      unresolvable one prints no braces and is reported; LIVE: every served HVAC config (both read points) equals the stored config,
      no "{{" reaches any served config, every request built through the read point equals the one built from the raw configs; the
      two live catalogue reads are pinned to `modified desc, name asc`.
  T6  G4 stamp freshness: a write that commits re-caches the fresh stamp (and a rolled-back one does not); a raw-SQL attribute edit
      makes the next read rebuild, a raw-SQL rate edit does not move the stamp; every app write route reaches a rebuild choke point.
Run: bench --site localhost run-tests --module nirmaan_stack.services.boq_rate_master.test_catalogue_lists
"""
import copy
import inspect
import json
import os
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from nirmaan_stack.services.boq_rate_master import catalogue_lists as CL
from nirmaan_stack.services.boq_rate_master import csv_importer, extraction, loader

DATA = os.path.join(os.path.dirname(loader.__file__), "data")
V88 = "rate_master_hvac_all_v88.json"
VALVE = "hvac_valve_package"
DECL = {"operation": ["On-Off"]}


def _asset(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as fh:
        return json.load(fh)


def _declared(asset):
    a = copy.deepcopy(asset)
    for c in a["category_configs"]:
        c["discipline"] = a["discipline"]
        if c["category_id"] == VALVE:
            c[CL.UNSTOCKED_KEY] = copy.deepcopy(DECL)
    return a


def _items(asset):
    return [dict(i, active=1) for i in asset["items"]]


def _defs(cfg):
    ls = cfg.get("list_spec")
    return ls["attribute_definitions"] if isinstance(ls, dict) else cfg["attribute_definitions"]


def _def(cfg, qid):
    return next(d for d in _defs(cfg) if d.get("id") == qid)


class TestT1Rebuild(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.A = _declared(_asset(V88))
        cls.built = CL.build(_items(cls.A), cls.A["category_configs"])

    def test_t1_01_rebuild_equals_today_every_config(self):
        moved = [c["category_id"] for c in self.A["category_configs"] if CL.merge_config(c, self.built, "HVAC") is not c]
        self.assertEqual(moved, [])
        klass = {}
        for rb in self.built["lists"].values():
            for r in rb.values():
                klass[r["klass"]] = klass.get(r["klass"], 0) + 1
        # CAT-D0 D1 (re-measured on v88): 9 family questions, 20 attribute questions, 46 class (b)
        self.assertEqual(klass, {"A-FAMILY": 9, "A-ATTRIBUTE": 20, "B": 46})

    def test_t1_02_negative_without_the_declaration_only_on_off_moves(self):
        a = copy.deepcopy(self.A)
        for c in a["category_configs"]:
            c.pop(CL.UNSTOCKED_KEY, None)
        built = CL.build(_items(a), a["category_configs"])
        moved = {c["category_id"]: CL.merge_config(c, built, "HVAC") for c in a["category_configs"]}
        moved = {k: v for k, v in moved.items() if v is not next(c for c in a["category_configs"] if c["category_id"] == k)}
        self.assertEqual(sorted(moved), [VALVE])
        self.assertEqual(_def(moved[VALVE], "operation")["values"], ["Modulating"])
        self.assertEqual(_def(next(c for c in a["category_configs"] if c["category_id"] == VALVE), "operation")["values"],
                         ["On-Off", "Modulating"])

    def test_t1_03_a_sku_added_with_a_new_value_is_offered(self):
        a = copy.deepcopy(self.A)
        cfg = next(c for c in a["category_configs"] if c["category_id"] == VALVE)
        donor = next(i for i in a["items"] if i["kind"] == cfg["list_spec"]["pricing"]["kind"] and i["attributes"].get("nrv_type"))
        new = copy.deepcopy(donor)
        new["item_uid"] = "rmi-cat1-test-new"
        new["attributes"]["nrv_type"] = "CAT1 Triple Plate"
        a["items"].append(new)
        before = list(_def(cfg, "nrv_type")["values"])
        merged = CL.merge_config(cfg, CL.build(_items(a), a["category_configs"]), "HVAC")
        after = _def(merged, "nrv_type")["values"]
        self.assertIn("CAT1 Triple Plate", after)
        self.assertNotIn("CAT1 Triple Plate", before)
        # the config's own order kept for every surviving value
        self.assertEqual([v for v in after if v in before], before)

    def test_t1_04_a_values_last_sku_removed_is_gone(self):
        a = copy.deepcopy(self.A)
        cfg = next(c for c in a["category_configs"] if c["category_id"] == VALVE)
        vals = _def(cfg, "nrv_type")["values"]
        gone = next(v for v in vals if v not in CL.declared_placeholders(cfg, "nrv_type"))
        a["items"] = [i for i in a["items"] if i["attributes"].get("nrv_type") != gone]
        merged = CL.merge_config(cfg, CL.build(_items(a), a["category_configs"]), "HVAC")
        self.assertNotIn(gone, _def(merged, "nrv_type")["values"])
        self.assertIn(gone, vals)

    def test_t1_05_the_leading_space_family_is_kept_exactly(self):
        ins = next(c for c in self.A["category_configs"] if c["category_id"] == "hvac_insulation")
        fam = ins["list_spec"]["family_attribute_id"]
        spaced = [v for v in _def(ins, fam)["values"] if isinstance(v, str) and v != v.lstrip()]
        self.assertTrue(spaced, "v88 Insulation carries a family written with a leading space")
        self.assertEqual(self.built["lists"]["hvac_insulation"][fam]["values"], _def(ins, fam)["values"])

    def test_t1_06_a_new_category_clone_is_covered_with_no_code_change(self):
        a = copy.deepcopy(self.A)
        src = next(c for c in a["category_configs"] if c["category_id"] == VALVE)
        clone = copy.deepcopy(src)
        clone["category_id"] = "hvac_cat1_valve_clone"
        kind = src["list_spec"]["pricing"]["kind"]
        clone["list_spec"]["pricing"]["kind"] = "hvac_cat1_clone_item"
        clone["list_spec"]["pricing"]["extra_kinds"] = []
        for i in [i for i in a["items"] if i["kind"] == kind]:
            j = copy.deepcopy(i)
            j["kind"], j["item_uid"] = "hvac_cat1_clone_item", "clone-" + str(i.get("item_uid"))
            a["items"].append(j)
        a["category_configs"].append(clone)
        built = CL.build(_items(a), a["category_configs"])
        self.assertIn("hvac_cat1_valve_clone", built["lists"])
        fam = clone["list_spec"]["family_attribute_id"]
        self.assertEqual(built["lists"]["hvac_cat1_valve_clone"][fam]["klass"], "A-FAMILY")
        # one of the clone's families loses its every SKU -> it leaves the clone's list, and only the clone's
        f = next(v for v in _def(clone, fam)["values"] if v not in CL.declared_placeholders(clone, fam))
        a["items"] = [i for i in a["items"] if not (i["kind"] == "hvac_cat1_clone_item" and i["attributes"].get(fam) == f)]
        built2 = CL.build(_items(a), a["category_configs"])
        self.assertNotIn(f, built2["lists"]["hvac_cat1_valve_clone"][fam]["values"])
        self.assertIn(f, built2["lists"][VALVE][fam]["values"])


class TestT2Stamp(FrappeTestCase):
    """CAT-D0 D3b's seven cases."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.A = _declared(_asset(V88))
        cls.items = _items(cls.A)
        cls.cfgs = cls.A["category_configs"]
        cls.base = CL.compute_stamp(cls.items, cls.cfgs)

    def _s(self, items=None, cfgs=None):
        return CL.compute_stamp(items if items is not None else self.items, cfgs if cfgs is not None else self.cfgs)

    def test_t2_1_add_a_sku_moves(self):
        it = copy.deepcopy(self.items[0]); it["item_uid"] = "rmi-x"; it["attributes"]["cat1"] = "new"
        self.assertNotEqual(self._s(self.items + [it]), self.base)

    def test_t2_2_remove_a_sku_moves(self):
        self.assertNotEqual(self._s(self.items[1:]), self.base)

    def test_t2_3_attribute_edit_moves(self):
        items = copy.deepcopy(self.items); items[5]["attributes"]["cat1"] = "edited"
        self.assertNotEqual(self._s(items), self.base)

    def test_t2_4_app_edit_of_a_choice_value_moves(self):
        items = copy.deepcopy(self.items)
        k = next(k for k, v in items[7]["attributes"].items() if isinstance(v, str))
        items[7]["attributes"][k] = items[7]["attributes"][k] + " (edited)"
        self.assertNotEqual(self._s(items), self.base)

    def test_t2_5_rate_only_edit_does_not_move(self):
        items = copy.deepcopy(self.items)
        items[3]["rates"] = {k: (v * 2 if isinstance(v, (int, float)) else v) for k, v in (items[3].get("rates") or {}).items()}
        items[3]["item_uid"] = "rmi-renamed-uid"
        self.assertEqual(self._s(items), self.base)

    def test_t2_6_same_content_reinsert_does_not_move(self):
        items = copy.deepcopy(self.items)
        items.append(items.pop(0))           # a superseded + re-inserted row: same content, new position / name
        self.assertEqual(self._s(items), self.base)

    def test_t2_7_config_list_reordered_moves(self):
        cfgs = copy.deepcopy(self.cfgs)
        d = _def(next(c for c in cfgs if c["category_id"] == VALVE), "operation")
        d["values"] = list(reversed(d["values"]))
        self.assertNotEqual(self._s(cfgs=cfgs), self.base)


class TestT3Fill(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.A = _declared(_asset(V88))
        cls.built = CL.build(_items(cls.A), cls.A["category_configs"])
        cls.share_uid = "rmi-51319c433867"   # the DDC panel SKU (v88)

    def test_t3_01_cat_placeholder_exact_lower_trim(self):
        v = "Dual Plate"
        self.assertIn(v, self.built["values"]["nrv_type"])
        self.assertEqual(CL.fill_text("a {{cat:nrv_type=Dual Plate}} NRV", self.built), "a Dual Plate NRV")
        self.assertEqual(CL.fill_text("a {{cat:nrv_type=Dual Plate|lower}} NRV", self.built), "a dual plate NRV")
        spaced = next(x for vals in self.built["values"].values() for x in vals if isinstance(x, str) and x != x.lstrip())
        attr = next(k for k, vals in self.built["values"].items() if spaced in vals)
        self.assertEqual(CL.fill_text("{{cat:%s=%s|trim}}" % (attr, spaced), self.built), spaced.strip())
        self.assertEqual(CL.fill_text("{{cat:%s=%s}}" % (attr, spaced), self.built), spaced)   # never stripped unless asked

    def test_t3_02_item_placeholder_reads_the_live_name_and_follows_a_rename(self):
        self.assertEqual(CL.fill_text("the {{item:%s:vav_item}} SKU" % self.share_uid, self.built), "the DDC Panel/ Controller SKU")
        a = copy.deepcopy(self.A)
        for i in a["items"]:
            if i.get("item_uid") == self.share_uid:
                i["attributes"]["vav_item"] = "DDC Panel / Controller (renamed)"
        built = CL.build(_items(a), a["category_configs"])
        self.assertEqual(CL.fill_text("the {{item:%s:vav_item}} SKU" % self.share_uid, built), "the DDC Panel / Controller (renamed) SKU")

    def test_t3_03_negative_unresolvable_prints_no_braces_and_is_reported(self):
        probs = []
        out = CL.fill_text("x {{cat:nrv_type=CAT1 Gone}} y {{item:rmi-nope}} z {{cat:bad}}", self.built, probs, "w")
        self.assertNotIn("{{", out)
        self.assertEqual(len(probs), 3)
        self.assertIn("CAT1 Gone", out)
        self.assertIn(CL.UNRESOLVED_ITEM_TEXT, out)

    def test_t3_04_a_placeholder_config_is_served_filled(self):
        cfg = copy.deepcopy(next(c for c in self.A["category_configs"] if c["category_id"] == VALVE))
        cfg["notes"] = "Read {{cat:nrv_type=Dual Plate|lower}} as written."
        merged = CL.merge_config(cfg, self.built, "HVAC")
        self.assertEqual(merged["notes"], "Read dual plate as written.")
        self.assertNotIn("{{", json.dumps(merged, ensure_ascii=False))
        self.assertIn("{{", cfg["notes"])     # the stored config is never touched

    def test_t3_05_live_both_read_points_serve_the_stored_configs(self):
        from nirmaan_stack.api.boq import rate_master
        raw = {(r.discipline, r.category_id): (json.loads(r.config) if isinstance(r.config, str) else r.config)
               for r in frappe.get_all("BoQ Rate Category Config", filters={"active": 1}, fields=["discipline", "category_id", "config"])}
        served = extraction._load_active_configs()
        self.assertEqual(sorted(served), sorted(raw))
        for k, cfg in raw.items():
            self.assertEqual(served[k], cfg, k)
            self.assertNotIn("{{", json.dumps(served[k], ensure_ascii=False), k)
        for (d, cid), cfg in raw.items():
            if d != "HVAC":
                continue
            row = rate_master.get_rate_category_config(discipline=d, category_id=cid)
            self.assertEqual(row["config"], cfg, cid)

    def test_t3_06_live_requests_through_the_read_point_equal_the_raw_build(self):
        raw = {(r.discipline, r.category_id): (json.loads(r.config) if isinstance(r.config, str) else r.config)
               for r in frappe.get_all("BoQ Rate Category Config", filters={"active": 1}, fields=["discipline", "category_id", "config"])}
        served = extraction._load_active_configs()

        def req(cfgs, k):
            ctx = extraction._group_context(cfgs, *k)
            return extraction.batch_prompt_content(ctx["prompt"], ctx["defs"], [], synonyms=ctx["synonyms"], defaults=ctx["defaults"],
                                                   none_guidance=ctx["none_guidance"], slot_spec=ctx["slot_spec"],
                                                   resolution_rules=ctx["resolution_rules"], rules=ctx["rules"], items_spec=ctx["items_spec"])
        eligible = [k for k, c in sorted(raw.items()) if extraction.config_is_eligible(c, raw)]
        self.assertEqual(len(eligible), 21)
        for k in eligible:
            self.assertEqual(req(served, k), req(raw, k), k)

    def _changed_built(self):
        """The live built store with ONE list changed (as a catalogue edit would): Valve `operation` -> ["Modulating"]."""
        b = copy.deepcopy(CL.current("HVAC", fresh=True))
        b["lists"][VALVE]["operation"]["values"] = ["Modulating"]
        return b

    def test_t3_08_the_request_read_point_serves_the_rebuilt_list(self):
        with patch.object(CL, "current", return_value=self._changed_built()):
            served = extraction._load_active_configs({"HVAC"})
        self.assertEqual(_def(served[("HVAC", VALVE)], "operation")["values"], ["Modulating"])
        raw = frappe.get_all("BoQ Rate Category Config", filters={"active": 1, "discipline": "HVAC", "category_id": VALVE},
                             fields=["config"])[0]["config"]
        raw = json.loads(raw) if isinstance(raw, str) else raw
        self.assertEqual(_def(raw, "operation")["values"], ["On-Off", "Modulating"])   # the stored config is untouched

    def test_t3_09_the_served_read_point_serves_the_rebuilt_list(self):
        from nirmaan_stack.api.boq import rate_master
        with patch.object(CL, "current", return_value=self._changed_built()):
            row = rate_master.get_rate_category_config(discipline="HVAC", category_id=VALVE)
        self.assertEqual(_def(row["config"], "operation")["values"], ["Modulating"])

    def test_t3_07_the_two_live_catalogue_reads_are_pinned(self):
        seen = []
        real = frappe.get_all

        def spy(*a, **kw):
            seen.append(kw.get("order_by"))
            return real(*a, **kw)
        cfg = extraction._load_active_configs().get(("Electrical", "wiring_cabling")) or {}
        with patch.object(extraction.frappe, "get_all", side_effect=spy):
            extraction.catalog_values("Electrical", dict(cfg, identity_attribute_id="item", item_kinds=["cable"]))
            extraction.values_from_catalog("Electrical", {"kind": "cable", "attr": "material"})
        self.assertEqual(seen, [extraction.CATALOGUE_READ_ORDER] * 2)
        self.assertEqual(extraction.CATALOGUE_READ_ORDER, "modified desc, name asc")


SCRATCH = "CAT1T"


class TestT6StampFreshness(FrappeTestCase):
    """G4 on a scratch discipline (rolled back; its cache key removed)."""

    def setUp(self):
        frappe.db.rollback()
        frappe.cache().delete_value(CL.cache_key(SCRATCH))
        CL._MEMO.pop(SCRATCH, None)
        self.p = patch.object(CL, "LINKED_DISCIPLINES", ("HVAC", SCRATCH))
        self.p.start()
        cfg = {"discipline": SCRATCH, "category_id": "cat1t_cat", "item_kinds": ["cat1t_item"], "pipelines": {},
               "attribute_definitions": [{"id": "colour", "label": "Colour", "type": "choice", "values": ["Red", "Blue"]}]}
        frappe.get_doc({"doctype": "BoQ Rate Category Config", "discipline": SCRATCH, "category_id": "cat1t_cat",
                        "config": json.dumps(cfg), "active": 1}).insert(ignore_permissions=True)
        self.names = []
        for n, c in enumerate(["Red", "Blue"]):
            d = frappe.get_doc({"doctype": "BoQ Rate Master Item", "discipline": SCRATCH, "kind": "cat1t_item", "item_uid": f"cat1t-{n}",
                                "attributes": json.dumps({"colour": c}), "rates": json.dumps({"cost_supply": 10}), "active": 1})
            d.insert(ignore_permissions=True)
            self.names.append(d.name)

    def tearDown(self):
        self.p.stop()
        frappe.db.rollback()
        frappe.cache().delete_value(CL.cache_key(SCRATCH))
        CL._MEMO.pop(SCRATCH, None)

    def test_t6_01_raw_sql_attribute_edit_makes_the_next_read_rebuild(self):
        a = CL.current(SCRATCH, fresh=True)
        self.assertEqual(a["lists"]["cat1t_cat"]["colour"]["values"], ["Red", "Blue"])
        frappe.db.sql('update "tabBoQ Rate Master Item" set attributes = %s where name = %s',
                      (json.dumps({"colour": "Green"}), self.names[1]))
        b = CL.current(SCRATCH, fresh=True)
        self.assertNotEqual(a["stamp"], b["stamp"])
        self.assertEqual(b["lists"]["cat1t_cat"]["colour"]["values"], ["Red", "Green"])
        self.assertEqual(frappe.cache().get_value(CL.cache_key(SCRATCH))["stamp"], b["stamp"])

    def test_t6_02_negative_a_raw_rate_edit_does_not_move_the_stamp(self):
        a = CL.current(SCRATCH, fresh=True)
        frappe.db.sql('update "tabBoQ Rate Master Item" set rates = %s where name = %s', (json.dumps({"cost_supply": 99}), self.names[0]))
        self.assertEqual(CL.current(SCRATCH, fresh=True)["stamp"], a["stamp"])

    def test_t6_03_a_write_caches_on_commit_only(self):
        CL.current(SCRATCH, fresh=True)
        frappe.db.sql('update "tabBoQ Rate Master Item" set attributes = %s where name = %s',
                      (json.dumps({"colour": "Green"}), self.names[0]))
        stamp = CL.rebuild_after_write(SCRATCH)
        self.assertNotEqual(frappe.cache().get_value(CL.cache_key(SCRATCH))["stamp"], stamp)   # not before the commit
        frappe.db.after_commit.run()                                                           # what a commit runs
        self.assertEqual(frappe.cache().get_value(CL.cache_key(SCRATCH))["stamp"], stamp)
        frappe.db.after_commit.reset()

    def test_t6_04_a_rolled_back_write_never_caches(self):
        before = CL.current(SCRATCH, fresh=True)["stamp"]
        frappe.db.sql('update "tabBoQ Rate Master Item" set attributes = %s where name = %s',
                      (json.dumps({"colour": "Green"}), self.names[0]))
        CL.rebuild_after_write(SCRATCH)
        frappe.db.rollback()                 # the writer's transaction aborts: its after_commit callbacks are dropped
        self.assertEqual(frappe.cache().get_value(CL.cache_key(SCRATCH))["stamp"], before)

    def test_t6_05_every_app_write_route_reaches_a_rebuild_choke_point(self):
        from nirmaan_stack.api.boq import rate_master
        for fn in (rate_master.update_rate_master_item, rate_master.create_rate_master_item, rate_master.deactivate_rate_master_item,
                   rate_master._twin_confirmed_write, csv_importer.apply_plan):
            self.assertIn("recompute_derived_after_write(", inspect.getsource(fn), fn.__name__)
        src = inspect.getsource(loader.recompute_derived_after_write)
        self.assertLess(src.index("catalogue_lists.rebuild_after_write("), src.index("return 0"))   # before the early return
        for fn in (loader.load_rate_master, loader._load_multi):
            s = inspect.getsource(fn)
            self.assertLess(s.index("_verify_derived_consistent(discipline)"), s.index("catalogue_lists.rebuild_after_write(discipline)"))
            self.assertLess(s.index("catalogue_lists.rebuild_after_write(discipline)"), s.index("frappe.db.commit()"))
