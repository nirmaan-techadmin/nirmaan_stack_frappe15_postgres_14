// @vitest-environment jsdom
//
// BCS-3S (owner R1, 21 Nov 13:31 "1 yes"): a Suggest run that read an Electrical row switches BCS on for the sheet on the
// server, and its result says so (`bcs_switched_on: true`). The REAL RateSuggestProgressModal, mounted with jsdom +
// react-dom/client only (no @testing-library, frontend/CLAUDE.md), shows ONE more line, "BCS is switched on for this
// sheet.", only when this run switched it on -- and nothing on any other run.
import { createRoot, type Root } from "react-dom/client";
import { act } from "react-dom/test-utils";
import { afterEach, describe, expect, it } from "vitest";

import { RateSuggestProgressModal, SUGGEST_BCS_ON_LINE, type SuggestModalSummary } from "./RateSuggestProgressModal";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let root: Root | null = null;
let host: HTMLDivElement | null = null;
afterEach(() => {
  act(() => root?.unmount());
  host?.remove();
  root = null;
  host = null;
  document.body.innerHTML = "";
});

function mount(summary: SuggestModalSummary) {
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
  act(() => root!.render(
    <RateSuggestProgressModal open running={false} sheetName="ELE" progress={null} summary={summary} onClose={() => {}} />,
  ));
}
const dialogText = () => (document.body.querySelector('[role="dialog"]')?.textContent ?? "").replace(/\s+/g, " ").trim();
const SUCCESS: SuggestModalSummary = { status: "success", run_status: "complete", results: [{}, {}], scoped_row_count: 2 };

describe("BCS-3S: the completion message says when this run switched BCS on", () => {
  it("POSITIVE: the run switched BCS on -> the line, in exactly the owner's words", () => {
    mount({ ...SUCCESS, bcs_switched_on: true });
    expect(SUGGEST_BCS_ON_LINE).toBe("BCS is switched on for this sheet.");
    expect(document.body.querySelector('[data-testid="suggest-bcs-on"]')?.textContent).toBe("BCS is switched on for this sheet.");
    expect(dialogText()).toContain("BCS is switched on for this sheet.");
  });

  it("NEGATIVE: no flag (BCS already on, an HVAC-only run, a locked sheet) -> no line", () => {
    mount(SUCCESS);
    expect(document.body.querySelector('[data-testid="suggest-bcs-on"]')).toBeNull();
    expect(dialogText()).not.toContain("BCS");
  });

  it("NEGATIVE: a halted or failed run never shows the line, even if a payload carried the key", () => {
    mount({ status: "partial", run_status: "partial", results: [{}], attempted_count: 1, population_count: 2, bcs_switched_on: true });
    expect(dialogText()).not.toContain("BCS is switched on");
    act(() => root?.unmount());
    root = null;
    document.body.innerHTML = "";
    mount({ status: "error", run_status: "failed", halt_reason: "stopped", bcs_switched_on: true });
    expect(dialogText()).not.toContain("BCS is switched on");
  });
});
