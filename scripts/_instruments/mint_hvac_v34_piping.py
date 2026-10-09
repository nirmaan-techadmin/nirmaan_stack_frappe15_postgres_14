"""SLICE 12e-1 -- MINT HVAC v34 = v33 + THE PIPING CATALOGUE (40 items, one data-only config, two live MS links).

Runs IN THE CONTAINER under the bench's python (it needs frappe for the ONE uid mint and, with --load, for
the loader / exporter). Two phases, both explicit:

  build   read the owner's workbook sheet "Piping" + the v33 asset, mint one item_uid per row through
          `csv_importer.mint_item_uid` (the ONE mint -- never inline), assemble the candidate payload
          (v33's items + 40 Piping items; v33's 9 configs + the Piping config; every other top-level key
          carried verbatim), validate it offline (config validator + the derived-rate consistency the
          loader will re-check), write it to --out. NO database write.
  load    take the pre-load HVAC snapshot, `loader.load_rate_master(path=<candidate>, replace=True)`,
          then `exporter.export_asset_text("HVAC")` -> the DB-exported v34 text (two exports of an
          unchanged DB are byte-identical) -> --canonical. Electrical is never touched.

The committed artefact is the DB export RE-ORDERED INTO THE FILE CONVENTION the HVAC series carries
(measured on v32 / v33, 2026-10-09): items in GLOBAL `item_uid` order (kinds interleaved), configs in
creation order with the new one LAST -- the exporter's own `kind asc, item_uid asc` / `category_id asc`
order is a different, content-equal ordering, and the cross-version pins compare ORDERED lists -- plus
the top-level `intentional_removals` key the exporter does not emit, carried from the previous asset.
Both are done by hand after `load` (the 12e-1 session record names the steps); the content of every
carried item and config is asserted byte-equal to v33 while doing so. Re-running `build` mints fresh
uids (the mint is random by design); the committed file is the record.

Owner rulings carried (2026-10-09): 40 items all per metre; sizes in the sheet's own spelling; copper
install flat 110 BCS; copper 31.7 install 220 (the sheet carries it); no rounding; MS 300 = 2 x MS 150
and MS 250 = MS 150 + MS 100 as LIVE links; one category at a time; every item carries its own
supply / install markup (ruling revised 2026-10-09 17:39); NO pricing (pipelines {}).
"""
import argparse, copy, json, os, sys

PIPE_TYPE_BY_ITEM = {
    "Refrigerant Piping/Copper Piping": "Copper",
    "Chilled Water Piping / MS Piping": "MS",
    "PVC Pipe": "PVC",
    "CPVC Pipe": "CPVC",
}
KIND = "hvac_piping_item"
CATEGORY_ID = "hvac_piping"
SHEET = "Piping"
# header -> column index (0-based), verified against the sheet's row 1 on 2026-10-09
COLS = {"item": 0, "unit": 1, "size_mm": 2, "size_in": 3, "supply_markup": 4, "install_markup": 5,
        "bcs_pipe": 6, "bcs_accessories": 7, "cost_supply": 8, "cost_install": 9, "boq_supply": 10, "boq_install": 11}
HEADERS = ["Item", "Unit", "Pipe Size/ Dia (mm)", "Pipe Size/ Dia (inches)", "Supply Mark up", "Install Mark up",
           "BCS Pipe", "BCS Accessories", "Total BCS Supply", "BCS Installation", "BoQ Supply", "BoQ Installation"]


def read_sheet(path):
    import openpyxl
    ws = openpyxl.load_workbook(path, data_only=True)[SHEET]
    rows = [r for r in ws.iter_rows(min_row=1, max_row=ws.max_row, values_only=True) if any(v is not None for v in r)]
    if [str(h).strip() for h in rows[0][:12]] != HEADERS:
        raise SystemExit("sheet header differs from the verified shape: %r" % (rows[0][:12],))
    out = []
    for excel_row, r in enumerate(rows[1:], start=2):
        item = str(r[COLS["item"]]).strip()
        if item not in PIPE_TYPE_BY_ITEM:
            raise SystemExit("row %d: unknown Item text %r" % (excel_row, item))
        num = lambda k: r[COLS[k]]
        for k in ("size_mm", "supply_markup", "install_markup", "cost_supply", "cost_install"):
            if not isinstance(num(k), (int, float)):
                raise SystemExit("row %d: %s is not a number: %r" % (excel_row, k, num(k)))
        out.append({
            "excel_row": excel_row, "pipe_type": PIPE_TYPE_BY_ITEM[item], "unit": str(r[COLS["unit"]]).strip(),
            "size_mm": float(num("size_mm")), "supply_markup": float(num("supply_markup")), "install_markup": float(num("install_markup")),
            "cost_supply": float(num("cost_supply")), "cost_install": float(num("cost_install")),
        })
    if len(out) != 40:
        raise SystemExit("expected 40 data rows, read %d" % len(out))
    return out


