// BCS-6a -- EVERY BCS MARGIN IS WORKED FROM THE AMOUNT ON SCREEN (owner R1, 26 Nov 19:32: "we should calculate the summary margin
// based on the the actual rates for BoQ and BCS which the user has selcted"; R2 "we have to fix all of this completely").
//
// The production case that proved it: BOQ-26-00479 'HVAC Estimate Cost' (Wells Fargo), 16 of its 17 costed rows wrong because a
// BOQ Total formula dropped every "take formula" choice (D1). `bcs6a479.fixture.json` is that sheet's production snapshot reduced to
// numbers; each row's `expected_margin_pct` is the "expected" column of Abhishek's write-up, verified 17 / 17 by BCS-S6.
//   (+) the grid's % Margin column (`computeBcsRowCells`) on row 60 = 34.48% (not 24.0%), and on all 17 rows = the expected column;
//   (+) the sheet's Summary panel (`rollupByParent`, as SummaryPanel calls it) = 5,10,302.5 / 3,79,028 = 25.7%;
//   (+) the BoQ summary (`sheetFigures` + `marginOf`) the same;
//   (-) a row with no rate in the app or the uploaded file has a blank % Margin (owner R-BCS-158 1), its cost left out.
import { describe, expect, it } from "vitest";
import FIX from "./bcs6a479.fixture.json";
import { computeBcsRowCells } from "./PricingGrid";
import { rollupByParent } from "./pricingRollup";
import { marginOf, sheetFigures } from "./BoqSummaryBlock";
import { bcsLiveRateKinds, bcsRowQuantity } from "./bcsColumns";
import { buildReconChoiceMap } from "./reconcile";
import { resolveDescriptorValue } from "./reviewRender";
import type { BcsRowRate, ColumnDescriptor, ColumnFormula, PricedRow, ReconciliationChoiceRef } from "./boqTypes";

// ── the fixture, in the get_priced_rows shape the page hands these functions ─────────────────────────────────────────
const descriptors: ColumnDescriptor[] = FIX.column_descriptors.map((s) => {
  const [col, role, value_field] = s.split(":");
  return { col, role, value_field, value_key: null, rate_subkey: null, area: null, header_label: col } as ColumnDescriptor;
});
const formulas: ColumnFormula[] = FIX.column_formulas.map((f) =>
  ({ target_value_field: f.target_value_field, target_value_key: null, target_rate_subkey: null, formula: f.formula }) as unknown as ColumnFormula);
const recon: ReconciliationChoiceRef[] = FIX.reconciliation_choices.map((s) => {
  const [k, choice] = s.split("=");
  const [er, col] = k.split(":");
  return { excel_row: Number(er), col_letter: col, choice } as ReconciliationChoiceRef;
});
const rows: PricedRow[] = FIX.rows.map((r) => ({
  source_row_number: r.excel_row, row_index: r.row_index, node_type: "Line Item", effective_classification: "line_item",
  effective_parent_index: null, description: `row ${r.excel_row}`, qty_total: r.qty, rate_supply: r.rate_supply, rate_install: r.rate_install,
  amount_supply: r.amount_supply, amount_install: r.amount_install, amount_total: r.amount_total,
  priced_rate_supply: r.priced_rate_supply, priced_rate_install: r.priced_rate_install,
}) as unknown as PricedRow);
const bcsRates: BcsRowRate[] = FIX.rows.map((r) =>
  ({ excel_row: r.excel_row, supply_rate: r.bcs_supply, install_rate: r.bcs_install, combined_rate: r.bcs_combined || null, is_filled: 1 }) as unknown as BcsRowRate);
const ratesByExcelRow = new Map(bcsRates.map((r) => [r.excel_row, r]));
const kinds = bcsLiveRateKinds(descriptors);
const reconChoiceMap = buildReconChoiceMap(recon);
const qtySource = FIX.bcs_state.bcs_qty_source, amountSource = FIX.bcs_state.bcs_amount_source;

