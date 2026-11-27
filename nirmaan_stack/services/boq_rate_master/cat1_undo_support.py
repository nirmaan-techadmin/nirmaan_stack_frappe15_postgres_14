"""CAT-1 (HVAC v89: the Valve Package On-Off declared as an unstocked answer, the 5 VAV share parts by item_uid, the four ruled rules-page
lines; no item changed): a LIVE category config as v88 held it, for a test that compares the live catalogue with an older file. Test support,
no product code. Driven by ONE file -- frontend/src/pages/boq-wizard/rate-helper/__fixtures__/cat1Edits.json, the mint's own edits (a copy of
VAV-FIX's vavfix_undo_support.py pointed at that file).

It undoes ONLY the declared edits and refuses anything else, so nothing can hide in it: a config that holds v89's edits is reversed edit by edit;
a config that holds v88's (or an older file's) shape comes back as it is; one that holds neither raises. `vav2c3d_undo_support.as_v86` applies
this first, then VAV-FIX's `as_v87`, so every older comparison reads v89 as v88, then v87, v86 ...
"""
import copy
import json
import os

_FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "frontend", "src", "pages", "boq-wizard", "rate-helper", "__fixtures__",
                    "cat1Edits.json")
_MISSING = object()


def edits():
    with open(_FIX, encoding="utf-8") as f:
        return json.load(f)


def _at(cfg, path):
    node = cfg
    for p in path:
        if isinstance(node, list):
            if not isinstance(p, int) or p >= len(node):
                return _MISSING
            node = node[p]
        elif isinstance(node, dict):
            if p not in node:
                return _MISSING
            node = node[p]
        else:
            return _MISSING
    return node


def _holds(cfg, path, value):
    have = _at(cfg, path)
    return have is _MISSING if value is None else (have is not _MISSING and have == value)


def as_v88(cfg, category_id=None):
    """`cfg` (one live category config) with v89's edits undone; v88's and older shapes come back as they are. Raises otherwise."""
    cid = category_id or cfg["category_id"]
    mine = [e for e in edits()["configs"] if e["c"] == cid]
    if not mine:
        return cfg
    if all(_holds(cfg, e["p"], e["from"]) for e in mine):
        return cfg
    # an older file than v88: none of v89's new keys or values, and not every v88 text either -- leave it to the next undo in the chain
    # (a key v89 REMOVES is absent from older files too, so it never counts as a sign of v89)
    if not any(_holds(cfg, e["p"], e["to"]) for e in mine if e["to"] is not None):
        return cfg
    for e in mine:
        if not _holds(cfg, e["p"], e["to"]):
            raise AssertionError("as_v88: %s %s holds neither v88's nor v89's value" % (cid, "/".join(str(x) for x in e["p"])))
    out = copy.deepcopy(cfg)
    for e in reversed(mine):
        parent = _at(out, e["p"][:-1])
        last = e["p"][-1]
        if e["from"] is None:
            del parent[last]
        else:
            parent[last] = copy.deepcopy(e["from"])
    return out
