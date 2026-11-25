"""CAT-1 (2026-11-26) -- THE REFERENCE GATE AND THE REQUEST GUARD (owner 2026-11-26 00:06 / 00:10 / 00:14). Every check has a NEGATIVE.

  T4  G1 (R1 - R4) and G-REF: GREEN on v89 (and on Electrical v72); RED on each injected case -- an undeclared unstocked value; a
      declaration a SKU stocks; a default naming a renamed value ("Dual Plate"); a share part's item_uid deactivated; a placeholder
      naming a removed value; a new-category clone with a bad default; a Pricing Input id that is gone. A pinned case (goldens /
      impact_examples) naming an unstocked value is INFO only. The import gate refuses such a payload by name before any write.
  T5  G2 the request guard: the request built by the product's own builders (`build_items_spec`, `build_attribute_defs`) offers, for
      every class-(a) question, exactly the rebuilt list -- WALKING the borrowed sections (Misc / Sensors / Insulation inside Valve /
      Ducting / VAV / Piping requests) and every config present, a new-category clone included. RED when a builder bypasses the merge
      on a borrowed-section drift (the Air Balancing SKUs removed on a scratch copy).
  T8  the VAV shares by item_uid: v89's 5 parts resolve to the same SKUs v88's typed parts did; a renamed SKU (same uid) still resolves
      and shows the new name; a deactivated one is refused by the gate.
  T10 v89 = v88 + cat1Edits.json exactly (the mint's own transformation); a planted undeclared change is not v89.
  REG the declared reference-key registry is pinned (a new reference key joins it in the same change).
Run: bench --site localhost run-tests --module nirmaan_stack.services.boq_rate_master.test_catalogue_gate
"""
import copy
import importlib.util
import json
import os

import frappe
from frappe.tests.utils import FrappeTestCase

from nirmaan_stack.services.boq_rate_master import catalogue_gate as CG
from nirmaan_stack.services.boq_rate_master import catalogue_lists as CL
from nirmaan_stack.services.boq_rate_master import config_validation, extraction, loader

DATA = os.path.join(os.path.dirname(loader.__file__), "data")
APP = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(loader.__file__))))
V88, V89, E72 = "rate_master_hvac_all_v88.json", "rate_master_hvac_all_v89.json", "rate_master_electrical_all_v72.json"
EDITS = os.path.join(APP, "frontend/src/pages/boq-wizard/rate-helper/__fixtures__/cat1Edits.json")
VALVE, VAV, DUCT = "hvac_valve_package", "hvac_vav_box", "hvac_ducting"


