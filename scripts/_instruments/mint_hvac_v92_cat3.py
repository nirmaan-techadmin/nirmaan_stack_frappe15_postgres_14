"""CAT-3 (2026-11-28, desktop; the fourth build slice of the catalogue-link fix) -- MINT HVAC v92 = v91 + ONLY:
  (1) two one-item facts moved to their items' own notes (ANSWER to CAT3-3 QR-NOTE (a) + ANSWER to CAT3-8 QR-NOTE-2 (a)):
      the Automatic Air Vent's single price (hvac_valve_package text_notes[3].line) and the Pressure Gauge's own fittings
      (hvac_misc text_notes[1].rule_line); each config string becomes `{{note:<item_uid>}}` and the item carries the words;
  (2) `labels` emitted on every item, made by the label rule from the item's own values (CAT-D1 E3 L3; verified at load).
The edits are declared in ONE file, frontend/.../__fixtures__/cat3Edits.json (phase `edits` writes it from v91 through the served fill,
so no word is typed here; `build` refuses a fixture that differs).

PROOFS (build phase, no database write, NO model call):
  ITEMS       every item less `labels` / `item_notes` = v91's, byte for byte, in order; labels = the rule on every item (0 flags);
              exactly the two declared items carry a note.
  KEY BY KEY  every config = v91's except the two declared strings; undoing them gives v91 back.
  SERVED      every config through THE ONE MERGE = v91's through the same merge, BYTE FOR BYTE (the panel, the Calculator and the
              rules page show the same words: the note fill gives back the words the placeholder replaced).
  GATE        `catalogue_gate.reference_problems` on v91 and on the candidate = 0 REFUSE (the note references resolve).
  G-PROSE     the typed multi-word mentions per path, before / after (QR-PROSE: only HVAC entries the two moves empty may go).
  REQUESTS    every eligible HVAC category's whole request through the merge = v91's, byte for byte; no '{{'.
Runs IN THE CONTAINER under the bench's python. Phases: edits | build | load | verify. The candidate path is REQUIRED.
Usage (container, from frappe-bench): env/bin/python -I <this> edits|build|load|verify --candidate P
"""
import argparse
import copy
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mint_hvac_v79_vav2b1 import APP, DATA, _canon, _connect, _dump, _sha16, load  # noqa: E402  (the same load)
from mint_hvac_v79_vav2b1 import verify as verify_items_configs  # noqa: E402
from mint_hvac_v89_cat1 import _request_texts  # noqa: E402  (the same request builder)

V91 = os.path.join(DATA, "rate_master_hvac_all_v91.json")  # the base of v92
EDITS = os.path.join(APP, "frontend/src/pages/boq-wizard/rate-helper/__fixtures__/cat3Edits.json")
# (category, path, the item the fact is about) -- QR-NOTE-2 (a): only the two true one-item facts
MOVES = (
    ("hvac_valve_package", ["list_spec", "pricing", "text_notes", 3, "line"], "rmi-317efcac46be"),
    ("hvac_misc", ["list_spec", "pricing", "text_notes", 1, "rule_line"], "rmi-22a6ddc183f9"),
)


def _at(node, path):
    for p in path:
        node = node[p]
    return node


def _set(node, path, value):
    for p in path[:-1]:
        node = node[p]
    node[path[-1]] = value


def _base():
    raw = open(V91, "rb").read()
    prev = json.loads(raw.decode("utf-8"))
    if _dump(prev).encode("utf-8") != raw:
        raise SystemExit("re-dumping v91 does not reproduce its bytes")
    return prev


