/**
 * CAT-3 (QR-NOTE (a)): the TS twin of the {{note:<item_uid>}} fill for test readers of rate files, rule for rule with
 * catalogue_lists.py: + the note's words; - an empty note or a missing item is a problem; - a note takes no attribute.
 */
import { describe, expect, it } from "vitest";
import { buildFillCatalogue, fillText, parsePlaceholder, type FillProblem } from "./catalogueFill.harness";

const built = (note: string) => buildFillCatalogue([{ item_uid: "rmi-n1", kind: "k", attributes: { item_name: "Thing" }, item_notes: note }]);

describe("CAT-3 the {{note:}} fill (test readers)", () => {
  it("+ fills the item's own note", () => {
    const p: FillProblem[] = [];
    expect(fillText("BoQ says x - {{note:rmi-n1}}", built("one price for any size"), p)).toBe("BoQ says x - one price for any size");
    expect(p).toEqual([]);
    expect(fillText("{{note:rmi-n1|lower}}", built("ONE Price"))).toBe("one price");
  });
  it("- an empty note or a missing item is a problem; a note takes no attribute", () => {
    const p: FillProblem[] = [];
    fillText("{{note:rmi-n1}}", built(""), p);
    expect(p[0][1]).toMatch(/note/);
    const q: FillProblem[] = [];
    fillText("{{note:rmi-nope}}", built("x"), q);
    expect(q[0][1]).toMatch(/no active SKU/);
    expect(parsePlaceholder("note", "rmi-n1:item_name")).toBeNull();
  });
});