def _asset(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as fh:
        a = json.load(fh)
    for c in a["category_configs"]:
        c["discipline"] = a["discipline"]
    return a


def _refusals(a, disc=None):
    return [p for p in CG.reference_problems(a["category_configs"], a["items"], disc or a["discipline"]) if p["severity"] == CG.REFUSE]


def _cfg(a, cid):
    return next(c for c in a["category_configs"] if c["category_id"] == cid)


class TestT4Gate(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.A = _asset(V89)

    def test_t4_01_green_on_v89_and_v72_the_infos_listed(self):
        self.assertEqual(_refusals(self.A), [])
        self.assertEqual(_refusals(_asset(E72)), [])
        infos = [p for p in CG.reference_problems(self.A["category_configs"], self.A["items"], "HVAC") if p["severity"] == CG.INFO]
        self.assertTrue(infos and all(p["path"].startswith("impact_examples") for p in infos), infos[:3])

    def test_t4_02_v88_as_committed_refuses_exactly_the_undeclared_on_off(self):
        r = _refusals(_asset(V88))
        self.assertEqual([(p["config"], p["path"]) for p in r], [(VALVE, "list_spec.attribute_definitions[operation].values")])
        self.assertIn("'On-Off'", r[0]["message"])

    def test_t4_03_r2_a_declaration_a_sku_stocks_is_refused(self):
        a = copy.deepcopy(self.A)
        _cfg(a, VALVE)[CL.UNSTOCKED_KEY]["operation"].append("Modulating")
        self.assertIn((VALVE, "unstocked_answers.operation"), [(p["config"], p["path"]) for p in _refusals(a)])

    def test_t4_04_r3_a_list_with_no_stocked_value_is_refused(self):
        a = copy.deepcopy(self.A)
        v = _cfg(a, VALVE)
        d = next(x for x in v["list_spec"]["attribute_definitions"] if x["id"] == "operation")
        d["values"] = ["On-Off", "CAT1 Fake"]                          # every offered value declared, none stocked
        v[CL.UNSTOCKED_KEY]["operation"] = ["On-Off", "CAT1 Fake"]
        msgs = [p["message"] for p in _refusals(a) if p["config"] == VALVE]
        self.assertEqual(msgs, ["question operation: no value its list offers is stocked"])

    def test_t4_05_a_renamed_value_refuses_every_place_naming_it(self):
        a = copy.deepcopy(self.A)
        n = 0
        for i in a["items"]:
            if i["attributes"].get("nrv_type") == "Dual Plate":
                i["attributes"]["nrv_type"] = "Dual-Plate"
                n += 1
        self.assertGreater(n, 0)
        r = _refusals(a)
        self.assertTrue(r)
        self.assertTrue(all("Dual Plate" in p["message"] or "Dual-Plate" in p["message"] for p in r), r)
        self.assertTrue(any("defaults" in p["path"] or "values" in p["path"] for p in r), r)

    def test_t4_06_a_share_parts_item_deactivated_is_refused_by_id(self):
        a = copy.deepcopy(self.A)
        uid = _cfg(a, VAV)["list_spec"]["pricing"]["sheet_shares"]["shares"][0]["parts"][0]["sku"]["item_uid"]
        a["items"] = [i for i in a["items"] if i.get("item_uid") != uid]
        r = [p for p in _refusals(a) if "sheet_shares" in p["path"]]
        self.assertTrue(r and all(uid in p["message"] for p in r), r)

    def test_t4_07_a_placeholder_naming_a_removed_value_is_refused(self):
        a = copy.deepcopy(self.A)
        _cfg(a, VALVE)["notes"] = "Read {{cat:nrv_type=Dual Plate}} as the flanged type."
        self.assertEqual(_refusals(a), [])                     # it resolves today
        for i in a["items"]:
            if i["attributes"].get("nrv_type") == "Dual Plate":
                i["attributes"]["nrv_type"] = "Dual-Plate"
        self.assertIn((VALVE, "notes"), [(p["config"], p["path"]) for p in _refusals(a)])

    def test_t4_08_a_new_category_clone_with_a_bad_default_is_refused(self):
        a = copy.deepcopy(self.A)
        clone = copy.deepcopy(_cfg(a, VALVE))
        clone["category_id"] = "hvac_cat1_valve_clone"
        a["category_configs"].append(clone)
        self.assertEqual(_refusals(a), [])                     # a clone of a good config is good, with no code change
        d = clone["list_spec"]["pricing"]["defaults"]
        attr = next(k for k, v in d.items() if isinstance(v, dict) and isinstance(v.get("value"), str) and k != "operation")
        d[attr]["value"] = "CAT1 Triple Plate"
        self.assertIn(("hvac_cat1_valve_clone", f"list_spec.pricing.defaults.{attr}.value"),
                      [(p["config"], p["path"]) for p in _refusals(a)])

    def test_t4_09_a_gone_pricing_input_is_refused(self):
        a = copy.deepcopy(self.A)
        pid = _cfg(a, VAV)["list_spec"]["pricing"]["sheet_shares"]["shares"][0]["parts"][0]["per_input"]
        a["items"] = [i for i in a["items"] if not (i["kind"].endswith("_pricing_input") and i["attributes"].get("item") == pid)]
        self.assertTrue(any(pid in p["message"] for p in _refusals(a)))

    def test_t4_10_a_pinned_case_naming_an_unstocked_value_is_info_only(self):
        a = copy.deepcopy(self.A)
        vrf = _cfg(a, "hvac_vrf")
        self.assertTrue(vrf.get("impact_examples"))
        self.assertEqual(_refusals(a), [])
        self.assertTrue(any(p["severity"] == CG.INFO and p["config"] == "hvac_vrf"
                            for p in CG.reference_problems(a["category_configs"], a["items"], "HVAC")))

    def test_t4_11_the_import_gate_refuses_by_name_before_any_write(self):
        a = copy.deepcopy(self.A)
        for i in a["items"]:
            if i["attributes"].get("nrv_type") == "Dual Plate":
                i["attributes"]["nrv_type"] = "Dual-Plate"
        before = frappe.db.count("BoQ Rate Master Item", {"active": 1})
        with self.assertRaises(frappe.ValidationError) as cm:
            config_validation.validate_catalogue_references(a["category_configs"], a["items"], "HVAC")
        self.assertIn("Dual Plate", str(cm.exception))
        self.assertIn(VALVE, str(cm.exception))
        self.assertEqual(frappe.db.count("BoQ Rate Master Item", {"active": 1}), before)
        # and the live catalogue with v89's own configs passes (the standing catalogue = the live one)
        self.assertIsInstance(config_validation.validate_catalogue_references(self.A["category_configs"], self.A["items"], "HVAC"), list)

    def test_t4_12_the_loader_runs_the_gate_on_both_paths(self):
        import inspect
        for fn in (loader.load_rate_master, loader._load_multi):
            s = inspect.getsource(fn)
            self.assertLess(s.index("validate_catalogue_references("), s.index(".insert(ignore_permissions=True)"), fn.__name__)


def _request_mismatches(configs, built):
    """G2: every class-(a) question of every request the product's builders make vs the rebuilt list -- the main questions AND
    each borrowed section's questions (a borrower that asks offered families only asks the rebuilt list minus the others)."""
    out = []

    def check(where, defs, rebuilt, offered_filter=None, fam_id=None):
        for d in defs or []:
            r = (rebuilt or {}).get(d.get("id"))
            if not r or r.get("klass") not in ("A-FAMILY", "A-ATTRIBUTE") or "values" not in d:
                continue
            want = list(r["values"])
            if offered_filter is not None and d.get("id") == fam_id:
                want = [v for v in want if offered_filter(v)]
            got = [v for v in d["values"] if not (d.get("allow_none") and v == "None")]
            if got != want:
                out.append(f"{where} > {d['id']}: asks {got} but the catalogue list is {want}")
    for (disc, cid), cfg in sorted(configs.items()):
        if disc not in CL.LINKED_DISCIPLINES:
            continue
        if cfg.get("matching_mode") == extraction.LIST_MODE:
            spec = extraction.build_items_spec(cfg, configs, disc)
            if spec is None:
                continue
            check(cid, spec["attribute_definitions"], built["lists"].get(cid))
            secs = {s.get("id"): s for s in (cfg.get("list_spec") or {}).get("sections") or [] if isinstance(s, dict)}
            for s in spec.get("sections") or []:
                src = secs.get(s["id"]) or {}
                tcid = src.get("category_id")
                tcfg = configs.get((disc, tcid)) or {}
                offered = src.get("families") if ((tcfg.get("list_spec") or {}).get("borrowers_ask_offered_only") is True) else None
                tfams = (((tcfg.get("list_spec") or {}).get("pricing") or {}).get("families") or {})
                user_only = {u.get("family") for u in (((cfg.get("list_spec") or {}).get("pricing") or {}).get("user_addable") or [])
                             if isinstance(u, dict)}
                filt = None
                if isinstance(offered, list) and offered:
                    offered = [f for f in offered if f not in user_only]
                    filt = (lambda v, o=offered, t=tfams: v in o or v not in t)
                check(f"{cid} section {s['id']}", s["items_spec"]["attribute_definitions"], built["lists"].get(tcid), filt,
                      s["items_spec"].get("family_attribute_id"))
        else:
            check(cid, extraction.build_attribute_defs(cfg, None, disc), built["lists"].get(cid))
    return out


class TestT5RequestGuard(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.A = _asset(V89)

    def _maps(self, a):
        built = CL.build([dict(i, active=1) for i in a["items"]], a["category_configs"])
        raw = {("HVAC", c["category_id"]): c for c in a["category_configs"]}
        merged = {k: CL.merge_config(c, built, "HVAC") for k, c in raw.items()}
        return built, raw, merged

    def test_t5_01_green_today_every_config_and_every_borrowed_section(self):
        built, raw, merged = self._maps(self.A)
        self.assertEqual(_request_mismatches(merged, built), [])
        self.assertEqual(_request_mismatches(raw, built), [])          # v89's stored lists already ARE the catalogue's
        walked = [c["category_id"] for c in self.A["category_configs"] for s in (c.get("list_spec") or {}).get("sections") or []
                  if isinstance(s, dict) and s.get("category_id")]
        self.assertTrue({VALVE, DUCT, VAV} <= set(walked), walked)

    def test_t5_02_red_when_a_builder_bypasses_the_merge_on_a_borrowed_section_drift(self):
        a = copy.deepcopy(self.A)
        misc = _cfg(a, "hvac_misc")
        fam = misc["list_spec"]["family_attribute_id"]
        gone = [f for f in misc["list_spec"]["pricing"]["families"] if "Air Balancing" in f or "air balancing" in f.lower()]
        self.assertTrue(gone, "v89 Misc prices the Air Balancing families")
        a["items"] = [i for i in a["items"] if not (i["kind"] == misc["list_spec"]["pricing"]["kind"] and i["attributes"].get(fam) in gone)]
        built, raw, merged = self._maps(a)
        red = _request_mismatches(raw, built)
        self.assertTrue(any(f"{DUCT} section" in m for m in red), red)
        self.assertEqual(_request_mismatches(merged, built), [])

    def test_t5_03_a_new_category_clone_is_walked_with_no_code_change(self):
        a = copy.deepcopy(self.A)
        clone = copy.deepcopy(_cfg(a, VALVE))
        clone["category_id"] = "hvac_cat1_valve_clone"
        a["category_configs"].append(clone)
        built, raw, merged = self._maps(a)
        self.assertEqual(_request_mismatches(merged, built), [])
        fam = clone["list_spec"]["family_attribute_id"]
        d = next(x for x in clone["list_spec"]["attribute_definitions"] if x["id"] == fam)
        d["values"] = d["values"] + ["CAT1 Not Stocked"]          # the clone's list drifts: offered, never stocked
        red = _request_mismatches({("HVAC", "hvac_cat1_valve_clone"): clone, **raw}, built)
        self.assertTrue(any("hvac_cat1_valve_clone" in m for m in red), red)


class TestT8SharesByUid(FrappeTestCase):
    def test_t8_01_v89_parts_resolve_to_the_same_skus_v88_typed(self):
        a88, a89 = _asset(V88), _asset(V89)
        p88 = list(CG.share_parts(_cfg(a88, VAV)))
        p89 = list(CG.share_parts(_cfg(a89, VAV)))
        self.assertEqual(len(p89), 5)
        self.assertEqual([p for p, _ in p88], [p for p, _ in p89])
        for (_, s88), (_, s89) in zip(p88, p89):
            self.assertEqual(set(s89), {"item_uid", "attr"})
            h88, h89 = CG.resolve_share_sku(a88["items"], s88), CG.resolve_share_sku(a89["items"], s89)
            self.assertEqual(len(h89), 1)
            self.assertEqual([i["item_uid"] for i in h88], [i["item_uid"] for i in h89])
            self.assertEqual(h89[0]["attributes"][s89["attr"]], s88["value"])

    def test_t8_02_a_renamed_sku_still_resolves_and_shows_the_new_name(self):
        a = _asset(V89)
        _, sku = next(CG.share_parts(_cfg(a, VAV)))
        for i in a["items"]:
            if i.get("item_uid") == sku["item_uid"]:
                i["attributes"][sku["attr"]] = "DDC Panel / Controller (renamed)"
        h = CG.resolve_share_sku(a["items"], sku)
        self.assertEqual(h[0]["attributes"][sku["attr"]], "DDC Panel / Controller (renamed)")
        self.assertEqual([p for p in _refusals(a) if "sheet_shares" in p["path"]], [])
        # the typed form of v88 does NOT survive the same rename (the reason for the change)
        a88 = _asset(V88)
        for i in a88["items"]:
            if i.get("item_uid") == sku["item_uid"]:
                i["attributes"][sku["attr"]] = "DDC Panel / Controller (renamed)"
        self.assertTrue([p for p in CG.reference_problems(a88["category_configs"], a88["items"], "HVAC")
                         if p["severity"] == CG.REFUSE and "sheet_shares" in p["path"]])

    def test_t8_03_the_shape_validator_takes_both_forms_and_nothing_else(self):
        a = _asset(V89)
        cfg = copy.deepcopy(_cfg(a, VAV))
        config_validation._validate_config(cfg)
        cfg["list_spec"]["pricing"]["sheet_shares"]["shares"][0]["parts"][0]["sku"] = {"item_uid": "rmi-x"}
        with self.assertRaises(frappe.ValidationError):
            config_validation._validate_config(cfg)


def _mint():
    spec = importlib.util.spec_from_file_location("mint89", os.path.join(APP, "scripts/_instruments/mint_hvac_v89_cat1.py"))
    m = importlib.util.module_from_spec(spec)
    import sys
    sys.path.insert(0, os.path.join(APP, "scripts/_instruments"))
    spec.loader.exec_module(m)
    return m


class TestT10V89IsV88PlusEdits(FrappeTestCase):
    def test_t10_01_the_mints_own_transformation_byte_for_byte(self):
        m = _mint()
        with open(os.path.join(DATA, V88), encoding="utf-8") as fh:
            prev = json.load(fh)
        K = json.load(open(EDITS, encoding="utf-8"))
        by = {}
        for e in K["configs"]:
            by.setdefault(e["c"], []).append(e)
        final = copy.deepcopy(prev)
        final["category_configs"] = [m.apply_config(c, by.get(c["category_id"], [])) for c in prev["category_configs"]]
        with open(os.path.join(DATA, V89), "rb") as fh:
            self.assertEqual(m._dump(final).encode("utf-8"), fh.read())
        self.assertEqual(len(K["configs"]), 10)
        self.assertEqual(K["pricing_inputs"], {})

    def test_t10_02_negative_a_planted_change_is_not_v89(self):
        m = _mint()
        with open(os.path.join(DATA, V89), encoding="utf-8") as fh:
            a = json.load(fh)
        a["category_configs"][0]["category_display"] = a["category_configs"][0].get("category_display", "") + " "
        with open(os.path.join(DATA, V89), "rb") as fh:
            self.assertNotEqual(m._dump(a).encode("utf-8"), fh.read())


class TestDeclarationShape(FrappeTestCase):
    def test_decl_01_the_two_keys_validate_and_refuse_a_bad_shape(self):
        cfg = copy.deepcopy(_cfg(_asset(V89), VALVE))
        config_validation._validate_config(cfg)                               # v89's own declaration passes
        for bad in ({"no_such_question": ["On-Off"]}, {"operation": []}, {"operation": ["On-Off", "On-Off"]}, []):
            c = copy.deepcopy(cfg)
            c[CL.UNSTOCKED_KEY] = bad
            with self.assertRaises(frappe.ValidationError, msg=repr(bad)):
                config_validation._validate_config(c)
        c = copy.deepcopy(cfg)
        c[CL.EXCLUDES_KEY] = {"operation": ["Modulating"]}
        config_validation._validate_config(c)                                 # shape only; the gate checks carriage


class TestRegistry(FrappeTestCase):
    def test_reg_the_declared_reference_keys(self):
        self.assertEqual(len(CG.REFERENCE_KEYS), 22)
        for k in ("defaults", "value_map", "derive_when_none", "override_when", "family_when_none", "companion_items", "sections",
                  "text_notes", "read_notes", "conditions", "extraction_defaults", "synonyms", "sheet_shares", "Pricing Input",
                  "placeholders", "goldens"):
            self.assertTrue(any(k in r for r in CG.REFERENCE_KEYS), k)
