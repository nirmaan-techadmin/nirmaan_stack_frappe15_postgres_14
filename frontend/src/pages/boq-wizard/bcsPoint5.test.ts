// BCS-FX K2 / K3 (pure) -- note point 5's rule (`bcsPoint5.ts`), the one Indian number style (`indianAmount.ts`) and a rate-only
// row's quantity text (`rateOnlyQty.ts`).
//   point 5: (+) a combined-rate sheet (ONE rate column) uses the combined amount and the BCS combined cost; (+) a halves sheet with
//            no Amount (Supply) column takes quantity x supply rate; (-) a point-3 row is never listed; (+) the marked rows are the
//            listed row and every group above it.
//   E2:      (+) Indian grouping, a blank for no value, "0" for zero.
//   E3:      (+) "RO" (the file's own text) for a rate-only row's 0 quantity; (+) "RO" for a parser-marked row with no text;
//            (-) a normal 0-quantity row shows its 0 (no text); (-) a real quantity is shown as it is; (-) not on a rate column.
import { describe, expect, it } from "vitest";
import { point5MarkedRowIndexes, point5Rows } from "./bcsPoint5";
import { indianAmount } from "./indianAmount";
import { rateOnlyQtyText } from "./rateOnlyQty";
import type { RollupColumn, RollupNode } from "./pricingRollup";

const desc = (col: string, vf: string) => ({ col, role: vf, area: null, value_field: vf, value_key: null, rate_subkey: null });
const col = (c: string, vf: string): RollupColumn => ({ col: c, label: c, descriptor: desc(c, vf) as never });
const node = (rowIndex: number, er: number | null, own: Record<string, number | null>, children: RollupNode[] = []): RollupNode =>
  ({ rowIndex, sourceRowNumber: er, description: null, classification: "line_item", depth: 0, ownAmounts: own, totals: {},
    isParent: children.length > 0, children } as unknown as RollupNode);
const rate = (er: number, s: number | null, i: number | null, c: number | null) =>
  [er, { excel_row: er, supply_rate: s, install_rate: i, combined_rate: c }] as [number, never];

describe("BCS-FX point 5 (pure)", () => {
  it("(+) a combined-rate sheet: the combined amount and the BCS combined cost", () => {
    const cols = [col("F", "amount_total")];
    const roots = [node(0, 10, { F: 500 }), node(1, 11, { F: 300 }), node(2, 12, { F: 0 })];
    const rates = new Map([rate(10, 99, null, 0), rate(11, null, null, 120)]);
    // row 10: a supply figure is NOT the combined cost on a one-rate-column sheet -> listed (combined 0); row 11 costed; row 12 no amount
    expect(point5Rows({ roots, columns: cols, ratesByExcelRow: rates, kinds: ["combined"], leftOut: [] })).toEqual([10]);
  });
  it("(+) a halves sheet with no Amount (Supply) column: quantity x supply rate", () => {
    const cols = [col("G", "amount_total")];
    const rows = [{ source_row_number: 151, qty_total: 1, rate_supply: 350000 }, { source_row_number: 152, qty_total: 2, rate_supply: 0 }];
    const descriptors = [desc("D", "qty_total"), desc("E", "rate_supply"), desc("F", "rate_install"), desc("G", "amount_total")];
    const roots = [node(0, 151, { G: 381500 }), node(1, 152, { G: 60 })];
    const rates = new Map([rate(151, 0, 265000, 0)]);
    expect(point5Rows({ roots, columns: cols, ratesByExcelRow: rates, kinds: ["supply", "install"], leftOut: [],
      rows: rows as never, descriptors: descriptors as never })).toEqual([151]);
  });
  it("(-) a point-3 row is never listed, (+) the marks climb to every group above a listed row", () => {
    const cols = [col("G", "amount_supply")];
    const leaf = node(2, 21, { G: 50 });
    const roots = [node(0, 20, { G: null }, [node(1, 22, { G: null }, [leaf])]), node(3, 23, { G: 40 })];
    const listed = point5Rows({ roots, columns: cols, ratesByExcelRow: new Map(), kinds: ["supply", "install"], leftOut: [23] });
    expect(listed).toEqual([21]);
    expect([...point5MarkedRowIndexes(roots, listed)].sort()).toEqual([0, 1, 2]);
  });
});

describe("BCS-FX E2 one Indian number style", () => {
  it("(+) grouping 12,34,567; blank for none; 0 for zero", () => {
    expect(indianAmount(1234567)).toBe("12,34,567");
    expect(indianAmount(11503517.5)).toBe("1,15,03,517.5");
    expect(indianAmount(null)).toBe("");
    expect(indianAmount(undefined)).toBe("");
    expect(indianAmount(0)).toBe("0");
  });
});

describe("BCS-FX E3 a rate-only row's quantity", () => {
  const qty = desc("D", "qty_total") as never;
  const rateCol = desc("E", "rate_supply") as never;
  it("(+) the file's own text for a rate-only row's 0 quantity; 'RO' for a parser-marked row with none", () => {
    expect(rateOnlyQtyText({ qty_cell_text: "RO", is_rate_only: 0 } as never, qty, 0)).toBe("RO");
    expect(rateOnlyQtyText({ qty_cell_text: "Qro", is_rate_only: 0 } as never, qty, null)).toBe("Qro");
    expect(rateOnlyQtyText({ qty_cell_text: null, is_rate_only: 1 } as never, qty, 0)).toBe("RO");
  });
  it("(-) a normal 0-quantity row shows its 0; a real quantity stays; a rate column is never touched", () => {
    expect(rateOnlyQtyText({ qty_cell_text: null, is_rate_only: 0 } as never, qty, 0)).toBeNull();
    expect(rateOnlyQtyText({ qty_cell_text: "40", is_rate_only: 0 } as never, qty, 0)).toBeNull();
    expect(rateOnlyQtyText({ qty_cell_text: "RO", is_rate_only: 1 } as never, qty, 12)).toBeNull();
    expect(rateOnlyQtyText({ qty_cell_text: "RO", is_rate_only: 1 } as never, rateCol, 0)).toBeNull();
  });
});
