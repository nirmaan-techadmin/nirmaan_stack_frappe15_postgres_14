/**
 * SRS-2 T5 (pure) -- the AI Suggest Records page's display rules: a figure only when the server sent one ("-" for a
 * pending / not-priced / not-computed row, never 0), the status chip's colour, the default 30-day window, the filters
 * payload, the pager.
 */
import { describe, expect, it } from "vitest";

import { parseJson } from "@/lib/parseJson";

import {
  NO_FIGURE,
  batchTokensText,
  defaultFilters,
  filtersPayload,
  lastPage,
  messageOf,
  pagerText,
  rateText,
  runDateText,
  statusTone,
} from "./suggestRecordsModel";

describe("SRS-2 the rates rule", () => {
  it("shows a figure only when the server sent one", () => {
    expect(rateText(38500)).toBe("₹38,500");
    expect(rateText(0)).toBe("₹0"); // a real priced 0 (the server sends it only for a priced, in-scope kind)
  });
  it("NEGATIVE: a pending / not-priced / not-computed row shows no figure, never 0", () => {
    for (const v of [null, undefined]) expect(rateText(v)).toBe(NO_FIGURE);
  });
});

describe("SRS-2 the batch's token line (cert D2)", () => {
  it("reads each call's usage, as the store keeps it", () => {
    expect(batchTokensText({ calls: [{ usage: { input_tokens: 3097, output_tokens: 506 } }, { usage: { input_tokens: 3, output_tokens: 4 } }] }))
      .toBe("tokens in 3100 / out 510");
  });
  it("NEGATIVE: no recorded usage says so - never 0 for a count that was not recorded", () => {
    expect(batchTokensText(null)).toBe("tokens not recorded");
    expect(batchTokensText({ calls: [{ usage: null }, {}] })).toBe("tokens not recorded");
  });
});

describe("SRS-2 the status chip", () => {
  it("green priced, amber not priced, red not computed, grey pending", () => {
    expect(statusTone("priced")).toBe("priced");
    expect(statusTone("not priced: no SKU for this size")).toBe("not_priced");
    expect(statusTone("rates not computed: pricing step bundle missing")).toBe("not_computed");
    expect(statusTone("pending")).toBe("pending");
    expect(statusTone(null)).toBe("pending");
  });
});

describe("SRS-2 filters and pager", () => {
  it("defaults to the last 30 days and nothing else", () => {
    const f = defaultFilters(new Date(2026, 10, 27, 18, 0));
    expect(f.date_from).toBe("2026-10-28");
    expect(f.date_to).toBe("2026-11-27");
    expect(Object.entries(f).filter(([k, v]) => v && !k.startsWith("date_"))).toEqual([]);
  });
  it("sends only the filters that are set", () => {
    const f = { ...defaultFilters(new Date(2026, 10, 27)), boq: "BOQ-26-00375", search: "  " };
    expect(parseJson(filtersPayload(f))).toEqual({ date_from: "2026-10-28", date_to: "2026-11-27", boq: "BOQ-26-00375" });
  });
  it("50 a page", () => {
    expect(pagerText(1, 0)).toBe("");
    expect(pagerText(2, 53)).toBe("Showing 51 - 53 of 53 records. 50 per page.");
    expect(lastPage(53)).toBe(2);
    expect(lastPage(0)).toBe(1);
  });
  it("run date in the app's format; the envelope opened once", () => {
    expect(runDateText("2026-11-27 15:45:39.928077")).toBe("27-Nov-2026 15:45");
    expect(runDateText(null)).toBe(NO_FIGURE);
    expect(messageOf<{ a: number }>({ message: { a: 1 } })).toEqual({ a: 1 });
    expect(messageOf(undefined)).toBeNull();
  });
});