const gridRow = (row: PricedRow, choices = reconChoiceMap) =>
  computeBcsRowCells({
    row, bcsRow: ratesByExcelRow.get(row.source_row_number), rowBcsDrafts: {}, bcsKinds: kinds,
    bcsQty: bcsRowQuantity(qtySource, (e) => resolveDescriptorValue(row, e), descriptors), bcsAmountSource: amountSource,
    columnDescriptors: descriptors, columnFormulas: formulas, rowDraftRates: {}, reconChoiceMap: choices,
  });
const value = (c: { kind: string; value?: number }) => (c.kind === "value" ? c.value! : null);
const round1 = (v: number | null) => (v === null ? null : Math.round(v * 10) / 10);

describe("BCS-6a -- BOQ-26-00479 from its production snapshot (the grid's % Margin column)", () => {
  it("(+) row 60 (file I 2,500; rates 120 + 25; qty 20; BCS 85 + 10; choice 60:I take formula) -> 34.48%, not 24.0%", () => {
    const c = gridRow(rows.find((r) => r.source_row_number === 60)!);
    expect(value(c.amountCell)).toBe(2900); // 20 x 120 + 20 x 25 -- the Amount (Total) on screen
    expect(value(c.totalCell)).toBe(1900); // (85 + 10) x 20
    expect(Math.round(value(c.marginCell)! * 100) / 100).toBe(34.48);
  });

  it("(+) the owner's rows: 14 -> 28.9%, 23 -> 32.1%, 74 (install-only lump sum) -> 15.0%", () => {
    const m = (er: number) => round1(value(gridRow(rows.find((r) => r.source_row_number === er)!).marginCell));
    expect([m(14), m(23), m(74)]).toEqual([28.9, 32.1, 15.0]);
  });

  it("(+) all 17 costed rows equal the expected column", () => {
    const got = FIX.rows.map((fr) => [fr.excel_row, round1(value(gridRow(rows.find((r) => r.source_row_number === fr.excel_row)!).marginCell))]);
    expect(got).toEqual(FIX.rows.map((fr) => [fr.excel_row, fr.expected_margin_pct]));
  });
});

describe("BCS-6a -- BOQ-26-00479: the sheet's Summary panel and the BoQ summary", () => {
  it("(+) the 17-row Summary panel: 5,10,302.5 / 3,79,028 -> 25.7%", () => {
    const res = rollupByParent(rows, descriptors, formulas, recon, { ratesByExcelRow, kinds, qtySource, amountSource });
    expect(res.bcs!.grand.tendered).toBe(FIX.expected.summary_amount);
    expect(res.bcs!.grand.cost).toBe(FIX.expected.summary_cost);
    expect(round1(value(res.bcs!.grand.margin))).toBe(FIX.expected.summary_margin_pct);
  });

  it("(+) the BoQ summary's line for the sheet: the same amount, cost and margin", () => {
    const f = sheetFigures({ rows, descriptors, formulas, recon, bcsOn: true, qtySource, amountSource, rates: bcsRates });
    expect(f.boqAmount).toBe(FIX.expected.summary_amount);
    expect((f.bcsSupply ?? 0) + (f.typedInstall ?? 0)).toBe(FIX.expected.summary_cost);
    expect(round1(marginOf(f.boqAmount, f.bcsSupply, f.typedInstall))).toBe(FIX.expected.summary_margin_pct);
  });
});

