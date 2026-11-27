// BCS-FX K1 (owner R-BCS-182) -- the AI Suggest Records page's BCS supply text (`bcsSupplyText`): the suggested BCS supply worked
// out at the run, as the server sends it (`records.shown_bcs`).
//   (+) a figure is shown in the rates' own style; (+) the server's "not recorded (run before BCS)" is shown as sent;
//   (+) "-" for none (null, or the server's "-"); (-) a 0 sent as a figure is a real figure, never turned into "not recorded";
//   (-) the old "not yet - added when the BCS branch merges" text is gone from the model.
import { describe, expect, it } from "vitest";
import * as model from "./suggestRecordsModel";
import { BCS_NOT_RECORDED, NO_FIGURE, bcsSupplyText, rateText } from "./suggestRecordsModel";

describe("BCS-FX K1 the BCS supply on the AI Suggest Records page", () => {
  it("(+) a figure in the rates' style, the server's texts as sent, '-' for none", () => {
    expect(bcsSupplyText(4717)).toBe(rateText(4717));
    expect(bcsSupplyText(BCS_NOT_RECORDED)).toBe("not recorded (run before BCS)");
    expect(bcsSupplyText("-")).toBe(NO_FIGURE);
    expect(bcsSupplyText(null)).toBe(NO_FIGURE);
    expect(bcsSupplyText(undefined)).toBe(NO_FIGURE);
  });
  it("(-) a 0 the server sends as a figure stays a figure; the old 'not yet' text is gone", () => {
    expect(bcsSupplyText(0)).toBe(rateText(0));
    expect(JSON.stringify(model)).not.toContain("not yet - added when the BCS branch merges");
    expect((model as Record<string, unknown>).BCS_TEXT).toBeUndefined();
  });
});
