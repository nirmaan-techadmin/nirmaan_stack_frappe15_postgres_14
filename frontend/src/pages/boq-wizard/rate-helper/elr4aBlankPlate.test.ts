// ELR-4a AC4 (owner R-PW-BLANK / R-KEEP, 2026-10-29; Q1 (A)): point wiring's "Blank plate" is hidden on the panel and
// the calculator by `panel: false`, and the note N1 says how the blank count is worked out, in the field's place;
// switches & sockets and pop-up boxes keep "Blank plate"; no priced figure moves.
import { describe, expect, it } from "vitest";
import { blanksWorkedOutNote } from "./pricingSheetHelper";
import { isSuggestion, type HelperResult, type WorkingsAttribute } from "./rateHelperTypes";
import { HIDDEN, LIVE, N1, boqResult, calcResult, pwRow } from "./elr4aBlankPlate.harness";

const attrs = (r: HelperResult): WorkingsAttribute[] => (isSuggestion(r) ? r.workings.attributes : []);
const ids = (r: HelperResult) => attrs(r).map((a) => a.id);
const priced = (r: HelperResult) => isSuggestion(r) && Object.keys(r.values ?? {}).length > 0;

describe("ELR-4a: the note N1, written from the config", () => {
  it("POSITIVE: point wiring's blanks block (no display field) gives N1, on 'Blank plate qty'", () => {
    expect(blanksWorkedOutNote(LIVE.get("point_wiring")!)).toEqual({ attr: "blank_qty", text: N1 });
  });

  it("NEGATIVE: switches & sockets and pop-up boxes show their blanker on 'Blank plate' -> no note", () => {
    expect(blanksWorkedOutNote(LIVE.get("switches_sockets")!)).toBeNull();
    expect(blanksWorkedOutNote(LIVE.get("popup_boxes")!)).toBeNull();
    const shown = structuredClone(LIVE.get("point_wiring")!);
    for (const pl of Object.values(shown.pipelines ?? {})) for (const s of pl.steps ?? []) {
      const b = (s as { params?: { blanks?: Record<string, unknown> } }).params?.blanks;
      if (b) b.display_attr = "blank_item";
    }
    expect(blanksWorkedOutNote(shown)).toBeNull();
  });

  it("the words follow the config: the blanker's name and a term's weight", () => {
    const c = structuredClone(LIVE.get("point_wiring")!);
    for (const pl of Object.values(c.pipelines ?? {})) for (const s of pl.steps ?? []) {
      const p = (s as { params?: { blanks?: Record<string, unknown>; terms?: Array<Record<string, unknown>> } }).params;
      if (p?.blanks) { p.blanks.item_when_positive = "2M Blanker"; p.terms![0].weight = 3; }
    }
    const t = blanksWorkedOutNote(c)!.text;
    expect(t).toContain("(a socket takes 3, a switch 1)");
    expect(t).toContain("gets a '2M Blanker'");
  });
});

describe("ELR-4a AC4: point wiring's 'Blank plate' gone from both screens, the note in its place", () => {
  it("calculator: WAS 'Blank plate' starred between 'Socket qty' and 'Blank plate qty'; NOW gone, N1 on 'Blank plate qty'", () => {
    const was = calcResult(LIVE, "point_wiring");
    expect(ids(was)).toContain("blank_item");
    expect(attrs(was).find((a) => a.id === "blank_item")!.required).toBe(true);
    const now = calcResult(HIDDEN, "point_wiring");
    expect(ids(now)).not.toContain("blank_item");
    const at = ids(now).indexOf("blank_qty");
    expect(ids(now)[at - 1]).toBe("socket_qty");
    expect(attrs(now)[at].leadNote).toBe(N1);
    expect(attrs(now).filter((a) => a.leadNote).length).toBe(1);
    // "Blank plate qty" itself is unchanged: same label, not starred, editable
    const qty = attrs(now)[at];
    expect(qty.label).toBe("Blank plate qty");
    expect(qty.required).toBeUndefined();
    expect(qty.readOnly).toBeUndefined();
  });

  it("BoQ panel: the same field list and note as the calculator (calculator = panel)", () => {
    const panel = boqResult(HIDDEN, "point_wiring", pwRow("None"));
    expect(ids(panel)).toEqual(ids(calcResult(HIDDEN, "point_wiring")));
    expect(attrs(panel).find((a) => a.id === "blank_qty")!.leadNote).toBe(N1);
  });

  it("NO PRICE MOVES: a priced row prices the same figures with the field hidden", () => {
    const was = boqResult(LIVE, "point_wiring", pwRow("None"));
    const now = boqResult(HIDDEN, "point_wiring", pwRow("None"));
    expect(priced(was)).toBe(true);
    expect(isSuggestion(now) && now.values).toEqual(isSuggestion(was) && was.values);
  });

  it("Q1 (A), the declared change: WAS a row whose 'Blank plate' read came back blank refused on that field alone; NOW it prices, at the figures of the same row read 'None'", () => {
    const was = boqResult(LIVE, "point_wiring", pwRow(null));
    expect(priced(was)).toBe(false);
    expect(isSuggestion(was) && was.workings.derivation.join(" ")).toContain("Missing to price: Blank plate -- fill them to compute a rate.");
    const now = boqResult(HIDDEN, "point_wiring", pwRow(null));
    expect(priced(now)).toBe(true);
    expect(isSuggestion(now) && now.values).toEqual(isSuggestion(boqResult(LIVE, "point_wiring", pwRow("None"))) && (boqResult(LIVE, "point_wiring", pwRow("None")) as { values: unknown }).values);
  });
});

describe("ELR-4a AC4 (R-KEEP): switches & sockets and pop-up boxes keep 'Blank plate', with no note", () => {
  it("both screens", () => {
    for (const cat of ["switches_sockets", "popup_boxes"]) {
      for (const r of [calcResult(HIDDEN, cat), boqResult(HIDDEN, cat, {})]) {
        expect(ids(r), cat).toContain("blank_item");
        expect(attrs(r).find((a) => a.id === "blank_item")!.label, cat).toBe("Blank plate");
        expect(attrs(r).some((a) => a.leadNote), cat).toBe(false);
      }
    }
  });
});
