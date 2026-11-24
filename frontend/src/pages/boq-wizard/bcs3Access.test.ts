// BCS-3 -- WHO MAY SEE COST ON SCREEN (owner R2 "1a"; answer 1 "1a").
//   (+) Administrator, Admin profile, Estimates profile see cost.
//   (-) PMO, Billing, Procurement, Project Lead and every other profile do not; "Loading" / "Error" withhold.
//   (+) the two client copies of the set (`canSeeBcsCost`, `canDownloadBcsExport`) agree on every profile -- they cannot drift.
import fs from "fs";
import path from "path";
import { describe, expect, it } from "vitest";
import { canSeeBcsCost, canSeeBoqCommercials } from "./boqAccess";
import { canDownloadBcsExport } from "./PricedTenderBcsDialog";

const PROFILES = [
  "Nirmaan Admin Profile", "Nirmaan Estimates Executive Profile", "Nirmaan PMO Executive Profile", "Nirmaan Billing Executive Profile",
  "Nirmaan Procurement Executive Profile", "Nirmaan Procurement Lead Profile", "Nirmaan Project Lead Profile", "Nirmaan Project Manager Profile",
  "Nirmaan Accountant Profile", "Nirmaan HR Executive Profile", "Loading", "Error", "",
];

describe("BCS-3 canSeeBcsCost", () => {
  it("(+) Administrator, Admin and Estimates", () => {
    expect(canSeeBcsCost("anything", "Administrator")).toBe(true);
    expect(canSeeBcsCost("Nirmaan Admin Profile", "a@b.c")).toBe(true);
    expect(canSeeBcsCost("Nirmaan Estimates Executive Profile", "a@b.c")).toBe(true);
  });
  it("(-) PMO and Billing see the commercials but not the cost; nobody else sees the cost", () => {
    for (const p of ["Nirmaan PMO Executive Profile", "Nirmaan Billing Executive Profile"]) {
      expect(canSeeBoqCommercials(p, "a@b.c"), p).toBe(true);
      expect(canSeeBcsCost(p, "a@b.c"), p).toBe(false);
    }
    for (const p of PROFILES.slice(4)) expect(canSeeBcsCost(p, "a@b.c"), p).toBe(false);
  });
  it("(+) agrees with canDownloadBcsExport on every profile", () => {
    for (const p of PROFILES) expect(canSeeBcsCost(p, "a@b.c"), p).toBe(canDownloadBcsExport(p, "a@b.c"));
  });
});

// BCS-3 K2 (owner answer 1 "1a"): the two pages gate the COST READ and the block / the switch on canSeeBcsCost. Source pins: the
// pages need the whole SDK to mount, and what matters is that the read is never made for a user outside the set.
const src = (f: string) => fs.readFileSync(path.join(__dirname, f), "utf-8");
describe("BCS-3 the pages: no cost read, no cost block and no BCS switch outside Admin and Estimates", () => {
  it("(+) the pricing page: the cost read's key, the block and the switch all wait on canSeeBcsCost", () => {
    const s = src("SheetPricingPage.tsx");
    expect(s).toContain("const showBcsCost = canSeeBcsCost(bcsViewerRole, bcsViewer);");
    expect(s).toContain("showBcsCost && boqId && sheetName && liveCommitVersion !== null ? undefined : null,");
    expect(s).toContain("showBcsCost && bcsToggle === \"on\" && bcsReady && !isViewingHistory && liveCommitVersion !== null;");
    // the BCS switch (its click handler) sits inside the `{showBcsCost && (` that opens just before it
    const gate = s.indexOf("{showBcsCost && (");
    const sw = s.indexOf("onClick={handleBcsButtonClick}");
    expect(gate).toBeGreaterThan(0);
    expect(sw - gate).toBeGreaterThan(0);
    expect(sw - gate).toBeLessThan(400);
  });
  it("(+) the read-only view: the cost read and the block wait on canSeeBcsCost; the commercials stay on canSeeBoqCommercials", () => {
    const s = src("SheetViewPage.tsx");
    expect(s).toContain("const showBcsCost = canSeeBcsCost(role, user_id);");
    expect(s).toContain("showBcsCost && boqId && sheetName && commitVersion !== null ? undefined : null,");
    expect(s).toMatch(/const bcsColumnsVisible =\s*showCommercials &&\s*showBcsCost &&/);
    expect(s).toContain("const showCommercials = canSeeBoqCommercials(role, user_id);");
  });
});