describe("BCS-6a P2f -- a row with no rate anywhere (owner R-BCS-158 1: \"1 agree\")", () => {
  // Row 60 with BOTH rates unpriced in the app and absent from the uploaded file (0 / 0, no marker), its BCS cost unchanged.
  const bare = { ...rows.find((r) => r.source_row_number === 60)!, rate_supply: 0, rate_install: 0, priced_rate_supply: false,
    priced_rate_install: false, amount_supply: 0, amount_install: 0, amount_total: 0 } as PricedRow;

  it("(-) the grid: its % Margin is blank (no amount to measure against); its BCS Total still shows", () => {
    const c = gridRow(bare, new Map());
    expect(c.marginCell.kind).toBe("blank");
    expect(c.amountCell.kind).toBe("blank");
    expect(value(c.totalCell)).toBe(1900);
  });

  it("(-) the Summary panel: its cost is left out with its amount", () => {
    const others = rows.filter((r) => r.source_row_number !== 60);
    const res = rollupByParent([...others, bare], descriptors, formulas, recon, { ratesByExcelRow, kinds, qtySource, amountSource });
    expect(res.bcs!.grand.cost).toBe(FIX.expected.summary_cost - 1900);
    expect(res.bcs!.grand.tendered).toBe(FIX.expected.summary_amount - 2900);
  });
});

describe("BCS-6a D1 -- the choice is found under a BOQ Total formula, so \"keep document\" is honoured where it was chosen", () => {
  // Since the calculated amount is the default (owner R-BCS-158), a MISSED choice and "take formula" give the same number; the
  // case D1 still decides is "keep document": with the ref left as `col: ""` the choice "14:I" would be missed and the margin
  // would use qty x rate (28.86%) although the user kept the file's 13,950 in that cell.
  it("(+) row 14 with I on \"keep document\": the margin divides by the kept 13,950 -> 5.91%", () => {
    const keep = buildReconChoiceMap(recon.map((c) => (c.excel_row === 14 && c.col_letter === "I" ? { ...c, choice: "keep_document" } : c)));
    const c = gridRow(rows.find((r) => r.source_row_number === 14)!, keep);
    expect(value(c.amountCell)).toBe(13950);
    expect(Math.round(value(c.marginCell)! * 100) / 100).toBe(5.91);
  });
});

describe("BCS-6a POINT 4 -- a row with no rate but WITH an amount counts (owner 2026-11-27 01:43, \"agree\")", () => {
  // A sheet whose Amount (Total) has no formula: a lump-sum row with no rate in the app or the file, but 50,000 written in the
  // file's Amount (Total), shown on screen. It counts at 50,000, and its cost counts.
  const d = (col: string, vf: string) => ({ col, role: vf, value_field: vf, value_key: null, rate_subkey: null, area: null, header_label: col }) as ColumnDescriptor;
  const descs = [d("D", "qty_total"), d("E", "rate_supply"), d("F", "rate_install"), d("I", "amount_total")];
  const lump = { source_row_number: 9, row_index: 0, node_type: "Line Item", effective_classification: "line_item", effective_parent_index: null,
    description: "lump sum", qty_total: 1, rate_supply: 0, rate_install: 0, amount_total: 50000 } as unknown as PricedRow;
  const bcsRow = { excel_row: 9, supply_rate: 0, install_rate: 35000, combined_rate: null, is_filled: 1 } as unknown as BcsRowRate;
  const k = bcsLiveRateKinds(descs);

  it("(+) the grid: its % Margin is worked from the 50,000 on screen -> 30.0%", () => {
    const c = computeBcsRowCells({ row: lump, bcsRow, rowBcsDrafts: {}, bcsKinds: k, bcsQty: 1, bcsAmountSource: null,
      columnDescriptors: descs, columnFormulas: [], rowDraftRates: {}, reconChoiceMap: new Map() });
    expect(value(c.amountCell)).toBe(50000);
    expect(round1(value(c.marginCell))).toBe(30.0);
  });

  it("(+) the Summary panel counts its amount and its cost", () => {
    const res = rollupByParent([lump], descs, [], [], { ratesByExcelRow: new Map([[9, bcsRow]]), kinds: k, qtySource: null, amountSource: null });
    expect(res.bcs!.grand.tendered).toBe(50000);
    expect(res.bcs!.grand.cost).toBe(35000);
  });
});
