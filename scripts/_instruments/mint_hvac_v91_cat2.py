"""CAT-2 (2026-11-27, desktop; the third build slice of the catalogue-link fix) -- MINT HVAC v91 = v90 + ONLY the edits of ONE file,
frontend/.../__fixtures__/cat2Edits.json: a `list_spec.code_targets` block on four configs naming, by role, the catalogue values the code
rules picked from typed constants until now (owner 2026-11-26 00:10 "we can combine your prviou ssolution and this for wider coverage",
01:16 "yes proceed" -- CAT-2 = "HVAC code words + family picker"; ANSWER to CAT2-4 QR-FORM: role -> {attr, value | values, section}).

  items     NONE changed: every item byte-identical to v90.
  configs   only the new key `list_spec.code_targets` on hvac_insulation / hvac_piping / hvac_vrf / hvac_valve_package; nothing else.
PROOFS (build phase, no database write, NO model call):
  KEY BY KEY  every candidate config minus `list_spec.code_targets` = v90's config, byte for byte; undoing every edit gives v90 back.
  GATE        `catalogue_gate.reference_problems` on v90 and on the candidate = 0 REFUSE (every code target is carried by an active SKU of
              its scope, the STRICT check).
  SERVED      every candidate config through THE ONE MERGE, less the new key, = v90's config through the same merge, byte for byte.
  G-PROSE     the typed multi-word mentions per path are unchanged (a code target IS a value: a reference, not prose).
  REQUESTS    every eligible HVAC category's whole request through the merge = v90's, byte for byte; no '{{'.
Runs IN THE CONTAINER under the bench's python. Phases: build (v90 file -> the candidate), load, verify. The candidate path is
REQUIRED (no default into the repo tree).
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
from mint_hvac_v82_vav2c1 import apply_config  # noqa: E402  (the same edit semantics: `from` null = a new key)
from mint_hvac_v89_cat1 import _request_texts  # noqa: E402  (the same request builder)

V90 = os.path.join(DATA, "rate_master_hvac_all_v90.json")  # the base of v91
EDITS = os.path.join(APP, "frontend/src/pages/boq-wizard/rate-helper/__fixtures__/cat2Edits.json")
CONFIGS = {"hvac_insulation", "hvac_piping", "hvac_vrf", "hvac_valve_package"}
PATH = ["list_spec", "code_targets"]


def _without(cfg):
    c = copy.deepcopy(cfg)
    (c.get("list_spec") or {}).pop("code_targets", None)
    return c


def build(out):
    frappe = _connect()
    from nirmaan_stack.services.boq_rate_master import catalogue_gate, catalogue_lists, config_validation, extraction
    from nirmaan_stack.services.boq_rate_master.loader import _validate_items, _validate_one_config
    raw = open(V90, "rb").read()
    prev = json.loads(raw.decode("utf-8"))
    if _dump(prev).encode("utf-8") != raw:
        raise SystemExit("re-dumping v90 does not reproduce its bytes")
    K = json.load(open(EDITS, encoding="utf-8"))
    assert K["pricing_inputs"] == {}, "v91 changes no item"
    by_cat = {}
    for e in K["configs"]:
        assert e["p"] == PATH and e["from"] is None and isinstance(e["to"], dict) and e["to"], (e["c"], e["p"])
        by_cat.setdefault(e["c"], []).append(e)
    assert set(by_cat) == CONFIGS and all(len(v) == 1 for v in by_cat.values()), sorted(by_cat)
    known = {c["category_id"] for c in prev["category_configs"]}
    assert all(PATH[-1] not in (c.get("list_spec") or {}) for c in prev["category_configs"]), "v90 already carries code_targets"
    final = copy.deepcopy(prev)
    final["category_configs"] = [apply_config(c, by_cat.get(c["category_id"], [])) for c in prev["category_configs"]]
    roles = sum(len(e["to"]) for e in K["configs"])
    print("edits: %d configs / %d roles (file counts %s)" % (len(K["configs"]), roles, K["counts"]))
    assert (len(K["configs"]), roles) == (K["counts"]["configs"], K["counts"]["roles"])

    # ITEM BY ITEM: every item byte-identical, in order
    assert _canon(prev["items"]) == _canon(final["items"])
    print("items %d; changed 0; rates changed 0" % len(final["items"]))
    # KEY BY KEY: less the new key every config = v90's; undoing every edit gives v90 back; a config with no edit is unchanged
    for a, b in zip(prev["category_configs"], final["category_configs"]):
        assert _canon(_without(b)) == _canon(a), a["category_id"]
        back = apply_config(b, [dict(e, **{"from": e["to"], "to": e["from"]}) for e in reversed(by_cat.get(a["category_id"], []))])
        assert _canon(back) == _canon(a), a["category_id"]
        assert (_canon(a) == _canon(b)) == (a["category_id"] not in by_cat), a["category_id"]
    print("configs changed:", sorted(by_cat), "| unchanged:", sorted(known - set(by_cat)))
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

    # THE GATE: v90 and the candidate refuse nothing; every code target is carried (STRICT)
    stored_base = [dict(c, discipline=prev["discipline"]) for c in prev["category_configs"]]
    g_base = [p for p in catalogue_gate.reference_problems(stored_base, prev["items"], "HVAC") if p["severity"] == "REFUSE"]
    g_new = catalogue_gate.reference_problems(stored, final["items"], "HVAC")
    refused = [p for p in g_new if p["severity"] == "REFUSE"]
    by_id = {c["category_id"]: c for c in stored}
    n_refs = sum(1 for c in stored for r in catalogue_gate.code_target_refs(c, by_id) if r[4] is None)
    print("GATE v90: %d refusal(s) | v91: %d refusal(s), %d info line(s); code-target references checked: %d"
          % (len(g_base), len(refused), len(g_new) - len(refused), n_refs))
    if g_base or refused:
        raise SystemExit("the reference gate refuses: %r" % [catalogue_gate.format_problem(p) for p in g_base + refused])

    # SERVED: every candidate config through THE ONE MERGE, less the new key, = v90's through the same merge
    built = catalogue_lists.build([dict(i, active=1) for i in final["items"]], stored)
    built_base = catalogue_lists.build([dict(i, active=1) for i in prev["items"]], stored_base)
    merged = {c["category_id"]: catalogue_lists.merge_config(c, built, "HVAC") for c in stored}
    merged_base = {c["category_id"]: catalogue_lists.merge_config(c, built_base, "HVAC") for c in stored_base}
    differ = sorted(cid for cid in merged if _canon(_without(merged[cid])) != _canon(merged_base[cid]))
    assert differ == [], differ
    carried = sorted(cid for cid in merged if PATH[-1] in (merged[cid].get("list_spec") or {}))
    assert carried == sorted(CONFIGS), carried
    print("SERVED v91 (less code_targets) = SERVED v90 on all %d configs, byte for byte; served with code_targets: %s | stamp %s -> %s"
          % (len(stored), carried, built_base["stamp"], built["stamp"]))

    # G-PROSE: the typed multi-word mentions per path are unchanged
    p_old = catalogue_gate.prose_mentions(stored_base, prev["items"])
    p_new = catalogue_gate.prose_mentions(stored, final["items"])
    assert p_old == p_new, sorted(set(p_new) ^ set(p_old))
    print("G-PROSE HVAC: paths %d -> %d, mentions %d -> %d (unchanged)" % (len(p_old), len(p_new), sum(sum(d.values()) for d in p_old.values()),
                                                                      sum(sum(d.values()) for d in p_new.values())))

    # REQUESTS: candidate through the merge == v90 through the merge, every eligible category, whole request text
    cfgs_base = {(prev["discipline"], cid): merged_base[cid] for cid in merged_base}
    cfgs_new = {(final["discipline"], cid): merged[cid] for cid in merged}
    eligible = sorted(c["category_id"] for c in stored if extraction.config_is_eligible(c, cfgs_new))
    assert eligible == sorted(c["category_id"] for c in stored_base if extraction.config_is_eligible(c, cfgs_base)), eligible
    r_base, r_new = _request_texts(stored_base, cfgs_base, extraction), _request_texts(stored, cfgs_new, extraction)
    for k in sorted(r_new):
        print("   request sha16 %-20s before %s after %s" % (k, hashlib.sha256(r_base[k].encode()).hexdigest()[:16],
                                                        hashlib.sha256(r_new[k].encode()).hexdigest()[:16]))
    diff = sorted(k for k in set(r_base) | set(r_new) if r_base.get(k) != r_new.get(k))
    assert diff == [], diff
    raw_braces = sorted(k for k, t in r_new.items() if "{{" in t)
    assert raw_braces == [], raw_braces
    print("MODEL REQUESTS: %d eligible HVAC categories; changed %r, v90 -> v91; no '{{' in any" % (len(r_new), diff))

    text = _dump(final)
    tokens = sorted({t for t in re.findall(r"v\d+", text.replace(json.dumps(final.get("source_workbook") or "", ensure_ascii=False), '""'))})
    if tokens:
        raise SystemExit("the asset text carries version-like tokens %r (h07)" % tokens)
    open(out, "w", encoding="utf-8", newline="").write(text)
    print("candidate written:", out, "| items", len(final["items"]), "| configs", len(final["category_configs"]),
          "| sha256", hashlib.sha256(text.encode("utf-8")).hexdigest())
    print("per-config sha16 v91:", {c["category_id"]: _sha16(c) for c in final["category_configs"]})
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
