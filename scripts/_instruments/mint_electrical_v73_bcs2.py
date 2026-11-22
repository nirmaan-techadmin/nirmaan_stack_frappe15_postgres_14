"""BCS-2 (2026-11-22, desktop dev2) -- MINT ELECTRICAL v73 = v72 + THE BCS COST RULES (owner R1 - R4, 2026-11-21 / 22).

The owner's rules: BCS supply = BoQ supply / (1 + supply margin) unless stated; every component of a composite counts; wastage is
added; junction boxes and industrial sockets cost list price less discount, before the price's round-up (option b); "the discount
% should change if the user changes it ... dont hardcode it" -- so every figure below is READ from a Pricing Input, never typed.

  wiring_cabling       `cable_bcs` gains the conduit part the price adds (conduit list x (1 - conduit discount), no wastage)
  popup_boxes          `popup_bcs` gains the module parts the price adds (list x (1 - switch & socket discount)); box unchanged
  junction_box_raceway NEW `jb_bcs`: list x (1 - junction-box discount), no round-up
  industrial_sockets   NEW `indsock_bcs`: socket list x (1 - its discount) + paired MCB list x (1 - switchgear discount), no round-up
  db_switchgear, switches_sockets  the cost sum refuses with the price side's own sentence, never 0
                       (point_wiring: `pw_boq_supply` carries no such sentence; both its sides already refuse at circuit_fit)
  every category       `bcs_default_margin`: WHICH Pricing Input the supply margin is read from (a reference, never a number)
  electrical_pricing_inputs  + item "Electrical installation cost per sq ft (BCS)" = 42 under "amount" (owner 4b: no new column), `summary_inputs` names it
  goldens              15 point-wiring expectations re-computed by the interpreter (the 4 lighting ones are not stale: they match
                       on the brand the product projects); + worked examples for the new parts

Every other item, pipeline and golden stays byte-equal. Runs IN THE CONTAINER under the bench's python. No database write except `load`.
Usage (container, from frappe-bench): env/bin/python -I <this> build|agree|load|verify [--candidate P]   (site: ENV_SYNC_SITE or --site)
"""
import argparse
import copy
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
V72 = os.path.join(DATA, "rate_master_electrical_all_v72.json")
V73 = os.path.join(DATA, "rate_master_electrical_all_v73.json")
KIND = "electrical_pricing_input"
FT2_ID = "elec_bcs_install_per_sqft"
FT2_NAME = "Electrical installation cost per sq ft (BCS)"
DB_REFUSAL_FROM = {"db_switchgear": ("db_buildup_supply", "db_buildup_bcs"), "switches_sockets": ("swsock_boq", "swsock_bcs")}
# (price pipeline, its supply output, cost pipeline, its cost output) -- the pairs the agreement guard checks
PAIRS = {
    "cabletray_raceway": [("tray_boq_supply", "supply_per_rmt", "tray_bcs", "bcs_supply")],
    "conduit_piping": [("conduit_boq", "supply_per_mtr", "conduit_bcs", "bcs_supply_per_mtr")],
    "db_switchgear": [("db_buildup_supply", "supply", "db_buildup_bcs", "bcs_supply")],
    "earthing": [("earthing_boq", "supply", "earthing_bcs", "bcs_supply")],
    "industrial_sockets": [("indsock_boq", "supply", "indsock_bcs", "bcs_supply")],
    "junction_box_raceway": [("jb_boq", "supply", "jb_bcs", "bcs_supply")],
    "lighting_mgmt_system": [("lms_boq", "supply", "lms_bcs", "bcs_supply")],
    "miscellaneous": [("misc_boq", "supply", "misc_bcs", "bcs_supply")],
    "point_wiring": [("pw_boq_supply", "supply", "pw_bcs", "bcs_supply")],
    "popup_boxes": [("popup_boq", "supply", "popup_bcs", "bcs_supply")],
    "switches_sockets": [("swsock_boq", "supply", "swsock_bcs", "bcs_supply")],
    "wiring_cabling": [("cable_boq", "supply_per_mtr", "cable_bcs", "bcs_supply_per_mtr"),
                       ("termination_boq", "supply_per_set", "termination_bcs", "bcs_supply_per_set")],
}


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
const neutralItems = items.map((i: any) => String(i.kind).endsWith("_pricing_input")
  ? { ...i, rates: Object.fromEntries(Object.entries(i.rates).map(([k, v]: any) =>
      [k, k === "supply_markup" || k === "wastage" || k === "bcs_markup" ? 0 : k === "ratio" ? 1 : v])) } : i);
