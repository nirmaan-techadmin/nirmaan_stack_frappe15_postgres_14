// ELR-1 AC2 (owner R-NOTES-RULE: a note is required on a field that is TYPED, RENDERS and is MANDATORY; R-SCOPE (5)
// "the validator then enforces notes for Electrical"; R-NOTE A, 2026-10-27 23:00): the audit's ATTRIBUTE branch.
import { describe, expect, it } from "vitest";
import fs from "fs";
import path from "path";
import { pathToFileURL } from "url";
import { readJsonFixture } from "@/pages/pricing/calculatorPanelParity.harness";
import type { RateCategoryConfig, RateMasterItem } from "@/pages/pricing/rate-master/rateMasterTypes";
import { auditPanelFields, missingNotes } from "./panelFieldAudit";
import { makePricingSheetHelper } from "./pricingSheetHelper";
import { isSuggestion } from "./rateHelperTypes";

const DATA = path.resolve(__dirname, "../../../../../nirmaan_stack/services/boq_rate_master/data");
// the asset this slice minted, NAMED: its notes are what the pin below is about
const asset = readJsonFixture<never>(pathToFileURL(path.join(DATA, "rate_master_electrical_all_v67.json"))) as
  { items: RateMasterItem[]; category_configs: RateCategoryConfig[] };
const items: RateMasterItem[] = asset.items.map((i) => ({ ...i, discipline: "Electrical" }));
const cfgOf = (id: string): RateCategoryConfig => structuredClone(asset.category_configs.find((c) => c.category_id === id)!);

const RUNS_NOTE = "How many parallel runs of this cable the row needs, e.g. 2 runs of 4C x 95 sqmm. Leave 1 if the BoQ names a single run.";

/**
 * THE NAMED EXPECTED-MISSING LIST (owner AC2 (c)): the typed + rendered + mandatory Electrical fields that carry no note
 * YET. It may only SHRINK -- ELR-2 writes their notes and empties it. wiring_cabling is ENFORCED now (absent here).
 */
const EXPECTED_MISSING: Record<string, string[]> = {
  point_wiring: ["circuit_wire1_runs", "circuit_wire2_runs", "plate_qty", "points", "socket_qty", "switch_qty", "wire1_runs", "wire2_runs"],
  db_switchgear: ["db_shell_qty", "enclosure_qty", "mcb1_qty", "mcb2_qty", "mcb3_qty", "mcb4_qty", "mcb5_qty"],
  popup_boxes: ["module_count", "plate_qty", "socket1_qty", "socket2_qty", "socket3_qty", "socket4_qty", "switch_qty"],
  switches_sockets: ["plate_qty", "socket1_qty", "socket2_qty", "socket3_qty", "socket4_qty", "switch_qty"],
};

describe("ELR-1 AC2: the field audit measures Electrical (the attribute branch)", () => {
  it("every Electrical category: the fields missing a note are EXACTLY the named list -- wiring_cabling none", () => {
    const got: Record<string, string[]> = {};
    for (const c of asset.category_configs) {
      const m = missingNotes(c, items);
      if (m.length) got[c.category_id] = m;
    }
    expect(got).toEqual(EXPECTED_MISSING);
    expect(Object.values(EXPECTED_MISSING).flat().length).toBe(28);
  });

  it("wiring_cabling 'Runs': typed, rendered, mandatory -- and carries the R-NOTE A text", () => {
    const runs = auditPanelFields(cfgOf("wiring_cabling"), items).find((f) => f.attr === "runs")!;
    expect([runs.typed, runs.renders, runs.mandatory, runs.needsNote]).toEqual([true, true, true, true]);
    expect(runs.note).toBe(RUNS_NOTE);
  });

  it("NEGATIVE (ENFORCED): the same config without the note is refused, naming the field", () => {
    const cfg = cfgOf("wiring_cabling");
    delete (cfg.attribute_definitions.find((d) => d.id === "runs") as { note?: string }).note;
    expect(missingNotes(cfg, items)).toEqual(["runs"]);
  });

  it("each property both ways, from the product: a dropdown needs no note; a field made optional needs none", () => {
    const cfg = cfgOf("wiring_cabling");
    // TYPED: Material is a dropdown -- rendered and mandatory, no note asked
    const material = auditPanelFields(cfg, items).find((f) => f.attr === "material")!;
    expect([material.typed, material.mandatory, material.needsNote]).toEqual([false, true, false]);
    // MANDATORY: point_wiring's circuit length is typed and optional (a derived default fills it) -- no note asked
    const pw = auditPanelFields(cfgOf("point_wiring"), items);
    const optionalTyped = pw.filter((f) => f.typed && !f.mandatory).map((f) => f.attr);
    expect(optionalTyped.length).toBeGreaterThan(0);
    for (const a of optionalTyped) expect(pw.find((f) => f.attr === a)!.needsNote, a).toBe(false);
  });

  it("the audit names no attribute, category or discipline: the module source carries none", () => {
    const src = fs.readFileSync(path.join(__dirname, "panelFieldAudit.ts"), "utf-8");
    const code = src.split("\n").filter((l) => !/^\s*(\*|\/\/|\/\*)/.test(l)).join("\n");
    for (const banned of ["runs", "wiring", "Electrical", "plate_qty", "hvac_"]) expect(code, banned).not.toContain(banned);
  });
});

