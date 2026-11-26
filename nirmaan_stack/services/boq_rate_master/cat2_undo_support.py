"""CAT-2 (HVAC v91: a `list_spec.code_targets` block on four configs; no item changed): a LIVE category config as v90 held it, for a test
that reads the RAW live config (SQL) and compares it with an older file. Test support, no product code. Driven by ONE file --
frontend/src/pages/boq-wizard/rate-helper/__fixtures__/cat2Edits.json, the mint's own edits (the shape of CAT-1b's cat1b_undo_support.py;
every v91 edit ADDS a key, so undoing it removes the key).

It undoes ONLY the declared edits and refuses anything else: a config that holds v91's block exactly gets it removed; a config without the
key (v90 or an older file) comes back as it is; one that holds a DIFFERENT block raises.
`vav2c3d_undo_support.as_v86` applies this first, then CAT-1b's `as_v89`, so every older comparison reads v91 as v90, then v89 ...
"""
import copy
import json
import os

_FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "frontend", "src", "pages", "boq-wizard", "rate-helper", "__fixtures__",
                    "cat2Edits.json")
_CACHE = {}


def edits():
    if "e" not in _CACHE:
        with open(_FIX, encoding="utf-8") as f:
            _CACHE["e"] = json.load(f)
    return _CACHE["e"]


def as_v90(cfg, category_id=None):
    """`cfg` (one live category config) with v91's added key removed; v90's and older shapes come back as they are. Raises otherwise."""
    cid = category_id or cfg["category_id"]
    mine = [e for e in edits()["configs"] if e["c"] == cid]
    if not mine:
        return cfg
    out = cfg
    for e in reversed(mine):
        assert e["from"] is None, "as_v90: every v91 edit adds a key"
        parent = out
        for p in e["p"][:-1]:
            parent = parent.get(p) if isinstance(parent, dict) else None
        if not isinstance(parent, dict) or e["p"][-1] not in parent:
            continue        # v90 or older: the key is not there
        if parent[e["p"][-1]] != e["to"]:
            raise AssertionError("as_v90: %s %s holds a block that is not v91's" % (cid, "/".join(e["p"])))
        if out is cfg:
            out = copy.deepcopy(cfg)
            parent = out
            for p in e["p"][:-1]:
                parent = parent[p]
        del parent[e["p"][-1]]
    return out
