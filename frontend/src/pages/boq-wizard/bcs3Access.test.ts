// BCS-3 -- WHO MAY SEE COST ON SCREEN (owner R2 "1a"; answer 1 "1a").
//   (+) Administrator, Admin profile, Estimates profile see cost.
//   (-) PMO, Billing, Procurement, Project Lead and every other profile do not; "Loading" / "Error" withhold.
//   (+) the two client copies of the set (`canSeeBcsCost`, `canDownloadBcsExport`) agree on every profile -- they cannot drift.
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