def edits():
    """Write the edits fixture from v91: each config string's FILLED words (the served fill) become the item's note."""
    frappe = _connect()
    from nirmaan_stack.services.boq_rate_master import catalogue_lists
    prev = _base()
    stored = [dict(c, discipline=prev["discipline"]) for c in prev["category_configs"]]
    built = catalogue_lists.build([dict(i, active=1) for i in prev["items"]], stored)
    by_id = {c["category_id"]: c for c in prev["category_configs"]}
    uids = {i["item_uid"] for i in prev["items"]}
    out = {"_about": "CAT-3 HVAC v92: the two one-item facts moved to their items' notes (QR-NOTE (a), QR-NOTE-2 (a)) and the labels "
                     "emitted. `from` = v91's string, `to` = the placeholder, `item_notes` = the words the served fill gave on v91.",
           "items": {}, "configs": [], "labels": "every item: catalogue_labels.labels_for(kind, attributes)[0]", "counts": {}}
    for cid, path, uid in MOVES:
        assert uid in uids, uid
        frm = _at(by_id[cid], path)
        assert isinstance(frm, str) and "{{note:" not in frm, (cid, path)
        problems = []
        words = catalogue_lists.fill_text(frm, built, problems)
        assert not problems, problems
        out["items"][uid] = {"item_notes": words}
        out["configs"].append({"c": cid, "p": path, "from": frm, "to": "{{note:%s}}" % uid})
    out["counts"] = {"items_noted": len(out["items"]), "configs": len(out["configs"])}
    open(EDITS, "w", encoding="utf-8", newline="\n").write(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    print("edits written:", EDITS, json.dumps(out, ensure_ascii=False)[:600])
    frappe.destroy()


def build(out):
    frappe = _connect()
    from nirmaan_stack.services.boq_rate_master import catalogue_gate, catalogue_labels, catalogue_lists, config_validation, extraction
    from nirmaan_stack.services.boq_rate_master.loader import _validate_items, _validate_one_config
    prev = _base()
    K = json.load(open(EDITS, encoding="utf-8"))
    assert K["counts"] == {"items_noted": 2, "configs": 2}, K["counts"]
    final = copy.deepcopy(prev)
    for e in K["configs"]:
        cfg = next(c for c in final["category_configs"] if c["category_id"] == e["c"])
        assert _at(cfg, e["p"]) == e["from"], (e["c"], e["p"])
        _set(cfg, e["p"], e["to"])
    flagged = []
    for it in final["items"]:
        labels, flags = catalogue_labels.labels_for(it["kind"], it["attributes"])
        flagged += flags
        it["labels"] = labels
        if it["item_uid"] in K["items"]:
            it["item_notes"] = K["items"][it["item_uid"]]["item_notes"]
    assert not flagged, flagged[:5]

    # ITEMS: less labels / item_notes every item = v91's, in order; exactly the declared two carry a note
    strip = lambda i: {k: v for k, v in i.items() if k not in ("labels", "item_notes")}   # noqa: E731
    assert [_canon(strip(i)) for i in final["items"]] == [_canon(i) for i in prev["items"]]
    noted = sorted(i["item_uid"] for i in final["items"] if i.get("item_notes"))
    assert noted == sorted(K["items"]), noted
    n_lab = sum(1 for i in final["items"] if i["labels"])
    print("items %d; attributes / rates changed 0; labelled %d (0 flagged); noted %s" % (len(final["items"]), n_lab, noted))
    assert catalogue_labels.label_problems(final["items"]) == []

    # KEY BY KEY: only the declared strings differ; undoing them gives v91 back
    for a, b in zip(prev["category_configs"], final["category_configs"]):
        back = copy.deepcopy(b)
        for e in K["configs"]:
            if e["c"] == b["category_id"]:
                _set(back, e["p"], e["from"])
        assert _canon(back) == _canon(a), a["category_id"]
    changed = sorted({e["c"] for e in K["configs"]})
    print("configs changed:", changed)
    assert list(final.keys()) == list(prev.keys())

    _validate_items(final["items"])
    stored = [dict(c, discipline=final["discipline"]) for c in final["category_configs"]]
    for n, c in enumerate(stored):
        _validate_one_config(c, "category_configs[%d]" % n)
        config_validation._validate_config(c)
    problems = (config_validation.delegated_section_problems(stored, final["items"]) + config_validation.extras_problems(stored, final["items"])
                + config_validation.scope_problems(stored, final["items"]))
    if problems:
        raise SystemExit("cross-category check refuses: %r" % problems)

    # GATE
    stored_base = [dict(c, discipline=prev["discipline"]) for c in prev["category_configs"]]
    g_base = [p for p in catalogue_gate.reference_problems(stored_base, prev["items"], "HVAC") if p["severity"] == "REFUSE"]
    g_new = catalogue_gate.reference_problems(stored, final["items"], "HVAC")
    refused = [p for p in g_new if p["severity"] == "REFUSE"]
    print("GATE v91: %d refusal(s) | v92: %d refusal(s), %d info line(s)" % (len(g_base), len(refused), len(g_new) - len(refused)))
    if g_base or refused:
        raise SystemExit("the reference gate refuses: %r" % [catalogue_gate.format_problem(p) for p in g_base + refused])
    # ... and it REFUSES a note reference to an empty note (negative, in memory)
    neg = copy.deepcopy(final["items"])
    for it in neg:
        if it["item_uid"] in K["items"]:
            it["item_notes"] = ""
    neg_ref = [p for p in catalogue_gate.reference_problems(stored, neg, "HVAC") if p["severity"] == "REFUSE"]
    assert len(neg_ref) == 2 and all("note" in p["message"] for p in neg_ref), neg_ref
    print("GATE negative: both notes emptied -> %d refusals (%s)" % (len(neg_ref), neg_ref[0]["message"]))

    # SERVED: through THE ONE MERGE every config = v91's, byte for byte
    built = catalogue_lists.build([dict(i, active=1) for i in final["items"]], stored)
    built_base = catalogue_lists.build([dict(i, active=1) for i in prev["items"]], stored_base)
    merged = {c["category_id"]: catalogue_lists.merge_config(c, built, "HVAC") for c in stored}
    merged_base = {c["category_id"]: catalogue_lists.merge_config(c, built_base, "HVAC") for c in stored_base}
    differ = sorted(cid for cid in merged if _canon(merged[cid]) != _canon(merged_base[cid]))
    assert differ == [], differ
    for e in K["configs"]:
        print("   served %s %s: %r" % (e["c"], "/".join(map(str, e["p"])), _at(merged[e["c"]], e["p"])))
    print("SERVED v92 = SERVED v91 on all %d configs, byte for byte | stamp %s -> %s" % (len(stored), built_base["stamp"], built["stamp"]))

    # G-PROSE
    p_old = catalogue_gate.prose_mentions(stored_base, prev["items"])
    p_new = catalogue_gate.prose_mentions(stored, final["items"])
    gone = sorted(set(p_old) - set(p_new))
    print("G-PROSE HVAC: paths %d -> %d; paths no longer carrying a mention: %s" % (len(p_old), len(p_new), gone))
    assert set(p_new) <= set(p_old), sorted(set(p_new) - set(p_old))

    # REQUESTS
    cfgs_base = {(prev["discipline"], cid): merged_base[cid] for cid in merged_base}
    cfgs_new = {(final["discipline"], cid): merged[cid] for cid in merged}
    r_base, r_new = _request_texts(stored_base, cfgs_base, extraction), _request_texts(stored, cfgs_new, extraction)
    diff = sorted(k for k in set(r_base) | set(r_new) if r_base.get(k) != r_new.get(k))
    assert diff == [], diff
    assert not [k for k, t in r_new.items() if "{{" in t]
    print("MODEL REQUESTS: %d eligible HVAC categories; changed %r, v91 -> v92; no '{{' in any" % (len(r_new), diff))

    text = _dump(final)
    tokens = sorted({t for t in re.findall(r"v\d+", text.replace(json.dumps(final.get("source_workbook") or "", ensure_ascii=False), '""'))})
    if tokens:
        raise SystemExit("the asset text carries version-like tokens %r (h07)" % tokens)
    open(out, "w", encoding="utf-8", newline="").write(text)
    print("candidate written:", out, "| items", len(final["items"]), "| configs", len(final["category_configs"]),
          "| sha256", hashlib.sha256(text.encode("utf-8")).hexdigest())
    frappe.destroy()


def verify(candidate):
    verify_items_configs(candidate)   # items (kind / brand / unit / attributes / rates) and configs, live vs the file
    frappe = _connect()
    from nirmaan_stack.services.boq_rate_master import exporter
    asset = json.load(open(candidate, encoding="utf-8"))
    live = exporter.build_asset("HVAC")
    A = {i["item_uid"]: i for i in asset["items"]}
    L = {i["item_uid"]: i for i in live["items"]}
    differ = sorted(u for u in set(A) | set(L) if _canon(A.get(u)) != _canon(L.get(u)))
    notes = {u: L[u].get("item_notes") for u in L if L[u].get("item_notes")}
    print(json.dumps({"export_items_equal_file_incl_labels_and_notes": not differ, "differing": differ[:10],
                      "live_notes": notes, "configs_equal": _canon({c["category_id"]: c for c in live["category_configs"]})
                      == _canon({c["category_id"]: c for c in asset["category_configs"]})}, indent=1, ensure_ascii=False))
    frappe.destroy()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("phase", choices=["edits", "build", "load", "verify"])
    ap.add_argument("--candidate", required=True)
    a = ap.parse_args()
    if a.phase == "edits":
        edits()
    elif a.phase == "build":
        build(a.candidate)
    elif a.phase == "load":
        load(a.candidate)
    else:
        verify(a.candidate)
