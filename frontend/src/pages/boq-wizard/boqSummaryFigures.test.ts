// BCS-5 -- THE BoQ SUMMARY'S PER-SHEET FIGURES COME FROM THE SHEET SUMMARY'S OWN FUNCTIONS (BoqSummaryBlock.sheetFigures).
//   (+) BCS supply + typed installation == the BCS Total the sheet's own Summary shows (rollupByParent with the full cost input,
//       as SummaryPanel calls it), on the built-in total AND on a declared BCS Total formula;
//   (+) the BoQ amount == the Summary's own amount columns (supply + install halves); rows with a BoQ amount / with a BCS supply are counted per row;
//   (-) a sheet with BCS off has no cost figures (blank, never 0), only its BoQ amount;
//   (+) the table: the ticked block's one installation and one margin; an unticked sheet's typed installation; the total margin
//       blank until every listed sheet has a cost; no area -> needsArea.
import { describe, expect, it } from "vitest";
import { marginOf, sheetFigures, summaryTable, type SheetFigures, type SheetReads } from "./BoqSummaryBlock";
import { rollupByParent } from "./pricingRollup";
import type { BcsRowRate, ColumnDescriptor, ColumnFormula, PricedRow } from "./boqTypes";

const d = (col: string, vf: string): ColumnDescriptor => ({ col, role: vf, area: null, value_field: vf, value_key: null, rate_subkey: null });
// No total-amount column: with no amount formula a total pairs only with a combined rate, so the sheet's own amount columns are
// the two halves (bcsAmountColumns sums them - the BoQ amount).
const DESCS = [d("D", "qty_total"), d("E", "rate_supply"), d("F", "rate_install"), d("G", "amount_supply"), d("H", "amount_install")];
const row = (idx: number, parent: number | null, er: number, qty: number, s: number, i: number, cls = "line_item") =>
  ({ row_index: idx, effective_parent_index: parent, effective_classification: cls, description: `r${er}`, source_row_number: er,
    qty_total: qty, rate_supply: s, rate_install: i, node_type: cls === "line_item" ? "Line Item" : "Preamble",
    // BCS-6a (moved checks, third table): the rate is marked as entered in the app, so the Amount on screen is qty x rate.
    priced_rate_supply: s !== 0, priced_rate_install: i !== 0 }) as unknown as PricedRow;
const ROWS = [row(0, null, 10, 0, 0, 0, "preamble"), row(1, 0, 11, 10, 100, 20), row(2, 0, 12, 5, 200, 0), row(3, 0, 13, 2, 0, 0)];
const rate = (er: number, s: number, i: number) => ({ excel_row: er, supply_rate: s, install_rate: i, combined_rate: 0 }) as unknown as BcsRowRate;
const RATES = [rate(11, 70, 5), rate(12, 150, 0), rate(13, 40, 0)]; // row 13: a BCS supply with no BoQ amount
const reads = (over: Partial<SheetReads> = {}): SheetReads => ({ rows: ROWS, descriptors: DESCS, formulas: [], recon: [], bcsOn: true,
  qtySource: null, amountSource: null, rates: RATES, ...over });

/** What SummaryPanel shows for the same sheet: rollupByParent with the FULL cost input (no side read as 0). */
function summaryPanelFigures(formulas: ColumnFormula[]) {
  const r = rollupByParent(ROWS, DESCS, formulas, [], {
    ratesByExcelRow: new Map(RATES.map((x) => [x.excel_row, x])), kinds: ["supply", "install"], qtySource: null, amountSource: null,
  });
  return { bcsTotal: r.bcs?.grand.cost ?? null, totalAmount: r.grandTotals["G"] + r.grandTotals["H"] };
}

