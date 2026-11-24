"""BCS-2b (2026-11-24, desktop dev2) -- MINT ELECTRICAL v74 = v73 with the supply cost calculations GENERATED from the price
calculations (owner R1 2026-11-23 01:35, R2 01:38, R3 2026-11-24 00:36 "1 1b", R4 R-BCS-89, R6 2026-11-22 15:09).

What changes: the 13 supply cost pipelines (`tray_bcs`, `conduit_bcs`, `db_buildup_bcs`, `earthing_bcs`, `indsock_bcs`, `jb_bcs`,
`lms_bcs`, `misc_bcs`, `pw_bcs`, `popup_bcs`, `swsock_bcs`, `cable_bcs`, `termination_bcs`) are replaced, under the SAME ids, by
what `nirmaan_stack/services/boq_rate_master/bcs_derive.py` generates from each category's price pipeline (its one general rule
and its exceptions table). 11 are replaced whole; `misc_bcs` and `popup_bcs` also carry an installation output, whose steps are
taken over from v73 unchanged (R2). `tray_bcs_install` is not touched. Every price pipeline, item, Pricing Input, worked example
and every other key stays byte-equal to v73 (asserted).

THE EXACT GUARD (P3b; it replaces BCS-2's neutral agreement guard for these pairs): every generated pipeline, run by the
product's own interpreter, must give EXACTLY v73's stored cost - every output, every rounding in place, no tolerance - and refuse
where v73's refuses, on every case: the agreement cases (one selection per active catalogue item and per pair, as BCS-2's mint
built them), every worked example of the category, and (with --rows) the priced rows of a selections file. The mint refuses on
any difference. Nothing of the old neutral guard remains for these pairs: its 0.01 allowance and its markup / rounding stripping
existed because the cost was written by hand beside the price; a generated cost is compared with the figure itself.

Runs IN THE CONTAINER under the bench's python. No database write except `load`.
Usage (container, from frappe-bench): env/bin/python -I <this> build|agree|load|verify [--candidate P] [--rows R] [--site S]
"""
import argparse
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile

APP = "/workspace/development/frappe-bench/apps/nirmaan_stack"
DATA = os.path.join(APP, "nirmaan_stack/services/boq_rate_master/data")
V73 = os.path.join(DATA, "rate_master_electrical_all_v73.json")
V74 = os.path.join(DATA, "rate_master_electrical_all_v74.json")
sys.path.insert(0, APP)
from nirmaan_stack.services.boq_rate_master import bcs_derive  # noqa: E402  (pure: no frappe, no database)

GENERATED = {(p["category"], p["cost"]) for p in bcs_derive.PAIRS}


def _canon(o):
    return json.dumps(o, sort_keys=True, separators=(",", ":"), default=str)


def _dump(p):
    return json.dumps(p, indent=1, ensure_ascii=False) + "\n"


def _sha16(o):
    return hashlib.sha256(_canon(o).encode()).hexdigest()[:16]


def _connect(site):
    os.chdir("/workspace/development/frappe-bench/sites")
    import frappe
    frappe.init(site=site)
    frappe.connect()
    return frappe


# ---------------------------------------------------------------- the interpreter (the product's own, bundled with esbuild)
HARNESS = r'''
import { readFileSync } from "node:fs";
import { runPipeline } from "%(fe)s/src/pages/pricing/rate-master/ratePipelineInterpreter";
const spec = JSON.parse(readFileSync(process.argv[2], "utf8"));
const items = spec.items.map((i: any) => ({ ...i, discipline: "Electrical",
  attributes: { ...i.attributes, ...(i.brand ? { brand: i.brand } : {}) } }));          // the product's brand projection
const out: any[] = [];
for (const r of spec.runs) {
  const pl = spec.pipelines[r.side][r.cat][r.pid];
  let res: any;
  try { res = runPipeline(r.pid, pl, items, r.sel); } catch (e: any) { out.push({ id: r.id, side: r.side, status: "error", finals: null, last: String(e?.message ?? e).slice(0, 200) }); continue; }
  const st = res.steps ?? [];
  out.push({ id: r.id, side: r.side, status: res.status, finals: res.finals ?? null, last: st[st.length - 1]?.matchedCondition ?? st[st.length - 1]?.label ?? null });
}
console.log(JSON.stringify(out));
'''


