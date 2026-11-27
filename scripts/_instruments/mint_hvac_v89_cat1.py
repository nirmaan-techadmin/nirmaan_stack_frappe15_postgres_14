"""CAT-1 (2026-11-26, desktop; the first build slice of the catalogue-link fix) -- MINT HVAC v89 = v88 + ONLY the edits of ONE file,
frontend/.../__fixtures__/cat1Edits.json (10 edits):
  R5 (owner 2026-11-26 00:13 "ok for both") Valve Package `unstocked_answers` {operation: ["On-Off"]} -- the deliberate unstocked answer
     declared, so the rebuilt list keeps it and the reference gate accepts it;
  R2 (owner 2026-11-26 00:06 / 00:10) the 5 VAV share parts' `sku` by {item_uid, attr} (the name read live; CAT-D1 E2 R-A);
  R6 (owner 2026-11-26 01:14 "2 ok"; CAT-D0 D8) the four ruled rules-page lines as `rules_page_line` (ADP neck_mm,
     stream_heading_default[0], companion_items[0]; Piping sheet_heading_notes[0]).

  items     NONE changed: every item byte-identical to v88 (no rate, markup, name or text of any item moves).
  configs   hvac_valve_package, hvac_vav_box, hvac_adp, hvac_piping only. Every other config byte-identical.
Every edit names what it replaces and is refused when v88 does not hold it (a new key: `from` null).
THE GATE: `catalogue_gate.reference_problems` on the candidate = 0 REFUSE (and v88 itself = exactly the undeclared On-Off).
REQUESTS: every eligible category's whole request (`_group_context` -> `batch_prompt_content`) built from the candidate THROUGH THE
CAT-1 MERGE (rebuilt lists + fill) is byte-identical to the same request built from v88's RAW configs (the c4a3d5fa1 read path).

Runs IN THE CONTAINER under the bench's python. Phases: build (v88 file -> the candidate; NO database write), load, verify.
The candidate path is REQUIRED (no default into the repo tree).
Usage (container, from frappe-bench): env/bin/python -I <this> build|load|verify --candidate P
"""
import argparse
import copy
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mint_hvac_v79_vav2b1 import APP, DATA, _canon, _connect, _dump, _sha16, load, verify  # noqa: E402  (the same load / verify)
from mint_hvac_v82_vav2c1 import apply_config  # noqa: E402  (the same edit semantics)

V88 = os.path.join(DATA, "rate_master_hvac_all_v88.json")  # the base of v89
EDITS = os.path.join(APP, "frontend/src/pages/boq-wizard/rate-helper/__fixtures__/cat1Edits.json")


def _request_texts(stored, cfgs, extraction):
    """{category_id: the whole request content} for every eligible category, from the given config map (no model call)."""
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