describe("ELR-1 AC2 (a): the attribute path carries the definition's note to the panel (and the calculator)", () => {
  const helper = (cfg: RateCategoryConfig, ext?: Record<string, { value: string | null; confidence: number }>) =>
    makePricingSheetHelper({
      configsByCategory: new Map(asset.category_configs.map((c) => [c.category_id, c])),
      items, extractionByRow: new Map(ext ? [[9, { excelRow: 9, description: "4C x 95 sqmm armoured copper cable", attributes: ext }]] : []),
    } as never).compute({ excelRow: 9, description: "4C x 95 sqmm armoured copper cable", nodeType: "Line Item",
      category: cfg.category_id, discipline: "Electrical", rateKinds: [] } as never);

  it("a BoQ row (stored answers) and the calculator (no row) both show Runs with its note; no other field has one", () => {
    for (const ext of [{ runs: { value: "2", confidence: 1 } }, undefined]) {
      const r = helper(cfgOf("wiring_cabling"), ext);
      if (!isSuggestion(r)) throw new Error("no suggestion");
      const noted = r.workings.attributes.filter((a) => a.typedNote).map((a) => [a.id, a.typedNote]);
      expect(noted).toEqual([["runs", RUNS_NOTE]]);
    }
  });

  it("HVAC Cables (an alias of wiring) reads wiring's config, so its Runs carries the same note", () => {
    const configs = new Map(asset.category_configs.map((c) => [c.category_id, c] as [string, RateCategoryConfig]));
    configs.set("hvac_cables", { category_id: "hvac_cables", discipline: "HVAC", alias_of: { discipline: "Electrical", category_id: "wiring_cabling" },
      attribute_definitions: [], pipelines: {} } as never);
    const r = makePricingSheetHelper({ configsByCategory: configs, items, extractionByRow: new Map() } as never)
      .compute({ excelRow: 1, description: "", nodeType: "Line Item", category: "hvac_cables", discipline: "HVAC", rateKinds: [] } as never);
    if (!isSuggestion(r)) throw new Error("no suggestion");
    expect(r.workings.attributes.find((a) => a.id === "runs")?.typedNote).toBe(RUNS_NOTE);
  });

  it("the panel draws it in the item-list path's own box and style (one class, two call sites)", () => {
    const src = fs.readFileSync(path.join(__dirname, "RateHelperPanel.tsx"), "utf-8");
    expect(src).toContain('{a.typedNote && <p className={TYPED_NOTE_CLASS} data-testid="attribute-typed-note">{a.typedNote}</p>}');
    expect(src).toContain("{f.typedNote && <p className={TYPED_NOTE_CLASS}>{f.typedNote}</p>}");
    expect(src).toContain('export const TYPED_NOTE_CLASS = "text-[10px] leading-tight opacity-90";');
  });
});
