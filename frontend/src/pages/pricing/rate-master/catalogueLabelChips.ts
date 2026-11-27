/**
 * CAT-3 (owner 2026-11-26 01:14 "1 approved" -- the mockup; ANSWER 2, 2026-11-27 23:28: "every place a person sees a label shows PLAIN
 * WORDS taken from the row's OWN value that made the label ... never 'al' / 'cu' or any other internal code. No display word is typed in
 * code"). PURE display helpers for the Rate Master Labels column and the amber "could not label" chip.
 *
 * A chip reads "<label name>: <the row's own value>" -- the label name is the label id in words ("cloth_cladding" -> "Cloth cladding"),
 * the value is the row's attribute that made the label (an ALL-CAPS word title-cased: "ALUMINIUM" -> "Aluminium"; anything else as
 * written). A capture label (the cladding gauge) shows what it captured from the row ("24"). The internal label value is never shown.
 */
import { LABEL_FROM, CAPTURE_LABELS } from "@/pages/boq-wizard/rate-helper/catalogueLabels";

export type LabelFlag = { label: string; value?: unknown; reason?: string };
type ChipItem = { labels?: Record<string, string> | null; label_flags?: LabelFlag[] | null; attributes?: Record<string, unknown> | null };

/** "cloth_cladding" -> "Cloth cladding". */
export function labelName(id: string): string {
  const w = id.replace(/_/g, " ");
  return w.charAt(0).toUpperCase() + w.slice(1);
}

/** The row's own value as plain words: an ALL-CAPS value of more than three letters is title-cased per word; anything else as written. */
export function plainValue(v: unknown): string {
  const s = String(v ?? "").trim();
  if (/[a-z]/.test(s) || s.replace(/[^A-Z]/g, "").length <= 3) return s;
  return s.toLowerCase().replace(/(^|[\s/(-])([a-z])/g, (_m, a: string, b: string) => a + b.toUpperCase());
}

/** The Labels column's chips for one row, in the rule's order: [{key, text}]. */
export function labelChips(it: ChipItem): Array<{ key: string; text: string }> {
  const out: Array<{ key: string; text: string }> = [];
  for (const [id, lv] of Object.entries(it.labels ?? {})) {
    const from = (LABEL_FROM as Record<string, string>)[id];
    const raw = from ? it.attributes?.[from] : undefined;
    const shown = CAPTURE_LABELS.has(id) ? lv : plainValue(raw);
    if (shown === "") continue;
    out.push({ key: id, text: `${labelName(id)}: ${shown}` });
  }
  return out;
}

/** The amber chips: "could not label: <label name>" for each flag. */
export function flagChips(it: ChipItem): Array<{ key: string; text: string }> {
  return (it.label_flags ?? []).map((f) => ({ key: f.label, text: `could not label: ${labelName(f.label).toLowerCase()}` }));
}

/** Rows the rule could not label (the Admin line above the grid). */
export function flaggedCount(items: ReadonlyArray<ChipItem>): number {
  return items.filter((it) => (it.label_flags ?? []).length > 0).length;
}

/** The tooltip on an amber chip (the approved wording). */
export const FLAG_TOOLTIP = "The label rule could not read this row's value. The row is saved and priced as before; rules that need this label skip it.";
