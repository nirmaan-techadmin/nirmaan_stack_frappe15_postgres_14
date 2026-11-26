/**
 * CAT-1b T1 (owner 2026-11-26 01:47 "a a a ok", QR-C-1 (a): "one parity test: TS fill = Python fill on the asset"): the TypeScript fill of the
 * test readers (`catalogueFill.harness.ts`) against `__fixtures__/catalogueFillParity.json`, which IS the Python fill -- the Python side
 * (`services/boq_rate_master/test_cat1b_wording.py` T1) re-derives every entry and must equal it. So TS fill == Python fill, byte for byte:
 * every placeholder form on a made-up catalogue (output and problems), and every placeholder text of HVAC v90 (sha256 of the filled text).
 * Plus: a placeholder that does not resolve THROWS in the readers' fill (never braces), and the shared reader `readJsonFixture` hands
 * every test the filled v90.
 */
import { createHash } from "node:crypto";
import path from "path";
import { pathToFileURL } from "url";
import { describe, expect, it } from "vitest";
import { readJsonFixture } from "../../pricing/calculatorPanelParity.harness";
import { readFileSync } from "node:fs";
import { parseJson } from "@/lib/parseJson";
import {
  PLACEHOLDER_RE, buildFillCatalogue, fillAssetForTests, fillText, type FillItem, type FillProblem,
} from "./catalogueFill.harness";

type Case = { s: string; out: string; problems: string[] };
type Fx = { forms: { items: FillItem[]; cases: Case[] }; asset: { file: string; count: number; texts: Array<{ c: string; where: string; sha256: string }> } };
type Asset = { items: FillItem[]; category_configs: Array<Record<string, unknown> & { category_id: string }> };

const FX = readJsonFixture<Fx>(pathToFileURL(path.resolve(__dirname, "__fixtures__/catalogueFillParity.json")));
const DATA = path.resolve(__dirname, "../../../../../nirmaan_stack/services/boq_rate_master/data");
// the RAW file (not through readJsonFixture, which fills): the parity is over the placeholders as stored
const rawAsset = (f: string): Asset => {
  return parseJson(readFileSync(path.join(DATA, f), "utf-8")) as Asset;
};
const sha = (s: string) => createHash("sha256").update(s, "utf8").digest("hex");

function placeholderTexts(node: unknown, p: string, cid: string, out: Array<{ c: string; where: string; s: string }>): void {
  if (typeof node === "string") {
    if (new RegExp(PLACEHOLDER_RE.source).test(node)) out.push({ c: cid, where: p, s: node });
  } else if (Array.isArray(node)) {
    node.forEach((v, i) => placeholderTexts(v, `${p}[${i}]`, cid, out));
  } else if (node !== null && typeof node === "object") {
    for (const [k, v] of Object.entries(node)) placeholderTexts(v, p ? `${p}.${k}` : k, cid, out);
  }
}

describe("CAT-1b T1 -- the TypeScript wording fill equals the Python fill, byte for byte", () => {
  it("every placeholder form (exact, |lower, |trim, both, '=' in a value, brand, numbers, inactive, missing, malformed, item forms)", () => {
    const built = buildFillCatalogue(FX.forms.items);
    expect(FX.forms.cases.length).toBeGreaterThanOrEqual(30);
    for (const c of FX.forms.cases) {
      const probs: FillProblem[] = [];
      expect(fillText(c.s, built, probs, "case"), c.s).toBe(c.out);
      expect(probs.map((p) => p[1]), c.s).toEqual(c.problems);
    }
    expect(FX.forms.cases.filter((c) => c.problems.length).length).toBeGreaterThanOrEqual(10);
  });

  it("every placeholder text of HVAC v90 fills to the Python text (sha256), with no problem", () => {
    expect(FX.asset.file).toBe("rate_master_hvac_all_v90.json");
    const a = rawAsset(FX.asset.file);
    const built = buildFillCatalogue(a.items);
    const texts: Array<{ c: string; where: string; s: string }> = [];
    for (const c of a.category_configs) placeholderTexts(c, "", c.category_id, texts);
    const got = texts.map((t) => {
      const probs: FillProblem[] = [];
      const f = fillText(t.s, built, probs, t.where);
      expect(probs, t.where).toEqual([]);
      return { c: t.c, where: t.where, sha256: sha(f) };
    });
    expect(got.length).toBe(FX.asset.count);
    expect(got).toEqual(FX.asset.texts);
  });

  it("the readers' fill THROWS on a value or item the catalogue lacks, naming the place -- never braces", () => {
    const a = rawAsset(FX.asset.file);
    const bad = structuredClone(a);
    const vp = bad.category_configs.find((c) => c.category_id === "hvac_valve_package")!;
    vp.notes = "{{cat:valve_type=No Such Valve}} and {{item:rmi-no-such-item}}";
    expect(() => fillAssetForTests(bad)).toThrow(/2 placeholder\(s\) do not resolve: hvac_valve_package\.notes/);
    // positive: v90 fills with no brace left; v89 (no placeholder) comes back as the same object
    expect(JSON.stringify(fillAssetForTests(a).category_configs)).not.toContain("{{cat:");
    const v89 = rawAsset("rate_master_hvac_all_v89.json");
    expect(fillAssetForTests(v89)).toBe(v89);
  });

  it("readJsonFixture hands a test the FILLED v90: every config equal to v89's, byte for byte", () => {
    const filled = readJsonFixture<Asset>(pathToFileURL(path.join(DATA, "rate_master_hvac_all_v90.json")));
    const v89 = rawAsset("rate_master_hvac_all_v89.json");
    expect(filled.category_configs.length).toBe(v89.category_configs.length);
    filled.category_configs.forEach((c, i) => expect(JSON.stringify(c), c.category_id).toBe(JSON.stringify(v89.category_configs[i])));
    // negative half: the raw v90 does carry placeholders, so the check above is not vacuous
    expect(JSON.stringify(rawAsset("rate_master_hvac_all_v90.json").category_configs)).toContain("{{cat:");
  });
});
