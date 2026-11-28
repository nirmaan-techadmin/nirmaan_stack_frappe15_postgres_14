// BCS-FX K2 (owner R-BCS-175 "2 is ok"; QR-CLEAR (a)) -- the client half of "a cleared BCS cost box saves as not entered":
// `gatherBcsRowRates` builds the whole-row save payload.
//   (+) a cleared box (blank, or nothing typed) is sent as null, never 0; (+) a typed 0 is sent as 0; (+) a figure is sent as it is;
//   (-) a partial decimal that is no number ("-", ".") is not a 0 either (null).
// The server half (every box null -> the row's cost removed, kept in history) is test_bcs.TestBcsClearedBox.
import { describe, expect, it } from "vitest";
import { gatherBcsRowRates, mergeBcsRowValues } from "./bcsColumns";
import { foldBcsWrites } from "./clipboard";
import { invert } from "./undoHistory";

describe("BCS-FX K2 a cleared cost box is sent as null", () => {
  it("(+) cleared -> null; typed 0 -> 0; a figure as it is", () => {
    expect(gatherBcsRowRates({ supply_rate: "", install_rate: null, combined_rate: "0" })).toEqual({ supply_rate: null, install_rate: null, combined_rate: 0 });
    expect(gatherBcsRowRates({ supply_rate: "4717", install_rate: "  ", combined_rate: null })).toEqual({ supply_rate: 4717, install_rate: null, combined_rate: null });
  });
  it("(-) never a 0 for a box with no number in it", () => {
    const r = gatherBcsRowRates({ supply_rate: "-", install_rate: ".", combined_rate: "" });
    expect(Object.values(r)).toEqual([null, null, null]);
  });
});

// BCS-FX K2+3 reviewer findings 1 / 3: the chain from a SAVED record, and the cut / paste / undo paths.
describe("BCS-FX K2 the cleared box through the grid's own paths", () => {
  it("(+) a saved row (the server filled the untouched boxes with 0) with its one typed box cleared gathers as {null, 0, 0}", () => {
    const saved = { supply_rate: 10000, install_rate: 0, combined_rate: 0 };
    expect(gatherBcsRowRates(mergeBcsRowValues(saved as never, new Map([["supply_rate", ""]])))).toEqual({ supply_rate: null, install_rate: 0, combined_rate: 0 });
  });
  it("(+) a pasted / redone 0 on a never-costed row sends its empty boxes as 0 (a typed 0 stays 0); a clear-only gesture keeps them null", () => {
    const [w] = foldBcsWrites([{ excelRow: 7, field: "supply_rate", value: 0 }], () => ({ supply_rate: null, install_rate: null, combined_rate: null }));
    expect(w.args.rates).toEqual({ supply_rate: 0, install_rate: 0, combined_rate: 0 });
    const [c] = foldBcsWrites([{ excelRow: 8, field: "supply_rate", value: null }], () => ({ supply_rate: null, install_rate: 0, combined_rate: 0 }));
    expect(c.args.rates).toEqual({ supply_rate: null, install_rate: 0, combined_rate: 0 });
  });
  it("(+) a cut / pasted blank folds as null into the whole-row write, never 0", () => {
    const [w] = foldBcsWrites([{ excelRow: 7, field: "supply_rate", value: null }], () => ({ supply_rate: 500, install_rate: null, combined_rate: null }));
    expect(w.args.rates).toEqual({ supply_rate: null, install_rate: null, combined_rate: null });
  });
  it("(+) undo of a first cost entry puts the box back as null (not entered), and redo the figure", () => {
    const entry = { deltas: [], bcsDeltas: [{ excelRow: 7, field: "supply_rate" as const, draftKey: "k", oldValue: null, newValue: 4717 }] };
    const inv = invert(entry as never) as unknown as { bcsDeltas: { oldValue: number | null; newValue: number | null }[] };
    expect(inv.bcsDeltas[0]).toMatchObject({ oldValue: 4717, newValue: null });
  });
});
