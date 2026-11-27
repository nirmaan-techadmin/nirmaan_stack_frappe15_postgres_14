// @vitest-environment jsdom
//
// BCS-6b K2 -- "PREVIOUSLY PRICED": THE PAST ROW'S BCS FIGURES (owner R-BCS-152 Q4 / Q5 a; board 3; Answer 1 Q1-C / Q1-E).
//   (+) the green box "BoQ - what we quoted the customer" holds the four values exactly as before;
//   (+) the blue box "BCS - our cost (Admin and Estimates only)" under it: BCS supply / install / combined = the keys the server sent;
//   (+) "-" for a null key (the past row has no BCS record); a stored 0 shows as "Rs 0", not "-";
//   (-) NO blue box when the keys are absent (the server leaves them out for anyone without cost access);
//   (+) any discipline: an HVAC row's pop-up shows the blue box the same way;
//   (+) "Open this row" and "Not a match" unchanged.
import { createRoot, type Root } from "react-dom/client";
import { act } from "react-dom/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BCS_COST_HEADING, BOQ_QUOTED_HEADING, PreviouslyPricedCard, bcsFig, hasPastRowBcs } from "./PreviouslyPricedMatches";
import type { MatchDetail, PreviousMatch, PreviouslyPricedView } from "./rateHelperTypes";

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
function mount(el: JSX.Element) {
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
  act(() => root!.render(el));
}
const spaced = (n: Element | null | undefined): string => {
  const out: string[] = [];
  const walk = (x: Node) => { if (x.nodeType === 3) out.push(x.textContent ?? ""); x.childNodes.forEach(walk); };
  if (n) walk(n);
  return out.join(" ").replace(/\s+/g, " ").trim();
};
(Element.prototype as unknown as { scrollIntoView: () => void }).scrollIntoView = () => {};
const all = (sel: string) => Array.from(document.body.querySelectorAll(sel));
const click = async (el: Element | null | undefined) => {
  await act(async () => { (el as HTMLElement).dispatchEvent(new MouseEvent("click", { bubbles: true })); });
};
const flush = () => act(async () => { await Promise.resolve(); await Promise.resolve(); });
const q = (sel: string) => document.querySelector(sel);

const BASE: PreviousMatch = { key: "a", boq: "BOQ-26-00172", sheet_name: "Elec. BOQ", excel_row: 318, verdict: "SAME", colour: "green",
  n1b: null, supply_rate: 16500, install_rate: 0, unit: "Nos", priced_at: "2026-06-14 10:00:00", description: "MCB DB 8 way" };
const DETAIL: MatchDetail = { boq: "BOQ-26-00172", boq_name: "Tender", project: "PROJ-1", project_name: "Sample project B",
  sheet_name: "Elec. BOQ", excel_row: 318, committed_version: 1, can_open: true, payload: { id: 318, description: "MCB DB 8 way" } };
function view(matches: PreviousMatch[]): PreviouslyPricedView {
  return { matchRun: "BRMR-1", boq: "BOQ-T", sheetName: "S", excelRow: 88, rowUnit: "Nos", matches, canMark: true, canOpenBoqs: true,
    loadDetail: vi.fn(async () => DETAIL), onMark: vi.fn(async () => {}), onUndo: vi.fn(async () => {}) };
}
async function openFirst(matches: PreviousMatch[]) {
  mount(<PreviouslyPricedCard view={view(matches)} />);
  await click(all('[data-testid="match-row"]')[0]);
  await flush();
}

describe("BCS-6b - the BCS row in the 'Previously priced' pop-up", () => {
  it("(+) green box with the four values as before, then the blue box with the past row's BCS figures", async () => {
    await openFirst([{ ...BASE, bcs_supply: 14250, bcs_install: 0, bcs_combined: null } as PreviousMatch]);
    const green = q('[data-box="boq-quoted"]')!;
    expect(spaced(green.firstElementChild)).toBe(BOQ_QUOTED_HEADING);
    expect(spaced(q('[data-testid="match-rates"]'))).toBe("Supply Rs 16,500 Install Rs 0 Total / Nos Rs 16,500 Priced on 2026-06-14");
    const blue = q('[data-box="bcs-cost"]')!;
    expect(blue).not.toBeNull();
    expect(spaced(blue.firstElementChild)).toBe(BCS_COST_HEADING);
    // (+) a figure, (+) a stored 0 is Rs 0, (+) null is "-"
    expect(spaced(q('[data-testid="match-bcs-rates"]'))).toBe("BCS supply Rs 14,250 BCS install Rs 0 BCS combined -");
    // the blue box sits directly under the green one
    expect(green.nextElementSibling).toBe(blue);
  });

  it("(+) a past row with no BCS record: all three '-'", async () => {
    await openFirst([{ ...BASE, bcs_supply: null, bcs_install: null, bcs_combined: null } as PreviousMatch]);
    expect(spaced(q('[data-testid="match-bcs-rates"]'))).toBe("BCS supply - BCS install - BCS combined -");
  });

  it("(-) the keys absent (a caller without cost access): NO blue box, the green box unchanged", async () => {
    await openFirst([BASE]);
    expect(q('[data-box="bcs-cost"]')).toBeNull();
    expect(q('[data-testid="match-bcs-rates"]')).toBeNull();
    expect(document.body.textContent).not.toContain("BCS");
    expect(spaced(q('[data-testid="match-rates"]'))).toBe("Supply Rs 16,500 Install Rs 0 Total / Nos Rs 16,500 Priced on 2026-06-14");
  });

  it("(+) any discipline: an HVAC row's pop-up shows the blue box the same way", async () => {
    await openFirst([{ ...BASE, boq: "BOQ-26-00436", sheet_name: "HVAC", excel_row: 41, description: "Supply air diffuser 600 x 600",
      bcs_supply: 1850, bcs_install: 240, bcs_combined: 0 } as PreviousMatch]);
    expect(spaced(q('[data-testid="match-bcs-rates"]'))).toBe("BCS supply Rs 1,850 BCS install Rs 240 BCS combined Rs 0");
  });

  it("(+) 'Open this row' and 'Not a match' are still there", async () => {
    await openFirst([{ ...BASE, bcs_supply: 1, bcs_install: 2, bcs_combined: 3 } as PreviousMatch]);
    const labels = all("a, button").map((b) => spaced(b));
    expect(labels).toContain("Open this row");
    expect(labels).toContain("Not a match");
  });

  it("the helpers: keys present (even null) = shown; bcsFig", () => {
    expect(hasPastRowBcs(BASE)).toBe(false);
    expect(hasPastRowBcs({ ...BASE, bcs_supply: null } as PreviousMatch)).toBe(true);
    expect([bcsFig(null), bcsFig(undefined), bcsFig(0), bcsFig(1250)]).toEqual(["-", "-", "Rs 0", "Rs 1,250"]);
  });
});