def run_interpreter(items, pipelines, runs):
    """[results] of the product's runPipeline; `pipelines` = {side: {cat: {pid: pipeline}}}; nothing computed here."""
    fe = os.path.join(APP, "frontend")
    node = sorted(glob.glob("/home/frappe/.nvm/versions/node/*/bin/node"))[-1]
    with tempfile.TemporaryDirectory(prefix="bcs2b_mint_") as d:
        ts, js, spec = os.path.join(d, "h.ts"), os.path.join(d, "h.mjs"), os.path.join(d, "spec.json")
        open(ts, "w").write(HARNESS % {"fe": fe})
        json.dump({"items": items, "pipelines": pipelines, "runs": runs}, open(spec, "w"))
        env = dict(os.environ, PATH=os.path.dirname(node) + ":" + os.environ["PATH"])
        r = subprocess.run([os.path.join(fe, "node_modules/.bin/esbuild"), ts, "--bundle", "--platform=node", "--format=esm", "--outfile=" + js, "--log-level=error"],
                           cwd=fe, env=env, capture_output=True, text=True)
        if r.returncode:
            raise SystemExit("esbuild: " + r.stderr)
        r = subprocess.run([node, "--max-old-space-size=4096", js, spec], env=env, capture_output=True, text=True)
        if r.returncode:
            raise SystemExit("interpreter: " + r.stderr[-2000:])
    return json.loads(r.stdout)


# ---------------------------------------------------------------- the exact guard's cases
def agree_cases(final):
    """One selection per ACTIVE catalogue item and per price/cost pair that prices it on its own, plus conduit on every cable
    item and a box with modules. COPIED from scripts/_instruments/mint_electrical_v73_bcs2.py agree_cases() (BCS-2), unchanged,
    so the population is BCS-2's (1,633 runs on v73)."""
    cfg = {c["category_id"]: c for c in final["category_configs"]}

    def gold(cat, gid):
        return dict([g for g in cfg[cat]["goldens"] if g["id"] == gid][0]["attrs"])

    none_db = {k: v for n in range(1, 6) for k, v in (("mcb%d_item" % n, "None"), ("mcb%d_qty" % n, 0))}
    none_db.update({"db_shell_item": "None", "db_shell_qty": 0, "enclosure_item": "None", "enclosure_qty": 0})
    out = []
    for it in final["items"]:
        a, k = it["attributes"], it["kind"]

        def add(cat, sel):
            out.append((cat, it, sel))

        if k == "cable_tray":
            add("cabletray_raceway", {**gold("cabletray_raceway", "t1"), **{x: a[x] for x in ("tray_type", "material", "thickness_mm", "width_mm")}})
        elif k == "conduit":
            add("conduit_piping", {**gold("conduit_piping", "c1"), "conduit_type": a["conduit_type"], "size_mm": a["size_mm"]})
        elif k == "earthing_item":
            add("earthing", {**gold("earthing", "e1"), "material": a.get("material"), "type": a.get("type"), "with_busbar": "Without"})
        elif k == "junction_box":
            add("junction_box_raceway", {"face_mm": a["face_mm"]})
        elif k == "lms_item":
            add("lighting_mgmt_system", {"description": a["description"], "brand": it.get("brand") or ""})
        elif k == "misc_item":
            add("miscellaneous", {"description": a["description"]})
        elif k == "popup_box_module":
            add("popup_boxes", gold("popup_boxes", "p3"))
            add("popup_boxes", gold("popup_boxes", "p2"))
        elif k in ("cable", "termination"):
            base = {**gold("wiring_cabling", "g1"), **{x: a[x] for x in ("material", "insulation", "core", "thickness_sqmm")}, "runs": 1}
            add("wiring_cabling", {**base, "conduit_included": "No"})
            if k == "cable":
                add("wiring_cabling", {**base, "conduit_included": "Yes", "conduit_type": "PVC", "size_mm": 25})
        elif k == "industrial_socket":
            sel = {**gold("industrial_sockets", "i1"), **{x: a[x] for x in ("item", "enclosure", "rating", "pole")}, "paired_mcb": "None", "mcb_present": "No"}
            add("industrial_sockets", sel)
        elif k == "db_shell":
            add("db_switchgear", {**none_db, "db_shell_item": a["item"], "db_shell_qty": 1})
        elif k == "db_switchgear_item" and a.get("family") in ("Switchgear", "Enclosure Box"):
            slot = "mcb1" if a["family"] == "Switchgear" else "enclosure"
            add("db_switchgear", {**none_db, slot + "_item": a["item"], slot + "_qty": 1})
        elif k == "switch_socket_item" and not (a.get("family") == "Switch" and "blank" in a["item"].lower()):
            base = {**gold("switches_sockets", "s1"), "socket1_item": "None", "socket1_qty": 0, "colour": a.get("colour"), "back_box": "No", "blank_qty": 0}
            slots = {"Switch": {"switch_item": a["item"], "switch_qty": 1}, "Socket": {"socket1_item": a["item"], "socket1_qty": 1},
                     "Grid and Face Plates": {"plate_item": a["item"], "plate_qty": 1}, "Back Box": {"box_item": a["item"], "back_box": "Yes", "colour": "White"}}
            if a.get("family") in slots:
                add("switches_sockets", {**base, **slots[a["family"]]})
    out.append(("point_wiring", {"item_uid": "(pw1)", "kind": "golden"}, gold("point_wiring", "pw1")))
    out.append(("industrial_sockets", {"item_uid": "(i7)", "kind": "golden"}, gold("industrial_sockets", "i7")))
    return out


