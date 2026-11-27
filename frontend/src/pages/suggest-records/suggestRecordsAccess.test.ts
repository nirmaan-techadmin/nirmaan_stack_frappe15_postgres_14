/**
 * SRS-2 T5 (access) -- "AI Suggest Records" is Admin only, exactly as Rate Master is (owner QR-WHERE (a)):
 *   + the /suggest-records route is a RoleRoute on RATE_MASTER_ACCESS, right after Rate Master's;
 *   + the sidebar item sits in Rate Master's own isNirmaanAdmin array, directly after it, with its open key and its
 *     active-highlight entry;
 *   - a non-admin (Estimates, PMO, HR) is denied by that guard, and never gets the sidebar item (the array is empty
 *     for them).
 * Read from the source, as rmAccess1.test.ts reads the Rate Master's (the sidebar has no DOM test harness).
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { RATE_MASTER_ACCESS, isNirmaanAdmin } from "@/constants/roles";
import { roleRouteState } from "@/utils/auth/ProtectedRoute";

const SRC = join(__dirname, "..", "..");
const read = (...p: string[]) => readFileSync(join(SRC, ...p), "utf8");

describe("SRS-2 the route", () => {
  const routes = read("components", "helpers", "routesConfig.tsx");
  it("is a RoleRoute on RATE_MASTER_ACCESS, right after the Rate Master route", () => {
    const rm = routes.indexOf('path: "rate-master"');
    const at = routes.indexOf('path: "suggest-records"');
    expect(rm).toBeGreaterThan(-1);
    expect(at).toBeGreaterThan(rm);
    expect(routes.slice(rm + 1, at)).not.toContain('path: "'); // no other route in between
    const block = routes.slice(at, routes.indexOf("SuggestRecordsPage", at));
    expect(block).toContain('<RoleRoute allowed={RATE_MASTER_ACCESS} what="the AI Suggest Records" />');
    expect(routes.slice(at, at + 400)).toContain('import("@/pages/suggest-records/SuggestRecordsPage")');
  });
  it("NEGATIVE: the guard denies Estimates, PMO and HR, and admits Administrator and the Admin profile", () => {
    for (const role of ["Nirmaan Estimates Executive Profile", "Nirmaan PMO Executive Profile", "Nirmaan HR Executive Profile"]) {
      expect(roleRouteState(role, "someone@example.com", RATE_MASTER_ACCESS), role).toBe("deny");
    }
    expect(roleRouteState("Nirmaan Admin Profile", "a@example.com", RATE_MASTER_ACCESS)).toBe("allow");
    expect(roleRouteState(null, "Administrator", RATE_MASTER_ACCESS)).toBe("allow");
  });
});

describe("SRS-2 the sidebar item", () => {
  const side = read("components", "layout", "NewSidebar.tsx");
  it("sits in Rate Master's isNirmaanAdmin array, directly after Rate Master", () => {
    const rm = side.indexOf('{ key: "/rate-master", icon: Table2, label: "Rate Master" }');
    const at = side.indexOf('{ key: "/suggest-records", icon: Table2, label: "AI Suggest Records" }');
    expect(rm).toBeGreaterThan(-1);
    expect(at).toBeGreaterThan(rm);
    const between = side.slice(rm + 1, at); // after Rate Master's own "{ key:"
    expect(between).not.toContain("{ key:"); // nothing else in between
    expect(between).not.toContain("]"); // the same array
    expect(side.slice(side.lastIndexOf("...(", rm), rm)).toContain("isNirmaanAdmin(role, user_id)");
  });
  it("has its open key and its active-highlight entry", () => {
    expect(side).toContain('"suggest-records",');
    expect(side).toContain('"/suggest-records": ["suggest-records"]');
  });
  it("NEGATIVE: the gate is false for a non-admin, so the item is never offered", () => {
    for (const role of ["Nirmaan Estimates Executive Profile", "Nirmaan PMO Executive Profile", "Nirmaan HR Executive Profile"]) {
      expect(isNirmaanAdmin(role, "someone@example.com"), role).toBe(false);
    }
    expect(isNirmaanAdmin("Nirmaan Admin Profile", "a@example.com")).toBe(true);
  });
});