def build(workbook, base, out):
    import frappe
    os.chdir("/workspace/development/frappe-bench/sites")
    frappe.init(site="localhost"); frappe.connect()
    from nirmaan_stack.services.boq_rate_master import csv_importer, config_validation
    from nirmaan_stack.services.boq_rate_master.loader import _validate_items, _validate_one_config
    rows = read_sheet(workbook)
    v33 = json.load(open(base, encoding="utf-8"))
    taken = {it["item_uid"] for it in v33["items"]}
    taken |= {(r["item_uid"] or "").strip() for r in frappe.get_all("BoQ Rate Master Item", filters={"discipline": "HVAC"}, fields=["item_uid"])}
    items = []
    for r in rows:
        uid = csv_importer.mint_item_uid("HVAC", taken)     # the ONE mint
        items.append({
            "kind": KIND, "brand": None, "unit": r["unit"],
            "attributes": {"pipe_type": r["pipe_type"], "size_mm": r["size_mm"]},
            "rates": {"cost_supply": r["cost_supply"], "cost_install": r["cost_install"],
                      "supply_markup": r["supply_markup"], "install_markup": r["install_markup"]},
            "source": {"sheet": SHEET, "row": r["excel_row"]},
            "item_uid": uid,
        })
    by_ms = {it["attributes"]["size_mm"]: it["item_uid"] for it in items if it["attributes"]["pipe_type"] == "MS"}
    ms150, ms100, ms300, ms250 = by_ms[150.0], by_ms[100.0], by_ms[300.0], by_ms[250.0]
    link = lambda uid, mult: {"from": {"item_uid": uid, "rate_key": "__KEY__"}, "multiplier": mult, "constant": 0.0}
    def links(terms):
        return {k: [dict(t, **{"from": {"item_uid": t["from"]["item_uid"], "rate_key": k}}) for t in terms] for k in ("cost_supply", "cost_install")}
    derived = {ms300: links([link(ms150, 2.0)]), ms250: links([link(ms150, 1.0), link(ms100, 1.0)])}
    sizes = sorted({it["attributes"]["size_mm"] for it in items})
    config = {
        "discipline": "HVAC",
        "category_id": CATEGORY_ID,
        "category_display": "Piping",
        "item_kinds": [KIND],
        "attribute_definitions": [
            {"id": "pipe_type", "label": "Pipe type", "type": "choice", "values": ["Copper", "MS", "PVC", "CPVC"]},
            {"id": "size_mm", "label": "Pipe size / dia (mm)", "type": "number_choice", "values": sizes},
        ],
        "pipelines": {},
        "derived_rates": derived,
        "notes": "SLICE 12e-1 (owner, 2026-10-09): the Piping CATALOGUE only -- 40 per-metre items from the HVAC workbook's "
                 "Piping sheet (copper 13, MS 13, PVC 8, CPVC 6), each with the sheet's own BCS supply / BCS install / supply "
                 "markup / install markup, sizes in the sheet's own spelling, no inch pre-computation. DATA-ONLY: no pipelines, so "
                 "it can never price a BoQ row and the calculator shows 'coming soon' (12e-2 brings the rules). The two MS links are "
                 "LIVE: MS 300 = 2 x MS 150 and MS 250 = MS 150 + MS 100 on both cost columns, recomputed on every write of the base.",
    }
    _validate_one_config(config, "category_configs[hvac_piping]")
    config_validation._validate_config(config)
    _validate_items(items)
    # the loader's own post-load consistency check, run offline on the candidate
    by_uid = {it["item_uid"]: {"rates": it["rates"]} for it in items}
    bad = config_validation.derived_rate_updates([config], by_uid)
    if bad:
        raise SystemExit("derived cells disagree with their base in the candidate: %r" % bad)
    payload = copy.deepcopy(v33)
    payload["items"] = v33["items"] + items
    payload["category_configs"] = v33["category_configs"] + [config]
    json.dump(payload, open(out, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print("candidate written:", out, "| items", len(payload["items"]), "| configs", len(payload["category_configs"]),
          "| MS150", ms150, "MS100", ms100, "MS300", ms300, "MS250", ms250)
    frappe.destroy()


def load(candidate, canonical):
    import frappe
    os.chdir("/workspace/development/frappe-bench/sites")
    frappe.init(site="localhost"); frappe.connect()
    frappe.set_user("Administrator")
    from nirmaan_stack.services.boq_rate_master import exporter, loader
    # AC8: the pre-load HVAC snapshot
    pre_payload, pre_text = exporter.export_asset_text("HVAC")
    snap = exporter.write_snapshot("HVAC", pre_text, pre_payload)
    frappe.db.commit()
    print("pre-load snapshot:", snap, "| items", len(pre_payload["items"]), "| configs", len(pre_payload["category_configs"]))
    summary = loader.load_rate_master(path=candidate, replace=True)
    frappe.db.commit()
    print("LOAD SUMMARY:", json.dumps(summary, default=str))
    payload, text = exporter.export_asset_text("HVAC")
    open(canonical, "w", encoding="utf-8").write(text)
    print("canonical export written:", canonical, "| items", len(payload["items"]), "| configs", len(payload["category_configs"]))
    frappe.destroy()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("phase", choices=["build", "load"])
    ap.add_argument("--workbook"); ap.add_argument("--base"); ap.add_argument("--out")
    ap.add_argument("--candidate"); ap.add_argument("--canonical")
    a = ap.parse_args()
    if a.phase == "build":
        build(a.workbook, a.base, a.out)
    else:
        load(a.candidate, a.canonical)
