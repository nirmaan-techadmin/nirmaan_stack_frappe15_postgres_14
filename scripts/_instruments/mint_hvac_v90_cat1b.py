"""CAT-1b (2026-11-26, desktop; the second build slice of the catalogue-link fix) -- MINT HVAC v90 = v89 + ONLY the edits of ONE file,
frontend/.../__fixtures__/cat1bEdits.json: the HVAC WORDING names catalogue values through {{cat:<attr>=<value>}} placeholders
(owner 2026-11-26 01:47 "a a a ok", QR-C-1 (a): "converts the 533"; 11:15 "a", QR-C-2 (a): the 237 prose texts -- 518 placeholders --
are converted and the 15 texts that ARE a catalogue value stay typed, references the gate checks; + the one rules-page line v89 added
that names one, 2 placeholders).

  items     NONE changed: every item byte-identical to v89.
  configs   only the edited TEXTS change. Each edit names the v89 text it replaces (refused when v89 does not hold it).
PROOFS (build phase, no database write, NO model call):
  PER TEXT    the product fill (`catalogue_lists.fill_text`, v89's items) of every converted text = v89's text, byte for byte.
  SERVED      every candidate config through THE ONE MERGE (`catalogue_lists.merge_config`: rebuilt lists + fill) = v89's stored config,
              byte for byte -- the conversion is invisible to every reader of the served config.
  UNDO        undoing every edit gives v89's config back; a config with no edit is unchanged.
  GATE        `catalogue_gate.reference_problems` on the candidate = 0 REFUSE (every placeholder resolves).
  G-PROSE     the multi-word typed mentions per path only go DOWN (prints the new counts for catalogue_prose_allowlist.json).
  REQUESTS    every eligible HVAC category's whole request through the merge = the same request from v89's raw configs.
Runs IN THE CONTAINER under the bench's python. Phases: build (v89 file -> the candidate), load, verify. The candidate path is
REQUIRED (no default into the repo tree).
Usage (container, from frappe-bench): env/bin/python -I <this> build|load|verify --candidate P [--prose-out P]
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
from mint_hvac_v89_cat1 import _request_texts  # noqa: E402  (the same request builder)

V89 = os.path.join(DATA, "rate_master_hvac_all_v89.json")  # the base of v90
EDITS = os.path.join(APP, "frontend/src/pages/boq-wizard/rate-helper/__fixtures__/cat1bEdits.json")
CONFIGS = {"hvac_adp", "hvac_ducting", "hvac_insulation", "hvac_misc", "hvac_piping", "hvac_sensors", "hvac_valve_package", "hvac_vav_box",
           "hvac_vrf"}


def _at(cfg, path):
    node = cfg
    for p in path:
        node = node[p]
    return node


def build(out, prose_out=None):
    frappe = _connect()
    from nirmaan_stack.services.boq_rate_master import catalogue_gate, catalogue_lists, config_validation, extraction
    from nirmaan_stack.services.boq_rate_master.loader import _validate_items, _validate_one_config
    raw = open(V89, "rb").read()
    prev = json.loads(raw.decode("utf-8"))
    if _dump(prev).encode("utf-8") != raw:
        raise SystemExit("re-dumping v89 does not reproduce its bytes")
    K = json.load(open(EDITS, encoding="utf-8"))
    assert K["pricing_inputs"] == {}, "v90 changes no item"
    by_cat = {}
    for e in K["configs"]:
        assert isinstance(e["from"], str) and isinstance(e["to"], str) and e["from"] != e["to"], (e["c"], e["p"])
        assert "{{" not in e["from"] and catalogue_lists.PLACEHOLDER_RE.search(e["to"]), (e["c"], e["p"])
        by_cat.setdefault(e["c"], []).append(e)
    known = {c["category_id"] for c in prev["category_configs"]}
    assert set(by_cat) == CONFIGS, sorted(by_cat)
    final = copy.deepcopy(prev)
    final["category_configs"] = [apply_config(c, by_cat.get(c["category_id"], [])) for c in prev["category_configs"]]
    n_ph = sum(len(catalogue_lists.PLACEHOLDER_RE.findall(e["to"])) for e in K["configs"])
    print("edits %d texts / %d placeholders (file counts %s)" % (len(K["configs"]), n_ph, {k: v for k, v in K["counts"].items() if k != "kept_whole_value"}))
    assert (len(K["configs"]), n_ph) == (K["counts"]["texts"], K["counts"]["placeholders"])

    # ITEM BY ITEM: every item byte-identical, in order
    assert _canon(prev["items"]) == _canon(final["items"])
    print("items %d; changed 0; rates changed 0" % len(final["items"]))
    # KEY BY KEY: undoing every edit gives v89's config back; a config with no edit is unchanged
    for a, b in zip(prev["category_configs"], final["category_configs"]):
        back = apply_config(b, [dict(e, **{"from": e["to"], "to": e["from"]}) for e in reversed(by_cat.get(a["category_id"], []))])
        assert _canon(back) == _canon(a), a["category_id"]
        assert (_canon(a) == _canon(b)) == (a["category_id"] not in by_cat), a["category_id"]
    print("configs changed:", {c: len(v) for c, v in sorted(by_cat.items())}, "| unchanged:", sorted(known - set(by_cat)))
    assert list(final.keys()) == list(prev.keys())

    # PER TEXT: the product fill of each converted text = v89's text, byte for byte
    stored = [dict(c, discipline=final["discipline"]) for c in final["category_configs"]]
    built = catalogue_lists.build([dict(i, active=1) for i in final["items"]], stored)
    cfg_new = {c["category_id"]: c for c in final["category_configs"]}
    bad = []
    for e in K["configs"]:
        probs = []
        got = catalogue_lists.fill_text(_at(cfg_new[e["c"]], e["p"]), built, probs, "%s %r" % (e["c"], e["p"]))
        if got != e["from"] or probs:
            bad.append((e["c"], e["p"], probs))
    assert not bad, bad[:5]
    print("PER TEXT: %d / %d converted texts fill back byte-equal to v89's (0 problems)" % (len(K["configs"]), len(K["configs"])))

    _validate_items(final["items"])
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

    # THE GATE: v89 and the candidate refuse nothing; every placeholder resolves
    stored_base = [dict(c, discipline=prev["discipline"]) for c in prev["category_configs"]]
    g_base = [p for p in catalogue_gate.reference_problems(stored_base, prev["items"], "HVAC") if p["severity"] == "REFUSE"]
    g_new = catalogue_gate.reference_problems(stored, final["items"], "HVAC")
    refused = [p for p in g_new if p["severity"] == "REFUSE"]
    print("GATE v89: %d refusal(s) | v90: %d refusal(s), %d info line(s)" % (len(g_base), len(refused), len(g_new) - len(refused)))
    if g_base or refused:
        raise SystemExit("the reference gate refuses: %r" % [catalogue_gate.format_problem(p) for p in g_base + refused])

    # SERVED: every candidate config through THE ONE MERGE = v89's stored config, byte for byte
    merged = {c["category_id"]: catalogue_lists.merge_config(c, built, "HVAC") for c in stored}
    differ = sorted(c["category_id"] for c in stored_base if _canon(merged[c["category_id"]]) != _canon(c))
    assert differ == [], differ
    filled_moved = sorted(cid for cid in merged if merged[cid] is not [c for c in stored if c["category_id"] == cid][0])
    print("SERVED v90 = STORED v89 on all %d configs, byte for byte (filled: %s) | stamp %s" % (len(stored), filled_moved, built["stamp"]))
    assert filled_moved == sorted(CONFIGS), filled_moved

    # G-PROSE: the typed multi-word mentions per path only go DOWN
    p_old = catalogue_gate.prose_mentions(stored_base, prev["items"])
    p_new = catalogue_gate.prose_mentions(stored, final["items"])
    up = [(k, v, n) for k, d in p_new.items() for v, n in d.items() if n > (p_old.get(k) or {}).get(v, 0)]
    assert up == [], up
    print("G-PROSE HVAC: paths %d -> %d, mentions %d -> %d (none up)" % (len(p_old), len(p_new), sum(sum(d.values()) for d in p_old.values()),
                                                                     sum(sum(d.values()) for d in p_new.values())))
    if prose_out:
        json.dump({"v89": p_old, "v90": p_new}, open(prose_out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # REQUESTS: candidate through the merge == v89 raw, every eligible category, whole request text
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
    raw_braces = sorted(k for k, t in r_new.items() if "{{" in t)
    assert raw_braces == [], raw_braces
    print("MODEL REQUESTS: %d eligible HVAC categories; changed %r, v89 -> v90; no '{{' in any" % (len(r_new), diff))

    text = _dump(final)
    tokens = sorted({t for t in re.findall(r"v\d+", text.replace(json.dumps(final.get("source_workbook") or "", ensure_ascii=False), '""'))})
    if tokens:
        raise SystemExit("the asset text carries version-like tokens %r (h07)" % tokens)
    open(out, "w", encoding="utf-8", newline="").write(text)
    print("candidate written:", out, "| items", len(final["items"]), "| configs", len(final["category_configs"]),
          "| sha256", hashlib.sha256(text.encode("utf-8")).hexdigest())
    print("per-config sha16 v90:", {c["category_id"]: _sha16(c) for c in final["category_configs"]})
    frappe.destroy()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("phase", choices=["build", "load", "verify"])
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--prose-out")
    a = ap.parse_args()
    if a.phase == "build":
        build(a.candidate, a.prose_out)
    elif a.phase == "load":
        load(a.candidate)
    else:
        verify(a.candidate)
