"""CAT-1b (HVAC v90: the HVAC wording names catalogue values through {{cat:...}} placeholders; no item changed): a LIVE category config as
v89 held it, for a test that reads the RAW live config (SQL) and compares it with an older file. Test support, no product code. Driven by
ONE file -- frontend/src/pages/boq-wizard/rate-helper/__fixtures__/cat1bEdits.json, the mint's own edits (a copy of CAT-1's
cat1_undo_support.py pointed at that file).

It undoes ONLY the declared edits and refuses anything else: a config that holds v90's texts gets v89's texts back edit by edit; a config
that holds v89's (or an older file's) texts comes back as it is; one that holds some but not all of v90's texts raises.
`vav2c3d_undo_support.as_v86` applies this first, then CAT-1's `as_v88`, so every older comparison reads v90 as v89, then v88 ...
(The SERVED config never needs this: the fill gives v89's text back, `test_cat1b_wording`.)
"""
import copy
import json
import os

_FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "frontend", "src", "pages", "boq-wizard", "rate-helper", "__fixtures__",
                    "cat1bEdits.json")
_MISSING = object()
_CACHE = {}


def edits():
    if "e" not in _CACHE:
        with open(_FIX, encoding="utf-8") as f:
            _CACHE["e"] = json.load(f)
    return _CACHE["e"]


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


def as_v89(cfg, category_id=None):
    """`cfg` (one live category config) with v90's wording edits undone; v89's and older shapes come back as they are. Raises otherwise."""
    cid = category_id or cfg["category_id"]
    mine = [e for e in edits()["configs"] if e["c"] == cid]
    if not mine:
        return cfg
    held = [_at(cfg, e["p"]) == e["to"] for e in mine]
    if not any(held):
        return cfg          # v89 or older: none of v90's texts (an older file's texts are left to the next undo in the chain)
    if not all(held):
        miss = [e for e, h in zip(mine, held) if not h][0]
        raise AssertionError("as_v89: %s %s holds neither v89's nor v90's text" % (cid, "/".join(str(x) for x in miss["p"])))
    out = copy.deepcopy(cfg)
    for e in reversed(mine):
        parent = _at(out, e["p"][:-1])
        parent[e["p"][-1]] = e["from"]
    return out