def build(out):
    frappe = _connect()
    from nirmaan_stack.services.boq_rate_master import catalogue_gate, catalogue_lists, config_validation, extraction
    from nirmaan_stack.services.boq_rate_master.loader import _validate_items, _validate_one_config
    raw = open(V88, "rb").read()
    prev = json.loads(raw.decode("utf-8"))
    if _dump(prev).encode("utf-8") != raw:
        raise SystemExit("re-dumping v88 does not reproduce its bytes")
    K = json.load(open(EDITS, encoding="utf-8"))
    assert K["pricing_inputs"] == {}, "v89 changes no item"
    final = copy.deepcopy(prev)
    by_cat = {}
    for e in K["configs"]:
        by_cat.setdefault(e["c"], []).append(e)
    known = {c["category_id"] for c in prev["category_configs"]}
    assert set(by_cat) <= known, set(by_cat) - known
    assert set(by_cat) == {"hvac_valve_package", "hvac_vav_box", "hvac_adp", "hvac_piping"}, sorted(by_cat)
    final["category_configs"] = [apply_config(c, by_cat.get(c["category_id"], [])) for c in prev["category_configs"]]

    # ITEM BY ITEM: every item byte-identical, in order
    assert _canon(prev["items"]) == _canon(final["items"])
    print("items %d; changed 0; rates changed 0" % len(final["items"]))
    # KEY BY KEY: undoing every edit gives v88's config back, byte for byte; a config with no edit is unchanged
    for a, b in zip(prev["category_configs"], final["category_configs"]):
        back = apply_config(b, [dict(e, **{"from": e["to"], "to": e["from"]}) for e in reversed(by_cat.get(a["category_id"], []))])
        assert _canon(back) == _canon(a), a["category_id"]
        assert (_canon(a) == _canon(b)) == (a["category_id"] not in by_cat), a["category_id"]
    print("configs changed:", {c: len(v) for c, v in sorted(by_cat.items())}, "| unchanged:", sorted(known - set(by_cat)))
    assert list(final.keys()) == list(prev.keys())

    _validate_items(final["items"])
    stored = [dict(c, discipline=final["discipline"]) for c in final["category_configs"]]
    for n, c in enumerate(stored):
        try:
            _validate_one_config(c, "category_configs[%d]" % n)
            config_validation._validate_config(c)
        except Exception as e:
            raise SystemExit("config %s refused: %s" % (c["category_id"], e))
    problems = (config_validation.delegated_section_problems(stored, final["items"]) + config_validation.extras_problems(stored, final["items"])
                + config_validation.scope_problems(stored, final["items"]))
    if problems:
        raise SystemExit("cross-category check refuses: %r" % problems)

    # THE GATE: v88 as committed refuses exactly the undeclared On-Off; the candidate refuses nothing
    stored_base = [dict(c, discipline=prev["discipline"]) for c in prev["category_configs"]]
    g_base = [p for p in catalogue_gate.reference_problems(stored_base, prev["items"], "HVAC") if p["severity"] == "REFUSE"]
    g_new = catalogue_gate.reference_problems(stored, final["items"], "HVAC")
    refused = [p for p in g_new if p["severity"] == "REFUSE"]
    print("GATE v88: %d refusal(s): %s" % (len(g_base), [catalogue_gate.format_problem(p) for p in g_base]))
    print("GATE v89: %d refusal(s), %d info line(s)" % (len(refused), len(g_new) - len(refused)))
    assert [(p["config"], p["path"]) for p in g_base] == [("hvac_valve_package", "list_spec.attribute_definitions[operation].values")], g_base
    if refused:
        raise SystemExit("the reference gate refuses the candidate: %r" % [catalogue_gate.format_problem(p) for p in refused])

    # THE LISTS: the candidate's served configs (rebuilt lists + fill) equal its stored configs, every one
    built = catalogue_lists.build([dict(i, active=1) for i in final["items"]], stored)
    merged = {c["category_id"]: catalogue_lists.merge_config(c, built, "HVAC") for c in stored}
    moved = sorted(cid for c in stored for cid in [c["category_id"]] if merged[cid] is not c)
    assert moved == [], moved
    print("served = stored on every config (rebuilt lists equal; no placeholder) | stamp", built["stamp"])

    # REQUESTS: candidate through the merge == v88 raw (the c4a3d5fa1 read path), every eligible category, whole request text
    cfgs_base = {(prev["discipline"], c["category_id"]): c for c in stored_base}
    cfgs_new = {(final["discipline"], c["category_id"]): merged[c["category_id"]] for c in stored}
    eligible = sorted(c["category_id"] for c in stored if extraction.config_is_eligible(c, cfgs_new))
    assert eligible == sorted(c["category_id"] for c in stored_base if extraction.config_is_eligible(c, cfgs_base)), eligible
    r_base, r_new = _request_texts(stored_base, cfgs_base, extraction), _request_texts(stored, cfgs_new, extraction)
    for k in sorted(r_new):
        print("   request sha16 %-20s before %s after %s" % (k, hashlib.sha256(r_base[k].encode()).hexdigest()[:16],
                                                        hashlib.sha256(r_new[k].encode()).hexdigest()[:16]))
    diff = sorted(k for k in set(r_base) | set(r_new) if r_base.get(k) != r_new.get(k))
    assert diff == [], diff
    print("MODEL REQUESTS: %d eligible HVAC categories; changed %r, v88 -> v89" % (len(r_new), diff))

    text = _dump(final)
    tokens = sorted({t for t in re.findall(r"v\d+", text.replace(json.dumps(final.get("source_workbook") or "", ensure_ascii=False), '""'))})
    if tokens:
        raise SystemExit("the asset text carries version-like tokens %r (h07)" % tokens)
    open(out, "w", encoding="utf-8", newline="").write(text)
    print("candidate written:", out, "| items", len(final["items"]), "| configs", len(final["category_configs"]),
          "| sha256", hashlib.sha256(text.encode("utf-8")).hexdigest())
    print("per-config sha16 v89:", {c["category_id"]: _sha16(c) for c in final["category_configs"]})
    frappe.destroy()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("phase", choices=["build", "load", "verify"])
    ap.add_argument("--candidate", required=True)
    a = ap.parse_args()
    if a.phase == "build":
        build(a.candidate)
    elif a.phase == "load":
        load(a.candidate)
    else:
        verify(a.candidate)
