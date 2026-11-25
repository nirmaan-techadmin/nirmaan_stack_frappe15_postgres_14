/**
 * BCS-W -- A PRICING INPUT REMARK WORKED OUT FROM THE ROW'S OWN CURRENT VALUES. PURE: no React, no fetch.
 *
 * The owner's rules: "the users xan edit the 0.25 number in future ... so the text should get automatically updated of the inlut
 * changes" (2026-11-21 23:22; the standing rule that no explanatory text carries a figure that goes stale when a Pricing Input is
 * edited); BCS-W Question 1, answer 1 (a) (2026-11-25 00:20, "1a"): each Electrical remark keeps its words, its example item and
 * its list price; each worked figure is a short sum over THAT ROW'S OWN columns, worked out on screen from the current values,
 * with the rounding that sentence shows today; no pricing rule is copied and no round-up to tens is added. Answer R2 / R4 (board
 * 2): the price sentence sits in the green BoQ section, the cost sentence in the blue BCS section.
 *
 * THE TEMPLATE, as the rate file stores it (`attributes.remarks`):
 *   {%col}        the column's value as a percentage: discount 0.75 -> "75%"
 *   {rs:sum}      the sum in whole rupees (half up), thousands separated: 1217*(1-discount)*(1+supply_markup) -> "411"
 *   {rs2:sum}     the sum to the paisa: 146*share -> "29.20"
 *   {rs10:sum}    the sum rounded up to the next 10 (only where the sentence itself says "rounded up to the nearest 10")
 *   {bcs}         where the price sentences end and the cost sentences begin
 * A sum holds numbers, the row's own column names (discount, supply_markup, installation_markup, bcs_markup, wastage, ratio, share,
 * amount, factor), + - * / and brackets -- nothing else. A remark with none of these marks is drawn exactly as stored (every HVAC
 * remark, and the Electrical ones that carry no figure): `isTemplate` is false and the screen does not change.
 */

export interface RemarkSections {
  /** the price sentences (the green BoQ section) */
  boq: string;
  /** the cost sentences (the blue BCS section); "" when the remark has none */
  bcs: string;
}

const MARK = /\{(%[a-z_]+|rs10:[^}]+|rs2:[^}]+|rs:[^}]+|bcs)\}/;

/** Does this remark carry a template mark? false = draw it as stored (the screen is unchanged for it). */
export function isTemplate(remark: unknown): boolean {
  return typeof remark === "string" && MARK.test(remark);
}

/** A tiny calculator for a sum over the row's columns: numbers, names, + - * /, brackets. null = a name with no number, or bad text. */
export function evalSum(text: string, values: Readonly<Record<string, unknown>>): number | null {
  const toks = text.match(/\d+(?:\.\d+)?|[a-z_]+|[()+\-*/]|\S/g) ?? [];
  let i = 0;
  const peek = () => toks[i];
  const num = (v: unknown): number | null => {
    const n = typeof v === "number" ? v : typeof v === "string" && v.trim() !== "" ? Number(v) : NaN;
    return Number.isFinite(n) ? n : null;
  };
  function atom(): number | null {
    const t = toks[i++];
    if (t === undefined) return null;
    if (t === "(") { const v = expr(); if (toks[i++] !== ")") return null; return v; }
    if (t === "-") { const v = atom(); return v === null ? null : -v; }
    if (/^\d/.test(t)) return Number(t);
    if (/^[a-z_]+$/.test(t)) return num(values[t]);
    return null;
  }
  function term(): number | null {
    let v = atom();
    while (v !== null && (peek() === "*" || peek() === "/")) { const op = toks[i++]; const w = atom(); if (w === null) return null; v = op === "*" ? v * w : v / w; }
    return v;
  }
  function expr(): number | null {
    let v = term();
    while (v !== null && (peek() === "+" || peek() === "-")) { const op = toks[i++]; const w = term(); if (w === null) return null; v = op === "+" ? v + w : v - w; }
    return v;
  }
  const v = expr();
  return v !== null && i === toks.length && Number.isFinite(v) ? v : null;
}

// a sum like 165.5 * 0.25 = 41.375 is held as 41.374999...; the nudge rounds it half up as a person would (41.38)
const NUDGE = 1e-9;
const grouped = (n: number, digits: number) =>
  n.toLocaleString("en-IN", { minimumFractionDigits: digits, maximumFractionDigits: digits });

/** One mark's text. An unreadable mark shows "-" (the guard test proves every Electrical remark reads). */
export function markText(mark: string, values: Readonly<Record<string, unknown>>): string {
  if (mark.startsWith("%")) {
    const v = evalSum(mark.slice(1), values);
    return v === null ? "-" : `${String(Math.round(v * 100 * 1e6) / 1e6)}%`;
  }
  const at = mark.indexOf(":");
  const kind = mark.slice(0, at);
  const v = evalSum(mark.slice(at + 1), values);
  if (v === null) return "-";
  if (kind === "rs2") return grouped(Math.round(v * 100 + NUDGE) / 100, 2);
  if (kind === "rs10") return grouped(Math.ceil(v / 10 - NUDGE) * 10, 0);
  return grouped(Math.round(v + NUDGE), 0);
}

/** The remark worked out from `values` (the row's current figures), split into its BoQ and BCS sentences. */
export function remarkSections(remark: unknown, values: Readonly<Record<string, unknown>>): RemarkSections {
  const text = String(remark ?? "");
  const filled = text.replace(new RegExp(MARK.source, "g"), (_m, mark: string) => (mark === "bcs" ? "\u0000" : markText(mark, values)));
  const [boq, ...rest] = filled.split("\u0000");
  return { boq: boq.trim(), bcs: rest.join(" ").trim() };
}

/** The row's figures while it is being edited: each typed value that reads as a number replaces the stored one, so the remark
 *  follows the edit at once (board 2: "edit 75% -> the example changes at once"); a half-typed value keeps the stored figure. */
export function draftValues(
  stored: Readonly<Record<string, unknown>> | null | undefined,
  draft: Readonly<Record<string, string>>,
): Record<string, unknown> {
  const out: Record<string, unknown> = { ...(stored ?? {}) };
  for (const [k, raw] of Object.entries(draft)) {
    const n = typeof raw === "string" && raw.trim() !== "" ? Number(raw.trim()) : NaN;
    if (Number.isFinite(n)) out[k] = n;
  }
  return out;
}