def exact_cases(final, rows_file=None):
    """[(case id, category, cost id, selection)]: the agreement cases, every worked example, and the priced rows of `rows_file`."""
    by_cat = {}
    for p in bcs_derive.PAIRS:
        by_cat.setdefault(p["category"], []).append(p)
    cases = []
    for n, (cat, it, sel) in enumerate(agree_cases(final)):
        for p in by_cat[cat]:
            if (it.get("kind") == "termination" and p["price"] != "termination_boq") or (it.get("kind") == "cable" and p["price"] == "termination_boq"):
                continue
            cases.append(("agree|%d|%s" % (n, p["cost"]), cat, p["cost"], sel))
    for c in final["category_configs"]:
        for p in by_cat.get(c["category_id"], []):
            for g in final["goldens"].get(c["category_id"], c.get("goldens") or []):
                cases.append(("example|%s|%s" % (g["id"], p["cost"]), c["category_id"], p["cost"], g["attrs"]))
    if rows_file:
        for line in open(rows_file, encoding="utf-8"):
            if not line.strip():
                continue
            r = json.loads(line)
            ps = by_cat.get(r["cat"], [])
            p = next((x for x in ps if x["price"] == r.get("helper_primary")), ps[0] if ps else None)
            if p:
                cases.append(("row|%s|%s" % (r["key"], p["cost"]), r["cat"], p["cost"], r.get("selected") or {}))
    return cases


def exact_guard(prev, final, rows_file=None, quiet=False):
    """P3b: generated (final) against stored (prev), case by case, EXACTLY. Returns (differences, cases, per-category counts)."""
    pv = {c["category_id"]: c for c in prev["category_configs"]}
    fv = {c["category_id"]: c for c in final["category_configs"]}
    cases = exact_cases(final, rows_file)
    pipelines = {"stored": {}, "generated": {}}
    for cat, cid in GENERATED:
        pipelines["stored"].setdefault(cat, {})[cid] = pv[cat]["pipelines"][cid]
        pipelines["generated"].setdefault(cat, {})[cid] = fv[cat]["pipelines"][cid]
    runs = []
    for cid_, cat, cid, sel in cases:
        for side in ("stored", "generated"):
            runs.append({"id": cid_, "side": side, "cat": cat, "pid": cid, "sel": sel})
    res = run_interpreter(final["items"], pipelines, runs)
    by = {}
    for r in res:
        by.setdefault(r["id"], {})[r["side"]] = r
    diffs, counts = [], {}
    for cid_, cat, cid, sel in cases:
        a, b = by[cid_]["stored"], by[cid_]["generated"]
        c = counts.setdefault(cid, {"cases": 0, "equal": 0, "refuse_alike": 0, "differ": 0})
        c["cases"] += 1
        outs = pv[cat]["pipelines"][cid]["output"]
        same = a["status"] == b["status"] and all((a["finals"] or {}).get(o) == (b["finals"] or {}).get(o) for o in outs)
        if same:
            c["equal"] += 1
            if a["status"] != "ok":
                c["refuse_alike"] += 1
        else:
            c["differ"] += 1
            diffs.append({"case": cid_, "stored": [a["status"], {o: (a["finals"] or {}).get(o) for o in outs}],
                          "generated": [b["status"], {o: (b["finals"] or {}).get(o) for o in outs}]})
    return diffs, len(cases), counts


# ---------------------------------------------------------------- build / agree / load / verify
def _reads_inputs(pl):
    return sorted({(s["ref"]["item"], s["target"]) for s in pl["steps"] if s.get("step") == "rate_ref"})


