"""CAT-1b (owner 2026-11-26 01:47 "a a a ok", QR-C-1 (a)): THE WORDING FILL FOR PYTHON TEST READERS of a rate FILE. Test support, no product
code: the product reads the served config, filled by `catalogue_lists.serve_config` / `serve_configs`.

From HVAC v90 the HVAC wording names catalogue values and items through `{{cat:...}}` / `{{item:...}}` placeholders. A test that reads a
rate file from disk and checks a working line, note or rules-page sentence calls `fill_asset_for_tests` (or `read_asset`) so it reads what
the server serves for that file once loaded -- the SAME fill (`catalogue_lists.build` + `fill_node`, the product's own functions), with ONE
difference on purpose: a placeholder that does not resolve RAISES here, naming the place (the product prints the value and the load gate
refuses the file). The TypeScript twin is frontend/src/pages/boq-wizard/rate-helper/catalogueFill.harness.ts; `test_catalogue_fill_parity`
pins the two together byte for byte.
"""
import json

from nirmaan_stack.services.boq_rate_master import catalogue_lists


def has_placeholders(asset):
    return any(catalogue_lists.has_placeholder(c) for c in asset.get("category_configs") or [])


def fill_asset_for_tests(asset):
    """`asset` (a parsed rate file) with every config's wording filled from the file's OWN items. An asset with no placeholder comes back
    as the SAME object (every file before v90). Raises AssertionError listing the places that do not resolve."""
    if not isinstance(asset, dict) or not has_placeholders(asset):
        return asset
    configs = asset["category_configs"]
    built = catalogue_lists.build(asset.get("items") or [], configs)
    problems = []
    filled = [catalogue_lists.fill_node(c, built, problems, str(c.get("category_id") or "?")) for c in configs]
    if problems:
        raise AssertionError("fill_asset_for_tests: %d placeholder(s) do not resolve: %s"
                             % (len(problems), "; ".join("%s %s" % p for p in problems[:5])))
    out = dict(asset)
    out["category_configs"] = filled
    return out


def read_asset(path):
    """Read a rate file and fill it (`fill_asset_for_tests`)."""
    with open(path, encoding="utf-8") as f:
        return fill_asset_for_tests(json.load(f))
