"""CAT-3 (owner 2026-11-26 00:06, R7; ANSWER 1 QR-C-P2 (a)): the values the Rate Master Add-row lists offer -- every value a
category's active items carry. PURE. Split out of catalogue_lists.py (residence S1, the 500-line limit); `catalogue_lists.build`
calls it and re-exports both names."""


def rate_master_kinds(cfg):
    """The item kinds a category's Rate Master grid shows -- the mirror of the screen's `categoryItemKinds`
    (`rateMasterStructure.ts`): the declared `item_kinds`, else every `match_master_row` step's kind, in order."""
    declared = [k for k in (cfg.get("item_kinds") or []) if isinstance(k, str) and k]
    if declared:
        return declared
    kinds = []
    for pl in (cfg.get("pipelines") or {}).values():
        for st in (pl.get("steps") or []) if isinstance(pl, dict) else []:
            k = (st.get("params") or {}).get("kind") if isinstance(st, dict) else None
            if isinstance(st, dict) and st.get("step") == "match_master_row" and isinstance(k, str) and k and k not in kinds:
                kinds.append(k)
    return kinds


def category_item_values(cfg, by_kind):
    """CAT-3 (owner 2026-11-26 00:06, R7; ANSWER 1 QR-C-P2 (a)): {attr: [every value the category's active items carry]}
    over the kinds its Rate Master grid shows (`rate_master_kinds`), brand read from the row. Served BESIDE the config
    (`item_values`), never inside it, so `attribute_definitions` and every reader of the config stay byte-identical."""
    vals = {}
    for k in rate_master_kinds(cfg):
        for a in by_kind.get(k, []):
            for attr, v in a.items():
                if isinstance(v, (str, int, float)) and not isinstance(v, bool) and v != "":
                    vals.setdefault(attr, set()).add(v)
    return {attr: sorted(v, key=lambda x: (str(type(x)), str(x))) for attr, v in sorted(vals.items())}