def build(out, site):
    frappe = _connect(site)
    from nirmaan_stack.services.boq_rate_master import config_validation
    from nirmaan_stack.services.boq_rate_master.loader import _validate_items, _validate_one_config
    raw = open(V73, "rb").read()
    prev = json.loads(raw.decode("utf-8"))
    if _dump(prev).encode("utf-8") != raw:
        raise SystemExit("re-dumping v73 does not reproduce its bytes")
    final = bcs_derive.apply(prev, stored=prev)

    # BYTE-IDENTITY: every item in order, every key, every price pipeline and every other pipeline; only the 13 cost ids differ
    assert [_canon(a) for a in prev["items"]] == [_canon(b) for b in final["items"]]
    assert [k for k in final] == [k for k in prev]
    for k in prev:
        if k != "category_configs":
            assert _canon(prev[k]) == _canon(final[k]), k
    pv, fv = {c["category_id"]: c for c in prev["category_configs"]}, {c["category_id"]: c for c in final["category_configs"]}
    assert [c["category_id"] for c in prev["category_configs"]] == [c["category_id"] for c in final["category_configs"]]
    changed = []
    for cat, x in pv.items():
        y = fv[cat]
        for k in set(x) | set(y):
            if k != "pipelines":
                assert _canon(x.get(k)) == _canon(y.get(k)), (cat, k)
        assert list(x["pipelines"]) == list(y["pipelines"]), cat
        for pid in x["pipelines"]:
            if (cat, pid) in GENERATED:
                xp, yp = x["pipelines"][pid], y["pipelines"][pid]
                assert xp["output"] == yp["output"], (cat, pid, "output names")
                assert _reads_inputs(xp) == _reads_inputs(yp), (cat, pid, "Pricing Inputs read", _reads_inputs(xp), _reads_inputs(yp))
                if _canon(xp) != _canon(yp):
                    changed.append(pid)
            else:
                assert _canon(x["pipelines"][pid]) == _canon(y["pipelines"][pid]), (cat, pid)
    assert sorted(changed) == sorted(cid for _, cid in GENERATED), changed
    assert bcs_derive.drift(final) == [], "the generated file does not regenerate to itself"
    print("IDENTITY: %d items, every key and every price / installation pipeline byte-equal to v73; replaced %d cost pipelines %s"
          % (len(final["items"]), len(changed), sorted(changed)))
    for p in bcs_derive.PAIRS:
        print("  GENERATED %-22s from %-18s exceptions %s" % (p["cost"], p["price"], [e["kind"] for e in p["exceptions"]] or "-"))

    _validate_items(final["items"])
    stored = [dict(c, discipline=final["discipline"]) for c in final["category_configs"]]
    goldens = final["goldens"]
    for n, c in enumerate(stored):
        c["goldens"] = goldens.get(c["category_id"], c.get("goldens"))
        _validate_one_config(c, "category_configs[%d]" % n)
        config_validation._validate_config(c)
    rates = {(i["kind"], i["attributes"]["item"]): i["rates"] for i in final["items"] if str(i["kind"]).endswith("_pricing_input")}
    problems = config_validation.bcs_problems(stored, rates)
    if problems:
        raise SystemExit("bcs check refuses: %r" % problems)
    text = _dump(final)
    tokens = sorted(set(re.findall(r"v\d+", text)) - set(re.findall(r"v\d+", raw.decode("utf-8"))))
    if tokens:
        raise SystemExit("the asset text carries version-like tokens v73 does not %r (h07)" % tokens)
    open(out, "w", encoding="utf-8", newline="").write(text)
    print("candidate written:", out, "| items", len(final["items"]), "| configs", len(final["category_configs"]),
          "| sha256", hashlib.sha256(text.encode("utf-8")).hexdigest())
    frappe.destroy()


def run_agree(candidate, site, rows_file=None):
    prev = json.load(open(V73, encoding="utf-8"))
    final = json.load(open(candidate, encoding="utf-8"))
    diffs, n, counts = exact_guard(prev, final, rows_file)
    print("EXACT GUARD: %d cases (agreement cases + worked examples%s), %d differ" % (n, " + rows of " + rows_file if rows_file else "", len(diffs)))
    for cid in sorted(counts):
        print("   %-18s %s" % (cid, counts[cid]))
    for d in diffs[:15]:
        print("   DIFF", d)
    if diffs:
        raise SystemExit("the mint refuses: a generated cost is not exactly v73's stored cost")