describe("sheetFigures - the sheet Summary's own functions", () => {
  it("(+) supply + typed install == the Summary's BCS Total; BoQ amount == its total column; rows counted", () => {
    const f = sheetFigures(reads());
    const sp = summaryPanelFigures([]);
    // BCS-6a MOVED CHECK (owner R-BCS-158 1, "1 agree"): row 13 has a BCS supply but NO rate in the app or the uploaded
    // file, so it is left out of the margin -- its cost too. Until BCS-6a this was 10 x 70 + 5 x 150 + 2 x 40 = 1,530.
    expect(f.bcsSupply).toBe(10 * 70 + 5 * 150);
    expect(f.typedInstall).toBe(10 * 5);
    expect((f.bcsSupply ?? 0) + (f.typedInstall ?? 0)).toBe(sp.bcsTotal);
    expect(f.boqAmount).toBe(sp.totalAmount);
    expect(f.boqAmount).toBe(10 * 120 + 5 * 200);
    expect([f.rowsWithAmount, f.rowsWithSupply]).toEqual([2, 2]); // row 13 has a BCS supply but no BoQ amount: not counted
  });
  it("(+) the same on a declared BCS Total formula (supply + install) x qty", () => {
    const ref = (vf: string) => ({ ref: { value_field: vf, value_key: null, rate_subkey: null } });
    const formula = { target_value_field: "bcs_total", target_value_key: null, target_rate_subkey: null, target_col: null,
      formula: { op: "*", operands: [{ op: "+", operands: [ref("bcs_supply"), ref("bcs_install")] }, ref("qty_total")] } } as unknown as ColumnFormula;
    const f = sheetFigures(reads({ formulas: [formula] }));
    expect((f.bcsSupply ?? 0) + (f.typedInstall ?? 0)).toBe(summaryPanelFigures([formula]).bcsTotal);
    expect(f.typedInstall).toBe(50);
  });
  it("(-) BCS off: no cost figures (blank, never 0), the BoQ amount stays", () => {
    const f = sheetFigures(reads({ bcsOn: false }));
    expect([f.bcsSupply, f.typedInstall]).toEqual([null, null]);
    expect(f.boqAmount).toBe(2200);
  });
  it("(+) an ELV-style sheet (a BOQ Total formula + a reconciliation choice): the BoQ amount follows the choice, as the Summary shows it", () => {
    // Question 4 = (c): the document prints 999 in I; the sheet's formula I = G + H gives 1,200; a take_formula choice on I.
    const ref = (vf: string) => ({ ref: { value_field: vf, value_key: null, rate_subkey: null } });
    const fm = (target: string, col: string | null, formula: unknown) =>
      ({ target_value_field: target, target_value_key: null, target_rate_subkey: null, target_col: col, formula }) as unknown as ColumnFormula;
    const descs = [...DESCS, d("I", "amount_total")];
    const formulas = [fm("amount_total", "I", { op: "+", operands: [ref("amount_supply"), ref("amount_install")] }),
      fm("boq_total", null, ref("amount_total"))];
    // The document's own printed amounts: G 1,000, H 200 and I 999 (a divergent total).
    const rows = [{ ...ROWS[1], row_index: 0, effective_parent_index: null, amount_supply: 1000, amount_install: 200, amount_total: 999 } as unknown as PricedRow];
    const choice = [{ excel_row: 11, col_letter: "I", choice: "take_formula" }];
    const withChoice = sheetFigures(reads({ rows, descriptors: descs, formulas, recon: choice as never }));
    const panel = rollupByParent(rows, descs, formulas, choice as never);
    expect(panel.grandTotals["I"]).toBe(1200); // what the sheet's Summary shows in I
    expect(withChoice.boqAmount).toBe(1200); // the block follows it (not the un-reconciled 999)
    // BCS-6a MOVED CHECK (owner R-BCS-158): with NO choice the calculated amount is used (until BCS-6a: the document's 999).
    expect(sheetFigures(reads({ rows, descriptors: descs, formulas, recon: [] })).boqAmount).toBe(1200); // no choice: calculated
    const keep = [{ excel_row: 11, col_letter: "I", choice: "keep_document" }];
    expect(sheetFigures(reads({ rows, descriptors: descs, formulas, recon: keep as never })).boqAmount).toBe(999); // (-) kept only where chosen
  });
});

describe("summaryTable - the clubbed block, the lines and the total", () => {
  const fig = (amount: number | null, supply: number | null, typed: number | null): SheetFigures =>
    ({ boqAmount: amount, bcsSupply: supply, typedInstall: typed, rowsWithAmount: 1, rowsWithSupply: supply === null ? 0 : 1 });
  const figs = new Map<string, SheetFigures>([["A", fig(1200, 700, 50)], ["B", fig(1000, 750, null)], ["C", fig(1200, 600, 100)],
    ["D", fig(500, null, null)]]);
  const sheets = [{ sheet_name: "A", ticked: true }, { sheet_name: "B", ticked: true }, { sheet_name: "C", ticked: false }];
  it("(+) one installation and one margin for the ticked block; a ticked sheet's typed install is NOT counted", () => {
    const t = summaryTable(sheets, figs, 300);
    expect(t.block).toMatchObject({ boqAmount: 2200, bcsSupply: 1450, install: 300 });
    expect(t.block?.margin).toBeCloseTo((1 - 1750 / 2200) * 100, 9);
    expect(t.lines.find((l) => l.sheet === "C")).toMatchObject({ install: 100 });
    expect(t.total.install).toBe(400); // the block's 300 + C's typed 100; A's typed 50 is not in it
    expect(t.total.margin).toBeCloseTo((1 - (1450 + 600 + 400) / 3400) * 100, 9);
  });
  it("(+) the total margin stays blank until every listed sheet has a cost; (+) no area -> needsArea", () => {
    expect(summaryTable([...sheets, { sheet_name: "D", ticked: false }], figs, 300).total.margin).toBeNull();
    const noArea = summaryTable(sheets, figs, null);
    expect(noArea.needsArea).toBe(true);
    expect([noArea.block?.margin, noArea.total.margin, noArea.total.install]).toEqual([null, null, null]);
  });
  it("(-) margin is blank (never 0) with no cost or no amount", () => {
    expect(marginOf(1000, null, null)).toBeNull();
    expect(marginOf(null, 10, null)).toBeNull();
    expect(marginOf(0, 10, null)).toBeNull();
    expect(marginOf(1000, 700, 50)).toBeCloseTo(25, 9);
  });
});
