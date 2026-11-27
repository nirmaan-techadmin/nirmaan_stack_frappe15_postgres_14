"""CAT-3 (HVAC v92: two config strings became `{{note:<item_uid>}}`; items gained derived `labels` and two `item_notes`): a LIVE category
config as v91 held it, for a test that reads the RAW live config and compares it with an older file. Test support, no product code.
Driven by ONE file -- frontend/src/pages/boq-wizard/rate-helper/__fixtures__/cat3Edits.json, the mint's own edits (the shape of CAT-2's
cat2_undo_support.py; every v92 config edit REPLACES a string, so undoing it puts v91's string back).

It undoes ONLY the declared edits: a config holding v92's exact placeholder gets v91's string back; any other string there (v91's, or an
older file's own wording) comes back as it is; a FOREIGN note placeholder at that path (`{{note:<another uid>}}`) raises. `vav2c3d_undo_support.as_v86` applies this first, then CAT-2's
`as_v90`, so every older comparison reads v92 as v91, then v90 ...
"""
import copy
import json
import os

_FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "frontend", "src", "pages", "boq-wizard", "rate-helper", "__fixtures__",
                    "cat3Edits.json")
_CACHE = {}
_MISSING = object()


def edits():
    if "e" not in _CACHE:
        with open(_FIX, encoding="utf-8") as f:
            _CACHE["e"] = json.load(f)
    return _CACHE["e"]


def _at(node, path):
    for p in path:
        if isinstance(node, list) and isinstance(p, int) and p < len(node):
            node = node[p]
        elif isinstance(node, dict) and p in node:
            node = node[p]
        else:
            return _MISSING
    return node


def as_v91(cfg, category_id=None):
    """`cfg` (one live category config) with v92's string edits undone; v91's and older shapes come back as they are. Raises otherwise."""
    cid = category_id or cfg["category_id"]
    mine = [e for e in edits()["configs"] if e["c"] == cid]
    out = cfg
    for e in mine:
        have = _at(out, e["p"])
        if have != e["to"]:
            if isinstance(have, str) and "{{note:" in have:
                raise AssertionError("as_v91: %s %s holds a note placeholder that is not v92's" % (cid, "/".join(map(str, e["p"]))))
            continue        # v91 or an older file: its own string (or no such path) - nothing of v92's to undo
        if out is cfg:
            out = copy.deepcopy(cfg)
        node = out
        for p in e["p"][:-1]:
            node = node[p]
        node[e["p"][-1]] = e["from"]
    return out