def load(candidate, site, rows_file=None):
    run_agree(candidate, site, rows_file)
    frappe = _connect(site)
    frappe.set_user("Administrator")
    from nirmaan_stack.services.boq_rate_master import exporter, loader
    payload = exporter.build_asset("Electrical")
    snap = exporter.write_snapshot("Electrical", exporter.serialize_asset(payload), payload)
    frappe.db.commit()
    print("PRE-LOAD SNAPSHOT", snap, "| items", len(payload["items"]), "| configs", len(payload["category_configs"]))
    s = loader.load_rate_master(path=candidate, replace=True)
    frappe.db.commit()
    print("LOAD SUMMARY:", json.dumps(s, default=str)[:1500])
    frappe.destroy()


def verify(candidate, site):
    """live == file, item by item and sheet by sheet; on a difference it names the sheets AND the pipelines that differ."""
    frappe = _connect(site)
    asset = json.load(open(candidate, encoding="utf-8"))
    J = lambda v: json.loads(v) if isinstance(v, str) else v
    li = frappe.db.sql('select item_uid, kind, brand, unit, attributes, rates from "tabBoQ Rate Master Item" where active=1 and discipline=%s', ("Electrical",), as_dict=True)
    lc = frappe.db.sql('select category_id, config from "tabBoQ Rate Category Config" where active=1 and discipline=%s', ("Electrical",), as_dict=True)
    L = {r["item_uid"]: {"kind": r["kind"], "brand": r["brand"] or None, "unit": r["unit"] or None, "attributes": J(r["attributes"]), "rates": J(r["rates"])} for r in li}
    LC = {r["category_id"]: J(r["config"]) for r in lc}
    A = {r["item_uid"]: {"kind": r["kind"], "brand": r.get("brand") or None, "unit": r.get("unit") or None, "attributes": r["attributes"], "rates": r["rates"]} for r in asset["items"]}
    AC = {c["category_id"]: dict(c, discipline="Electrical") for c in asset["category_configs"]}
    for cat, goldens in asset["goldens"].items():       # the loader writes no `goldens` key on a sheet without examples
        AC[cat]["goldens"] = goldens
    pipes = sorted("%s/%s" % (c, p) for c in set(LC) & set(AC)
                   for p in set((LC[c].get("pipelines") or {})) | set((AC[c].get("pipelines") or {}))
                   if _canon((LC[c].get("pipelines") or {}).get(p)) != _canon((AC[c].get("pipelines") or {}).get(p)))
    keys = sorted("%s/%s" % (c, k) for c in set(LC) & set(AC) for k in set(LC[c]) | set(AC[c])
                  if k != "pipelines" and _canon(LC[c].get(k)) != _canon(AC[c].get(k)))
    out = {"items_live": len(L), "items_file": len(A), "configs_live": len(LC), "configs_file": len(AC),
           "items_missing": sorted(set(A) - set(L)), "items_extra": sorted(set(L) - set(A)),
           "items_differing": sorted(u for u in set(L) & set(A) if _canon(L[u]) != _canon(A[u])),
           "configs_differing": sorted(c for c in set(LC) | set(AC) if _canon(LC.get(c)) != _canon(AC.get(c))),
           "pipelines_differing": pipes, "other_keys_differing": keys,
           "sha_items_live": _sha16([[u, L[u]] for u in sorted(L)]), "sha_items_file": _sha16([[u, A[u]] for u in sorted(A)]),
           "sha_configs_live": _sha16([[c, LC[c]] for c in sorted(LC)]), "sha_configs_file": _sha16([[c, AC[c]] for c in sorted(AC)])}
    out["VERDICT"] = "EQUAL" if not (out["items_missing"] or out["items_extra"] or out["items_differing"] or out["configs_differing"]) else "DIFFER"
    print(json.dumps(out, indent=1, sort_keys=True))
    frappe.destroy()
    if out["VERDICT"] != "EQUAL":
        raise SystemExit("live != file")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("phase", choices=["build", "agree", "load", "verify"])
    ap.add_argument("--candidate", default=V74)
    ap.add_argument("--rows", default=None, help="a selections file (jsonl: key, cat, helper_primary, selected) whose rows the exact guard also runs")
    ap.add_argument("--site", default=os.environ.get("ENV_SYNC_SITE", "localhost"))
    a = ap.parse_args()
    if a.phase == "build":
        build(a.candidate, a.site)
    elif a.phase == "agree":
        run_agree(a.candidate, a.site, a.rows)
    elif a.phase == "load":
        load(a.candidate, a.site, a.rows)
    else:
        verify(a.candidate, a.site)