const neutralPl = (p: any) => ({ ...p, steps: p.steps.filter((s: any) => s.step !== "roundup").map((s: any) =>
  s.rate_stages ? { ...s, rate_stages: s.rate_stages.map(({ round, ...r }: any) => r) } : s) });
const out: any[] = [];
for (const r of spec.runs) {
  const cfg = spec.configs[r.cat];
  const sel = r.sel;
  if (r.mode === "neutral") {
    const p = runPipeline(r.price, neutralPl(cfg.pipelines[r.price]), neutralItems, sel);
    const c = runPipeline(r.cost, neutralPl(cfg.pipelines[r.cost]), neutralItems, sel);
    out.push({ ...r, sel: undefined, pStatus: p.status, cStatus: c.status, p: p.finals[r.pOut] ?? null, c: c.finals[r.cOut] ?? null });
  } else {
    const res = runPipeline(r.pid, cfg.pipelines[r.pid], items, sel);
    out.push({ id: r.id, pid: r.pid, status: res.status, finals: res.finals, last: res.steps[res.steps.length - 1]?.matchedCondition ?? res.steps[res.steps.length - 1]?.label ?? null });
  }
}
console.log(JSON.stringify(out));
'''


def run_interpreter(payload, runs):
    """[results] of the product's runPipeline on `payload` (a whole asset dict); nothing computed here."""
    fe = os.path.join(APP, "frontend")
    node = sorted(glob.glob("/home/frappe/.nvm/versions/node/*/bin/node"))[-1]
    with tempfile.TemporaryDirectory(prefix="bcs2_mint_") as d:
        ts, js, spec = os.path.join(d, "h.ts"), os.path.join(d, "h.mjs"), os.path.join(d, "spec.json")
        open(ts, "w").write(HARNESS % {"fe": fe})
        json.dump({"items": payload["items"], "configs": {c["category_id"]: c for c in payload["category_configs"]}, "runs": runs}, open(spec, "w"))
        env = dict(os.environ, PATH=os.path.dirname(node) + ":" + os.environ["PATH"])
        r = subprocess.run([os.path.join(fe, "node_modules/.bin/esbuild"), ts, "--bundle", "--platform=node", "--format=esm", "--outfile=" + js, "--log-level=error"],
                           cwd=fe, env=env, capture_output=True, text=True)
        if r.returncode:
            raise SystemExit("esbuild: " + r.stderr)
        r = subprocess.run([node, js, spec], env=env, capture_output=True, text=True)
        if r.returncode:
            raise SystemExit("interpreter: " + r.stderr[-2000:])
    return json.loads(r.stdout)


# ---------------------------------------------------------------- the transformation
def _step(pl, **match):
    hit = [s for s in pl["steps"] if all(s.get(k) == v for k, v in match.items())]
    assert len(hit) == 1, (match, len(hit))
    return hit[0]


def _rate_ref(item, target):
    return {"step": "rate_ref", "ref": {"kind": KIND, "item": item}, "target": target, "result": "pi_%s_%s" % (item, target),
            "explain": "pricing input: %s (%s)" % (item, target)}


def _cost_mult(item):
    """cost multiplier = 1 - discount, derived live from the Pricing Input (the same shape `swsock_bcs` uses)."""
    return {"step": "scale", "target": "pi_%s_discount" % item, "result": "pi_%s_bcs" % item, "formula": "1-base", "params": {},
            "explain": "BCS multiplier = 1 - discount", "pricing_input": True}


def edit_cable(c):
    """P2b 1 -- the conduit part the price adds when conduit is included; wastage on the cable only, no rounding on the sum."""
    boq, bcs = c["pipelines"]["cable_boq"], c["pipelines"]["cable_bcs"]
    head = [s for s in boq["steps"] if s["step"] in ("map_attribute", "catalog_fit")]
    assert len(head) == 4, len(head)
    ref = copy.deepcopy(_step(boq, step="component_ref", name="conduit"))
    ref["rate_stages"] = [{"mult_from_ctx": "pi_conduit_bcs"}]
    ref["explain"] = "the conduit the price adds, at our cost: list x (1 - the conduit discount); no wastage on the conduit, not rounded"
    steps = copy.deepcopy(head) + bcs["steps"][:4] + [
        ref,
        {"step": "sum_components", "result": "conduit_cost", "explain": "the conduit alone, zero when conduit is not included"},
        {"step": "scale", "target": "bcs_supply_per_mtr", "result": "bcs_supply_per_mtr", "params": {"conduit_from_ctx": "conduit_cost"},
         "formula": "base+conduit", "explain": "the cable (rounded as before) plus its conduit at cost"},
        _rate_ref("conduit", "discount"), _cost_mult("conduit")] + bcs["steps"][4:]
    for s in steps:
        if s.get("step") == "apply_effective_multiplier":
            s["explain"] = "discounted product cost plus the cable's wastage, no markup"
    bcs["steps"] = steps


def edit_popup(c):
    """P2b 2 -- the module parts the price adds; the box stays at its ratio."""
    boq, bcs = c["pipelines"]["popup_boq"], c["pipelines"]["popup_bcs"]
    fit = [copy.deepcopy(s) for s in boq["steps"] if s["step"] == "module_fit"]
    refs = [copy.deepcopy(s) for s in boq["steps"] if s["step"] == "component_ref"]
    assert len(fit) == 1 and len(refs) == 7, (len(fit), len(refs))
    bcs["steps"] = bcs["steps"] + fit + refs + [
        {"step": "sum_components", "result": "module_list", "explain": "the modules the price adds, at list"},
        {"step": "scale", "target": "module_list", "result": "module_cost", "params": {"m_from_ctx": "pi_swsock_bcs"}, "formula": "base*m",
         "explain": "the modules at our cost: list x (1 - the switch & socket discount), not rounded"},
        {"step": "scale", "target": "bcs_supply", "result": "bcs_supply", "params": {"modules_from_ctx": "module_cost"}, "formula": "base+modules",
         "explain": "our cost = the box at its ratio plus the modules it carries"},
        _rate_ref("swsock", "discount"), _cost_mult("swsock")]


def new_jb(c):
    """P2b 3 -- list x (1 - junction-box discount), no round-up."""
    boq = c["pipelines"]["jb_boq"]
    match = copy.deepcopy(_step(boq, step="match_master_row"))
    c["pipelines"]["jb_bcs"] = {"output": ["bcs_supply"], "note": "BCS = the list price less the junction-box discount, before the price's round-up (owner 2026-11-21 option b)",
                                "steps": [match,
                                          {"step": "scale", "target": "list_price", "result": "bcs_supply", "params": {"discount_from_ctx": "pi_jb_discount_discount"},
                                           "formula": "base*(1-discount)", "explain": "our cost = the list price less the junction-box discount"},
                                          _rate_ref("jb_discount", "discount")]}


def new_indsock(c):
    """P2b 4 -- socket list less the industrial-socket discount + paired breaker list less the switchgear discount, no round-up."""
    boq = copy.deepcopy(c["pipelines"]["indsock_boq"])
    steps = []
    for s in boq["steps"]:
        if s["step"] == "rate_ref" and s["target"] == "supply_markup":
            continue
        if s["step"] == "scale":
            continue
        if s["step"] == "component_ref":
            s["rate_stages"] = [{"mult_from_ctx": s["rate_stages"][0]["mult_from_ctx"].replace("_boq", "_bcs")}]
        if s["step"] == "sum_components":
            s["result"] = "bcs_supply"
        steps.append(s)
    steps += [_cost_mult("indsock"), _cost_mult("switchgear")]
    c["pipelines"]["indsock_bcs"] = {"output": ["bcs_supply"], "note": "BCS = list price less discount, part by part, before the price's round-up (owner 2026-11-21 option b)",
                                     "steps": steps}


def transform(prev):
    """v73 = v72 with ONLY the edits above. Returns (final, log)."""
    final = copy.deepcopy(prev)
    cfg = {c["category_id"]: c for c in final["category_configs"]}
    log = []
    edit_cable(cfg["wiring_cabling"]); log.append("cable_bcs: + conduit part (4 head steps, conduit component, its sum and add, conduit discount)")
    edit_popup(cfg["popup_boxes"]); log.append("popup_bcs: + module_fit, 7 module parts, their sum at the switch & socket discount, the add")
    new_jb(cfg["junction_box_raceway"]); log.append("jb_bcs: NEW")
    new_indsock(cfg["industrial_sockets"]); log.append("indsock_bcs: NEW")
    for cat, (pb, pc) in DB_REFUSAL_FROM.items():
        sent = [s["none_refusal"] for s in cfg[cat]["pipelines"][pb]["steps"] if s["step"] == "sum_components"][0]
        _step(cfg[cat]["pipelines"][pc], step="sum_components")["none_refusal"] = sent
        log.append("%s: sum refuses with the price side's sentence" % pc)
    for cat, entries in MARGINS.items():
        cfg[cat]["bcs_default_margin"] = {"entries": [dict(e) for e in entries]}
        log.append("%s: bcs_default_margin (%d entr%s)" % (cat, len(entries), "y" if len(entries) == 1 else "ies"))
    final["items"].append({
        "kind": KIND, "brand": None, "unit": "Rs per sq ft",
        "attributes": {"item": FT2_ID, "name": FT2_NAME,
                       "remarks": "Our installation cost for an Electrical BoQ = this x the project's area in square feet. Read by the BoQ summary, not by any category's rule.",
                       "shared_by": "", "used_by": "BoQ summary"},
        "rates": {"amount": 42.0}, "source": {"sheet": "Pricing Inputs", "row": 0}, "item_uid": FT2_UID})
    cfg["electrical_pricing_inputs"]["summary_inputs"] = [FT2_ID]
    log.append("item %s amount 42 + summary_inputs" % FT2_ID)
    return final, log


def E(item, field, components=None, when=None):
    e = {}
    if components:
        e["components"] = components
    if when:
        e["when"] = when
    e.update({"ref": {"kind": KIND, "item": item}, "field": field})
    return e


MARGINS = {
    "cabletray_raceway": [E("tray_supply", "supply_markup")],
    "conduit_piping": [E("conduit", "supply_markup")],
    "db_switchgear": [E("switchgear", "supply_markup")],
    "earthing": [E("earthing_supply", "supply_markup")],
    "industrial_sockets": [E("indsock", "supply_markup", ["socket"]), E("switchgear", "supply_markup", ["paired_mcb"])],
    "junction_box_raceway": [E("jb_supply", "supply_markup")],
    "lighting_mgmt_system": [E("lms_supply", "supply_markup")],
    "miscellaneous": [E("misc_supply", "ratio")],
    "point_wiring": [E("cable_unarm", "supply_markup", ["wire1", "wire2", "circuit_wire1", "circuit_wire2"]), E("conduit", "supply_markup", ["conduit"]),
                     E("swsock", "supply_markup", ["switch", "socket", "blank", "plate", "back_box"])],
    "popup_boxes": [E("swsock", "supply_markup", ["switch", "socket1", "socket2", "socket3", "socket4", "blank", "plate"]), E("popup_supply", "ratio")],
    "switches_sockets": [E("swsock", "supply_markup")],
    "wiring_cabling": [E("conduit", "supply_markup", ["conduit"]), E("lug", "supply_markup", ["lug"]), E("gland", "supply_markup", ["gland"]),
                       E("cable_arm", "supply_markup", None, {"insulation": "ARMOURED"}), E("cable_unarm", "supply_markup", None, {"insulation": "UNARMOURED"})],
}
FT2_UID = "rmi-" + hashlib.sha256(("bcs2 pricing input " + FT2_ID).encode()).hexdigest()[:12]


# ---------------------------------------------------------------- worked examples
PLUG = "Plug + Socket in Enclosure Box"
IS63 = {"item": PLUG, "enclosure": "IP44/54 - Splash Proof", "rating": "63A", "pole": "5 Pin / 3P+N+E"}
WIRE = {"material": "COPPER", "insulation": "UNARMOURED", "core": 1, "thickness_sqmm": 150, "runs": 1}
# (category, new golden id, the golden it starts from, attribute overrides, pipelines whose figures it records)
NEW_GOLDENS = [
    ("wiring_cabling", "g6", None, dict(WIRE, conduit_included="Yes", conduit_type="PVC", size_mm=25), ["cable_boq", "cable_bcs"]),
    ("wiring_cabling", "g7", None, dict(WIRE, conduit_included="No"), ["cable_boq", "cable_bcs"]),
    ("popup_boxes", "p2", "p1", {"has_modules": "Yes", "socket1_item": "6A 3-Pin Socket", "socket1_qty": 2.0, "switch_item": "16A 1 WAY SWITCH",
                                 "switch_qty": 1.0, "plate_item": "6M", "plate_qty": 1.0}, ["popup_boq", "popup_bcs"]),
    ("popup_boxes", "p3", "p1", {}, ["popup_boq", "popup_bcs"]),
    ("junction_box_raceway", "j2", None, {"face_mm": 300.0}, ["jb_boq", "jb_bcs"]),
    ("industrial_sockets", "i6", None, dict(IS63, paired_mcb="None"), ["indsock_boq", "indsock_bcs"]),
    ("industrial_sockets", "i7", None, dict(IS63, paired_mcb="63A FP MCB C CURVE"), ["indsock_boq", "indsock_bcs"]),
]
STALE = [("point_wiring", gid) for gid in ("pw1", "pw2", "pw3", "pw4", "pw5")] + [("lighting_mgmt_system", gid) for gid in ("lms2", "lms3")]


def _round(v):
    return round(v, 4) if isinstance(v, float) else v


def refresh_goldens(final):
    """Re-compute the stale examples and compute the new ones THROUGH THE INTERPRETER. Returns the log lines."""
    cfg = {c["category_id"]: c for c in final["category_configs"]}
    runs, at = [], {}
    for cat, gid in STALE:
        g = [x for x in cfg[cat]["goldens"] if x["id"] == gid][0]
        for pid in g["expect"]:
            runs.append({"id": "%s|%s" % (cat, gid), "cat": cat, "pid": pid, "sel": g["attrs"]})
            at[len(runs) - 1] = ("stale", cat, gid, pid, g["expect"][pid])
    fresh = []
    for cat, gid, base, over, pids in NEW_GOLDENS:
        attrs = dict([x for x in cfg[cat]["goldens"] if x["id"] == base][0]["attrs"]) if base else {}
        attrs.update(over)
        g = {"id": gid, "attrs": attrs, "expect": {}, "oracle": "BCS-2 (2026-11-22): computed by the interpreter from this file"}
        fresh.append((cat, g))
        for pid in pids:
            runs.append({"id": "%s|%s" % (cat, gid), "cat": cat, "pid": pid, "sel": attrs})
            at[len(runs) - 1] = ("new", cat, gid, pid, None)
    res = run_interpreter(final, runs)
    lines = []
    for n, r in enumerate(res):
        kind, cat, gid, pid, old = at[n]
        if r["status"] != "ok":
            raise SystemExit("golden %s/%s/%s did not price: %s (%s)" % (cat, gid, pid, r["status"], r["last"]))
        outs = cfg[cat]["pipelines"][pid]["output"]
        got = {k: _round(r["finals"][k]) for k in (old or outs) if k in r["finals"]}
        if kind == "stale":
            g = [x for x in cfg[cat]["goldens"] if x["id"] == gid][0]
            same = all(abs(got[k] - old[k]) <= 0.005 for k in old)
            lines.append("stale %s %s %s: old %s new %s%s" % (cat, gid, pid, old, got, " (unchanged)" if same else ""))
            if not same:
                g["expect"][pid] = got
        else:
            [g for c, g in fresh if c == cat and g["id"] == gid][0]["expect"][pid] = got
            lines.append("new   %s %s %s: %s" % (cat, gid, pid, got))
    for cat, g in fresh:
        cfg[cat]["goldens"].append(g)
    for cat in {c for c, _ in STALE} | {c for c, *_ in NEW_GOLDENS}:
        final["goldens"][cat] = copy.deepcopy(cfg[cat]["goldens"])
    return lines


# ---------------------------------------------------------------- the agreement guard (P2d)
def agree_cases(final):
    """One selection per ACTIVE catalogue item and per price/cost pair that prices it on its own, plus conduit on every cable
    item and a box with modules -- so every PART of a price is exercised (BCS-R1's p2b cases, plus those)."""
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


def agree(final):
    """P2d: the cost of every active item must equal its price with every margin and wastage at zero and every ratio at one, before any
    rounding (owner: equal; rounding up on either side; wastage). Returns (the disagreeing cases, priced cases, cases)."""
    runs = []
    for cat, it, sel in agree_cases(final):
        for price, p_out, cost, c_out in PAIRS[cat]:
            if (it.get("kind") == "termination" and price != "termination_boq") or (it.get("kind") == "cable" and price == "termination_boq"):
                continue
            runs.append({"mode": "neutral", "cat": cat, "price": price, "cost": cost, "pOut": p_out, "cOut": c_out, "sel": sel, "uid": it["item_uid"]})
    out, checked = [], 0
    for r in run_interpreter(final, runs):
        if r["pStatus"] != "ok":
            if r["cStatus"] == "ok" and r["c"]:
                out.append(dict(r, why="the price refuses and the cost does not"))
            continue
        checked += 1
        if r["p"] is None and r["c"] is None:
            continue   # the price carries no supply figure (a CEIG line) and neither does the cost
        if r["cStatus"] != "ok" or r["p"] is None or r["c"] is None or abs(r["p"] - r["c"]) > 0.01:
            out.append(r)
    return out, checked, len(runs)


# ---------------------------------------------------------------- build / agree / load / verify
EDITED = {"wiring_cabling": {"cable_bcs"}, "popup_boxes": {"popup_bcs"}, "junction_box_raceway": {"jb_bcs"}, "industrial_sockets": {"indsock_bcs"},
          "db_switchgear": {"db_buildup_bcs"}, "switches_sockets": {"swsock_bcs"}}


def build(out, site):
    frappe = _connect(site)
    from nirmaan_stack.services.boq_rate_master import config_validation
    from nirmaan_stack.services.boq_rate_master.loader import _validate_items, _validate_one_config
    raw = open(V72, "rb").read()
    prev = json.loads(raw.decode("utf-8"))
    if _dump(prev).encode("utf-8") != raw:
        raise SystemExit("re-dumping v72 does not reproduce its bytes")
    final, log = transform(prev)
    lines = refresh_goldens(final)
    for x in log + lines:
        print("  EDIT", x)

    # BYTE-IDENTITY: every item unchanged and in order (+ exactly the Rs 42 input), every pipeline but the edited ones unchanged
    assert [_canon(a) for a in prev["items"]] == [_canon(b) for b in final["items"][:-1]] and final["items"][-1]["item_uid"] == FT2_UID
    assert FT2_UID not in {i["item_uid"] for i in prev["items"]}
    for x, y in zip(prev["category_configs"], final["category_configs"]):
        cat = x["category_id"]
        assert cat == y["category_id"]
        for pid, pl in x["pipelines"].items():
            if pid in EDITED.get(cat, ()):
                continue
            assert _canon(pl) == _canon(y["pipelines"][pid]), (cat, pid)
        assert set(y["pipelines"]) - set(x["pipelines"]) == ({"jb_bcs"} if cat == "junction_box_raceway" else {"indsock_bcs"} if cat == "industrial_sockets" else set()), cat
        for k in set(x) | set(y):
            if k in ("pipelines", "goldens", "bcs_default_margin", "summary_inputs"):
                continue
            assert _canon(x.get(k)) == _canon(y.get(k)), (cat, k)
    assert [k for k in final] == [k for k in prev]
    print("IDENTITY: items unchanged %d + 1 new; pipelines edited %s" % (len(prev["items"]), sorted(p for v in EDITED.values() for p in v)))

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
    # the previous file's own notes carry version tokens; a token this mint ADDS is refused (h07)
    tokens = sorted(set(re.findall(r"v\d+", text)) - set(re.findall(r"v\d+", raw.decode("utf-8"))))
    if tokens:
        raise SystemExit("the asset text carries version-like tokens v72 does not %r (h07)" % tokens)
    open(out, "w", encoding="utf-8", newline="").write(text)
    print("candidate written:", out, "| items", len(final["items"]), "| configs", len(final["category_configs"]),
          "| sha256", hashlib.sha256(text.encode("utf-8")).hexdigest())
    frappe.destroy()


def run_agree(candidate, site):
    final = json.load(open(candidate, encoding="utf-8"))
    bad, checked, total = agree(final)
    print("AGREEMENT GUARD: %d cases, %d priced on both sides, %d disagree" % (total, checked, len(bad)))
    for r in bad[:15]:
        print("   ", r)
    if bad:
        raise SystemExit("the mint refuses: a stated cost does not agree with BoQ supply / (1 + margin)")


def load(candidate, site):
    run_agree(candidate, site)
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
    run_agree(candidate, site)
    frappe = _connect(site)
    asset = json.load(open(candidate, encoding="utf-8"))
    J = lambda v: json.loads(v) if isinstance(v, str) else v
    li = frappe.db.sql('select item_uid, kind, brand, unit, attributes, rates from "tabBoQ Rate Master Item" where active=1 and discipline=%s', ("Electrical",), as_dict=True)
    lc = frappe.db.sql('select category_id, config from "tabBoQ Rate Category Config" where active=1 and discipline=%s', ("Electrical",), as_dict=True)
    L = {r["item_uid"]: {"kind": r["kind"], "brand": r["brand"] or None, "unit": r["unit"] or None, "attributes": J(r["attributes"]), "rates": J(r["rates"])} for r in li}
    LC = {r["category_id"]: J(r["config"]) for r in lc}
    A = {r["item_uid"]: {"kind": r["kind"], "brand": r.get("brand") or None, "unit": r.get("unit") or None, "attributes": r["attributes"], "rates": r["rates"]} for r in asset["items"]}
    AC = {c["category_id"]: dict(c, discipline="Electrical", goldens=asset["goldens"].get(c["category_id"], c.get("goldens"))) for c in asset["category_configs"]}
    LC = {k: v for k, v in LC.items()}
    out = {"items_live": len(L), "items_file": len(A), "configs_live": len(LC), "configs_file": len(AC),
           "items_missing": sorted(set(A) - set(L)), "items_extra": sorted(set(L) - set(A)),
           "items_differing": sorted(u for u in set(L) & set(A) if _canon(L[u]) != _canon(A[u])),
           "configs_differing": sorted(c for c in set(LC) | set(AC) if _canon(LC.get(c)) != _canon(AC.get(c))),
           "sha_items_live": _sha16([[u, L[u]] for u in sorted(L)]), "sha_items_file": _sha16([[u, A[u]] for u in sorted(A)])}
    out["VERDICT"] = "EQUAL" if not (out["items_missing"] or out["items_extra"] or out["items_differing"] or out["configs_differing"]) else "DIFFER"
    print(json.dumps(out, indent=1, sort_keys=True))
    frappe.destroy()
    if out["VERDICT"] != "EQUAL":
        raise SystemExit("live != file")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("phase", choices=["build", "agree", "load", "verify"])
    ap.add_argument("--candidate", default=V73)
    ap.add_argument("--site", default=os.environ.get("ENV_SYNC_SITE", "localhost"))
    a = ap.parse_args()
    if a.phase == "build":
        build(a.candidate, a.site)
    elif a.phase == "agree":
        run_agree(a.candidate, a.site)
    elif a.phase == "load":
        load(a.candidate, a.site)
    else:
        verify(a.candidate, a.site)
