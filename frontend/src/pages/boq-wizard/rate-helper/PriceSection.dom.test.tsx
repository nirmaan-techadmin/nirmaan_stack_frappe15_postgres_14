// @vitest-environment jsdom
//
// BCS-3 -- THE ONE SECTION PIECE (owner R3 / R5 / R6; the approved mockup, 24 Nov 14:27 / 14:49).
//   (+) BoQ and BCS sections draw with their own tag and colour, equal weight (green / blue at the same shades).
//   (+) open: the body shows; the emphasised (clicked) section has the thicker border.
//   (-) folded: ONE line only -- the tag, the figure and a chevron; the body is not rendered.
//   (-) a folded section with no figure shows the em dash, never a 0.
import { createRoot, type Root } from "react-dom/client";
import { act } from "react-dom/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PriceSection, SECTION_TAG } from "./PriceSection";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
let root: Root | null = null;
let host: HTMLDivElement | null = null;
afterEach(() => { act(() => root?.unmount()); host?.remove(); root = null; host = null; });
function mount(node: JSX.Element) {
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
  act(() => root!.render(node));
  return host;
}

describe("BCS-3 PriceSection", () => {
  it("(+) the tags read as approved, word for word", () => {
    expect(SECTION_TAG.boq).toBe("BoQ - what we quote the customer");
    expect(SECTION_TAG.bcs).toBe("BCS - our cost");
  });
  it("(+) open BoQ: green, its tag, the body; emphasised = the thicker border", () => {
    const h = mount(<PriceSection side="boq" open emphasised><p>body-line</p></PriceSection>);
    const s = h.querySelector("[data-testid='price-section-boq']")!;
    expect(s.className).toContain("bg-green-50");
    expect(s.className).toContain("border-green-300");
    expect(s.className).toContain("border-2");
    expect(s.textContent).toContain(SECTION_TAG.boq);
    expect(s.textContent).toContain("body-line");
    expect(s.querySelector("span")!.className).toContain("bg-green-700");
  });
  it("(+) open BCS: blue at the same shades (equal weight); not emphasised = the thin border", () => {
    const h = mount(<PriceSection side="bcs" open><p>cost-line</p></PriceSection>);
    const s = h.querySelector("[data-testid='price-section-bcs']")!;
    expect(s.className).toContain("bg-blue-50");
    expect(s.className).toContain("border-blue-300");
    expect(s.className).not.toContain("border-2");
    expect(s.querySelector("span")!.className).toContain("bg-blue-700");
  });
  it("(-) folded: one line only -- tag, figure, chevron; no body; a tap calls back", () => {
    const onToggle = vi.fn();
    const h = mount(<PriceSection side="bcs" open={false} foldedFigure={2009.6000000000001} onToggle={onToggle}><p>cost-line</p></PriceSection>);
    const b = h.querySelector("[data-testid='price-section-bcs-folded']") as HTMLButtonElement;
    expect(b.textContent).toBe(`${SECTION_TAG.bcs}2009.6`);
    expect(h.textContent).not.toContain("cost-line");
    act(() => b.dispatchEvent(new MouseEvent("click", { bubbles: true })));
    expect(onToggle).toHaveBeenCalledTimes(1);
  });
  it("(-) a folded section with no figure shows the em dash, never 0", () => {
    const h = mount(<PriceSection side="boq" open={false} foldedFigure={undefined} />);
    expect(h.textContent).toBe(`${SECTION_TAG.boq}—`);
  });
});
