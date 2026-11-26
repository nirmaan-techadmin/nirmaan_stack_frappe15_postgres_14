/**
 * BoqSummaryBlock -- the BoQ summary on the BoQ's main page, and its one line on a ticked sheet's own Summary (slice BCS-5;
 * owner R1 - R8, approved mockup 26 Nov 14:07). For Admin and Estimates only (`canSeeBcsCost`): for anyone else nothing renders
 * and no cost read is made.
 *
 * ONE LINE PER PRICEABLE SHEET (the server lists them in sheet order); BoQ amount / BCS supply / typed installation come from THE
 * SAME functions the sheet's own Summary uses (`rollupByParent`, which runs `bcsTotalCell` / `boqTotalAmount` / `rollBcsSections`)
 * over the same three per-sheet reads the sheet page makes, so a sheet's figures here equal its own Summary's. BCS supply is the
 * sheet's BCS total with the install box read as 0; typed installation is it with the supply / combined boxes read as 0.
 * The TICKED sheets are ONE clubbed block: one installation figure (area x the live Rs per sq ft + floor cutting, from the server)
 * and one margin; a ticked sheet's typed installation is NOT counted (owner, mockup point A). Margin = 1 - (BCS supply + BCS
 * installation) / BoQ amount (`bcsMarginPercent`). A blank is "no value yet", never 0. Nothing here writes a price or a cost:
 * the only write is `save_boq_summary_inputs` (area, ticks, the two installation parts).
 */
import { useContext, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { FrappeContext, useFrappeGetCall, useFrappePostCall, type FrappeConfig } from "@/lib/frappe";
import { useUserData } from "@/hooks/useUserData";
import { canSeeBcsCost } from "./boqAccess";
import { amountExceptions, rollupByParent, rowRanges, type AmountExceptions, type RollupNode } from "./pricingRollup";
import { matchRowHref } from "./rate-helper/PreviouslyPricedMatches";
import { bcsAmountColumns, bcsLiveRateKinds, bcsMarginPercent, formatBcsMargin } from "./bcsColumns";
import type { BcsSectionTotals } from "./bcsRollup";
import { bcsFigureText } from "./rate-helper/bcsSide";
import type { BcsRowRate, BcsSource, ColumnDescriptor, ColumnFormula, GetBcsStateResponse, GetPricedRowsResponse,
  GetSheetBcsRatesResponse, PricedRow, ReconciliationChoiceRef } from "./boqTypes";

const GET = "nirmaan_stack.api.boq.wizard.boq_summary.get_boq_summary_inputs";
const SAVE = "nirmaan_stack.api.boq.wizard.boq_summary.save_boq_summary_inputs";
/** The pause before a typed area saves, as slice 4's helper-edit saves (`SheetPricingPage.HELPER_EDIT_SAVE_PAUSE_MS`). */
export const SUMMARY_SAVE_PAUSE_MS = 1000;
export const ENTER_AREA = "- enter the area";

// ── the server's answer ───────────────────────────────────────────────────────────────────────────────────────────────
export interface FloorRow { sheet_name: string; excel_row: number; text: string; qty: number; unit: string; reason?: string }
export interface BoqSummaryResponse {
  boq: string; has_record: boolean; area_sqft: number | null; covered_sheets: string[] | null;
  rates: { install_per_sqft: number | null; tray_cutting: number | null }; carpet_area: number | null;
  sheets: { sheet_name: string; sheet_order: number | null; committed_version: number; default_ticked?: boolean; ticked: boolean }[];
  ticked: string[];
  floor: { caught: FloorRow[]; mentioned: FloorRow[]; no_reading_rows: number; metres: number; system_amount: number | null };
  installation: { area_part_system: number | null; area_part: number | null; area_part_changed: boolean;
    floor_part_system: number | null; floor_part: number | null; floor_part_changed: boolean; total: number | null };
}

// ── the per-sheet figures (pure) ──────────────────────────────────────────────────────────────────────────────────────
export interface SheetReads {
  rows: PricedRow[]; descriptors: ColumnDescriptor[]; formulas: ColumnFormula[]; recon: ReconciliationChoiceRef[];
  /** The sheet's BCS readiness (get_bcs_state.is_ready): off = no cost figures, as the sheet's own Summary shows none. */
  bcsOn: boolean; qtySource: BcsSource | null; amountSource: BcsSource | null; rates: BcsRowRate[];
}
export interface SheetFigures {
  boqAmount: number | null; bcsSupply: number | null; typedInstall: number | null; rowsWithAmount: number; rowsWithSupply: number;
  /** BCS-6a: the note's three exception lists for this sheet (`amountExceptions`), only where BCS is on (a margin is shown). */
  exceptions?: AmountExceptions | null;
}

/** The stored cost rows keyed by Excel row, with one side read as 0 (install for BCS supply; supply + combined for install). */
function ratesWithout(rates: BcsRowRate[], side: "install" | "supply"): Map<number, BcsRowRate> {
  const m = new Map<number, BcsRowRate>();
  for (const r of rates) m.set(r.excel_row, side === "install" ? { ...r, install_rate: 0 } : { ...r, supply_rate: 0, combined_rate: 0 });
  return m;
}

/** Each node's OWN figure = its rolled figure minus its children's rolled figures (the rollup publishes rolled ones only). */
function ownFigures(roots: RollupNode[], by: Map<number, BcsSectionTotals>, pick: (t: BcsSectionTotals) => number | null) {
  const out = new Map<number, number>();
  const walk = (n: RollupNode) => {
    const kids = n.children.reduce((s, c) => s + (pick(by.get(c.rowIndex) ?? EMPTY) ?? 0), 0);
    out.set(n.rowIndex, (pick(by.get(n.rowIndex) ?? EMPTY) ?? 0) - kids);
    n.children.forEach(walk);
  };
  roots.forEach(walk);
  return out;
}
const EMPTY: BcsSectionTotals = { cost: null, tendered: null, margin: { kind: "blank", reason: "no_cost" } };

/** One sheet's BoQ amount, BCS supply, typed installation and "rows with BCS supply", through the sheet Summary's own functions.
 *  The BoQ amount = the rollup's tendered (`rollupByParent` -> `boqTotalAmount` over the amount ON SCREEN: the declared BOQ
 *  Total formula, else the sheet's own amount columns by `bcsAmountColumns`' rule; formulas AND reconciliation choices; BCS-6a:
 *  one-sided rows counted, no-rate rows without an amount left out) - the figure the sheet's Summary panel divides by. */
export function sheetFigures(r: SheetReads): SheetFigures {
  const kinds = bcsLiveRateKinds(r.descriptors);
  // The amount side: the confirmed columns where stored, else the sheet's own amount columns (`bcsAmountColumns`, the margin's rule).
  const amountSource: BcsSource = { mode: r.amountSource?.mode ?? "", columns: [...bcsAmountColumns(r.amountSource, r.descriptors)] };
  const roll = (side: "install" | "supply") =>
    rollupByParent(r.rows, r.descriptors, r.formulas, r.recon, {
      ratesByExcelRow: r.bcsOn ? ratesWithout(r.rates, side) : new Map(), kinds, qtySource: r.qtySource, amountSource,
    });
  const sup = roll("install");
  const ins = roll("supply");
  const supplyOwn = ownFigures(sup.roots, sup.bcs?.byRowIndex ?? new Map<number, BcsSectionTotals>(), (t) => t.cost);
  // BCS-6a: the BoQ amount IS the rollup's per-row tendered -- the denominator the sheet's grid and Summary panel divide
  // by (the amount on screen, one-sided rows counted, no-rate rows without an amount left out) -- so the three surfaces
  // cannot disagree. Until BCS-6a this block re-walked `boqTotalAmount` itself over the rollup's own amounts.
  const tenderedOwn = ownFigures(sup.roots, sup.bcs?.byRowIndex ?? new Map<number, BcsSectionTotals>(), (t) => t.tendered);
  const boqAmount: number | null = sup.bcs?.grand.tendered ?? null;
  let rowsWithAmount = 0;
  let rowsWithSupply = 0;
  const walk = (n: RollupNode) => {
    if ((tenderedOwn.get(n.rowIndex) ?? 0) > 0) {
      rowsWithAmount += 1;
      if ((supplyOwn.get(n.rowIndex) ?? 0) > 0) rowsWithSupply += 1;
    }
    n.children.forEach(walk);
  };
  sup.roots.forEach(walk);
  const costRows = new Set(r.rates.filter((x) => Number(x.supply_rate) || Number(x.install_rate) || Number(x.combined_rate))
    .map((x) => x.excel_row));
  return {
    boqAmount,
    bcsSupply: r.bcsOn ? (sup.bcs?.grand.cost ?? null) : null,
    typedInstall: r.bcsOn ? (ins.bcs?.grand.cost ?? null) : null,
    rowsWithAmount, rowsWithSupply,
    exceptions: r.bcsOn ? amountExceptions(r.rows, r.descriptors, r.formulas, r.recon, costRows) : null,
  };
}

// ── the table (pure) ──────────────────────────────────────────────────────────────────────────────────────────────────
export interface Totals { boqAmount: number | null; bcsSupply: number | null; install: number | null; rowsWithAmount: number;
  rowsWithSupply: number; margin: number | null }
export interface SummaryLine { sheet: string; ticked: boolean; fig: SheetFigures | null; install: number | null; margin: number | null }
export interface SummaryTable { lines: SummaryLine[]; block: Totals | null; total: Totals; needsArea: boolean }

const sum = (xs: (number | null)[]): number | null => (xs.some((x) => x !== null) ? xs.reduce<number>((s, x) => s + (x ?? 0), 0) : null);

/** 1 - (supply + install) / amount as a percentage, or null (blank) when there is no cost or no usable amount. */
export function marginOf(amount: number | null, supply: number | null, install: number | null): number | null {
  if (supply === null && install === null) return null;
  const c = bcsMarginPercent({ kind: "value", value: (supply ?? 0) + (install ?? 0) },
    amount === null ? { kind: "blank", reason: "no_amount" } : { kind: "value", value: amount });
  return c.kind === "value" ? c.value : null;
}

function totalsOf(lines: SummaryLine[], install: number | null, margin: number | null): Totals {
  return { boqAmount: sum(lines.map((l) => l.fig?.boqAmount ?? null)), bcsSupply: sum(lines.map((l) => l.fig?.bcsSupply ?? null)),
    install, margin, rowsWithAmount: lines.reduce((s, l) => s + (l.fig?.rowsWithAmount ?? 0), 0),
    rowsWithSupply: lines.reduce((s, l) => s + (l.fig?.rowsWithSupply ?? 0), 0) };
}

/** The lines, the ticked block and the BoQ total (owner R1, R2; mockup points A, C). `installation` null = no area yet. */
export function summaryTable(sheets: { sheet_name: string; ticked: boolean }[], figs: Map<string, SheetFigures>,
  installation: number | null): SummaryTable {
  const lines: SummaryLine[] = sheets.map((s) => {
    const fig = figs.get(s.sheet_name) ?? null;
    if (s.ticked) return { sheet: s.sheet_name, ticked: true, fig, install: null, margin: null };
    const install = fig?.typedInstall ?? null; // an unticked sheet: the installation typed on its rows
    return { sheet: s.sheet_name, ticked: false, fig, install, margin: fig ? marginOf(fig.boqAmount, fig.bcsSupply, install) : null };
  });
  const ticked = lines.filter((l) => l.ticked);
  const needsArea = ticked.length > 0 && installation === null;
  let block: Totals | null = null;
  if (ticked.length > 0) {
    const t = totalsOf(ticked, installation, null);
    block = { ...t, margin: needsArea ? null : marginOf(t.boqAmount, t.bcsSupply, installation) };
  }
  const install = needsArea ? null : sum([block ? installation : null, ...lines.filter((l) => !l.ticked).map((l) => l.install)]);
  const everyCost = lines.every((l) => l.fig !== null
    && (l.fig.bcsSupply !== null || (l.ticked ? installation !== null : l.fig.typedInstall !== null)));
  const t = totalsOf(lines, install, null);
  return { lines, block, needsArea,
    total: { ...t, margin: !needsArea && everyCost ? marginOf(t.boqAmount, t.bcsSupply, install) : null } };
}

// ── loading ──────────────────────────────────────────────────────────────────────────────────────────────────────────
/** The summary's server half, for a cost viewer only (the key is null otherwise: no cost read fires). */
export function useBoqSummary(boqId: string | undefined) {
  const { user_id, role } = useUserData();
  const allowed = canSeeBcsCost(role as string, user_id as string);
  const res = useFrappeGetCall<{ message: BoqSummaryResponse }>(GET, { boq: boqId ?? "" }, allowed && boqId ? undefined : null);
  return { allowed, summary: allowed ? (res.data?.message ?? null) : null, mutate: res.mutate, error: res.error };
}

/** The listed sheets' three reads, fetched one sheet after another (never N parallel calls), then their figures. */
export function useSheetFigures(boqId: string | undefined, sheets: { sheet_name: string; committed_version: number }[]) {
  const { call } = useContext(FrappeContext) as FrappeConfig;
  const [figs, setFigs] = useState<Map<string, SheetFigures>>(new Map());
  const [failed, setFailed] = useState<string[]>([]);
  const key = JSON.stringify(sheets.map((s) => [s.sheet_name, s.committed_version]));
  useEffect(() => {
    if (!boqId || sheets.length === 0) return;
    let cancelled = false;
    void (async () => {
      const out = new Map<string, SheetFigures>();
      const bad: string[] = [];
      for (const s of sheets) {
        try {
          const args = { boq_name: boqId, sheet_name: s.sheet_name }; // VERBATIM (#152)
          const priced = ((await call.get("nirmaan_stack.api.boq.wizard.pricing.get_priced_rows", args))?.message ?? {}) as GetPricedRowsResponse;
          const cv = priced.commit_version ?? s.committed_version;
          const state = ((await call.get("nirmaan_stack.api.boq.wizard.bcs.get_bcs_state", { ...args, committed_version: cv }))?.message ?? null) as GetBcsStateResponse | null;
          const rates = ((await call.get("nirmaan_stack.api.boq.wizard.bcs.get_sheet_bcs_rates", { ...args, committed_version: cv }))?.message ?? null) as GetSheetBcsRatesResponse | null;
          out.set(s.sheet_name, sheetFigures({ rows: priced.rows ?? [], descriptors: priced.column_descriptors ?? [],
            formulas: priced.column_formulas ?? [], recon: priced.reconciliation_choices ?? [], bcsOn: !!state?.is_ready,
            qtySource: state?.bcs_qty_source ?? null, amountSource: state?.bcs_amount_source ?? null, rates: rates?.rows ?? [] }));
        } catch {
          bad.push(s.sheet_name);
        }
        if (cancelled) return;
      }
      setFigs(out);
      setFailed(bad);
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `key` is the sheets' identity
  }, [boqId, key, call]);
  return { figs, failed, loading: sheets.length > 0 && figs.size + failed.length === 0 };
}

// ── display ──────────────────────────────────────────────────────────────────────────────────────────────────────────
/** A figure as the BCS display rule shows it (whole rupees, rounded up, en-IN); a zero reads "0" (bcsFigureText(0) gives "-0"). */
const fig = (v: number | null | undefined): string => {
  if (v === null || v === undefined) return "";
  const t = bcsFigureText(v);
  return t === "-0" ? "0" : t;
};
const pct = (v: number | null): string => (v === null ? "" : formatBcsMargin(v));
const td = "px-2 py-1.5 text-right tabular-nums align-top";

/** How many ranges the long list shows before "show all" (owner R5, 00:28: "the long list format is correct, but it should be
 *  shown in the block itself"). */
export const ROW_LIST_SHOWN = 8;

/**
 * BCS-6a -- THE LONG-LIST FORM (owner R5 00:26 "how do wew show all these ows in the list on the note"; mockup board 2): the
 * count first, the row numbers joined into ranges, "show all" opening the full list, each row number taking the user to that
 * row -- by `onJump` (the sheet page's own grid jump) or by `hrefFor` (the pricing route's `?row=` link, `matchRowHref`). An
 * empty list reads "none on this sheet". Shared by the sheet's Summary panel note and the BoQ summary's grey lines.
 */
export function RowRangeList({ rows, onJump, hrefFor }: { rows: readonly number[]; onJump?: (excelRow: number) => void;
  hrefFor?: (excelRow: number) => string }) {
  const [all, setAll] = useState(false);
  if (rows.length === 0) return <span>none on this sheet</span>;
  const ranges = rowRanges(rows);
  const shown = all ? ranges : ranges.slice(0, ROW_LIST_SHOWN);
  const num = (n: number) => onJump
    ? <button type="button" aria-label={`Go to row ${n}`} className="text-primary hover:underline" onClick={() => onJump(n)}>{n}</button>
    : hrefFor ? <Link aria-label={`Go to row ${n}`} className="text-primary hover:underline" to={hrefFor(n)}>{n}</Link> : <span>{n}</span>;
  return (
    <span>
      {rows.length} {rows.length === 1 ? "row" : "rows"}:{" "}
      {shown.map(([a, b], k) => (
        <span key={a}>{k > 0 ? ", " : ""}{num(a)}{b !== a && <>-{num(b)}</>}</span>
      ))}
      {ranges.length > ROW_LIST_SHOWN && (
        <>{!all && " ..."} <button type="button" className="text-primary hover:underline" onClick={() => setAll(!all)}>
          {all ? "show fewer" : "show all"}</button></>
      )}
    </span>
  );
}

/** The BoQ summary's short grey lines under a sheet's name, one per exception that applies (owner R3 / R5; mockup board 1). */
export function SheetExceptionLines({ ex, boqId, sheet }: { ex: AmountExceptions | null | undefined; boqId: string | undefined;
  sheet: string }) {
  if (!ex) return null;
  const href = (n: number) => matchRowHref({ boq: boqId ?? "", sheet_name: sheet, excel_row: n });
  const line = (label: string, rows: number[]) => rows.length === 0 ? null : (
    <span className="block text-[11px] text-muted-foreground">{label}: <RowRangeList rows={rows} hrefFor={href} /></span>);
  return (
    <>
      {line("Priced, but the uploaded file's amount kept", ex.keptDocument)}
      {line("Not priced in the app yet - the uploaded file's rate used", ex.fileRate)}
      {line("No rate anywhere - left out", ex.leftOut)}
    </>
  );
}

/** "Edit" / "Remove" (or "Back to system figure" once changed) for one installation part (R-BCS-144). */
function PartControls({ changed, onSave }: { changed: boolean; onSave: (v: string) => void }) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState("");
  const link = "text-xs text-primary hover:underline";
  if (editing) return (
    <span className="inline-flex items-center gap-1">
      <input aria-label="Figure" className="h-6 w-24 rounded border px-1 text-xs" value={text} onChange={(e) => setText(e.target.value)} />
      <button type="button" className={link} onClick={() => { onSave(text.replace(/,/g, "")); setEditing(false); }}>Save</button>
      <button type="button" className={link} onClick={() => setEditing(false)}>Cancel</button>
    </span>
  );
  return (
    <span className="inline-flex items-center gap-2">
      <button type="button" className={link} onClick={() => { setText(""); setEditing(true); }}>Edit</button>
      <button type="button" className={link} onClick={() => onSave("0")}>Remove</button>
      {changed && <span className="text-xs italic text-amber-700">changed by user</span>}
      {changed && <button type="button" className={link} onClick={() => onSave("")}>Back to system figure</button>}
    </span>
  );
}

export function BoqSummaryBlock({ boqId }: { boqId: string | undefined }) {
  const { allowed, summary, mutate } = useBoqSummary(boqId);
  if (!allowed) return null; // everyone else sees the page exactly as before; no cost read fired
  return <BoqSummaryBody boqId={boqId} summary={summary} mutate={mutate} />;
}

function BoqSummaryBody({ boqId, summary, mutate }: { boqId: string | undefined; summary: BoqSummaryResponse | null;
  mutate: (d?: { message: BoqSummaryResponse }, revalidate?: boolean) => unknown }) {
  const sheets = useMemo(() => summary?.sheets ?? [], [summary]);
  const { figs, failed, loading } = useSheetFigures(boqId, sheets);
  const { call: save } = useFrappePostCall<{ message: BoqSummaryResponse }>(SAVE);
  const [open, setOpen] = useState<boolean | null>(null);
  const [showRows, setShowRows] = useState(false);
  const [area, setArea] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);
  const send = async (args: Record<string, string>) => {
    const res = await save({ boq: boqId ?? "", ...args });
    if (res?.message) await mutate({ message: res.message }, false);
  };
  const typeArea = (v: string) => {
    setArea(v);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => { void send({ area_sqft: v.replace(/,/g, "") }).then(() => setArea(null)); }, SUMMARY_SAVE_PAUSE_MS);
  };
  const table = useMemo(() => summaryTable(sheets, figs, summary?.installation.total ?? null), [sheets, figs, summary]);
  if (!summary) return null;
  const isOpen = open ?? sheets.length > 0; // open by default once any sheet is committed
  const inst = summary.installation;
  const r = summary.rates;
  const fl = summary.floor;
  const areaText = area ?? (summary.area_sqft ? String(summary.area_sqft) : "");
  const ticked = table.lines.filter((l) => l.ticked);
  const firstTicked = table.lines.findIndex((l) => l.ticked);
  const ordered = firstTicked < 0 ? table.lines
    : [...table.lines.slice(0, firstTicked).filter((l) => !l.ticked), ...ticked, ...table.lines.slice(firstTicked).filter((l) => !l.ticked)];
  const rows = (l: { rowsWithSupply: number; rowsWithAmount: number }) => `${l.rowsWithSupply} of ${l.rowsWithAmount}`;
  const setTick = (name: string, on: boolean) =>
    void send({ covered_sheets: JSON.stringify(sheets.filter((s) => (s.sheet_name === name ? on : s.ticked)).map((s) => s.sheet_name)) });

  return (
    <section aria-label="BoQ summary" className="rounded-lg border border-border bg-background">
      <div className="flex items-center justify-between px-4 py-2 border-b border-border">
        <h2 className="text-sm font-semibold text-foreground">BoQ summary &middot; our cost and margin</h2>
        <button type="button" className="text-xs px-2 py-1 rounded-md border border-border" onClick={() => setOpen(!isOpen)}>
          {isOpen ? "Fold" : "Open"}
        </button>
      </div>
      {isOpen && (
        <div className="space-y-3 p-4 text-sm">
          <div className="grid gap-3 md:grid-cols-2">
            <div className="rounded-md border border-border p-3 space-y-1.5">
              <p className="font-medium">Electrical installation cost (one figure for the ticked sheets)</p>
              <div className="flex flex-wrap items-center gap-2">
                <label className="inline-flex items-center gap-1">Area
                  <input aria-label="Area in sq ft" className="h-7 w-28 rounded border px-1 text-right" value={areaText}
                    onChange={(e) => typeArea(e.target.value)} /> sq ft</label>
                {summary.carpet_area !== null && (
                  <span className="text-xs text-muted-foreground">Project carpet area: {fig(summary.carpet_area)} sq ft &middot;{" "}
                    <button type="button" className="text-primary hover:underline"
                      onClick={() => void send({ area_sqft: String(summary.carpet_area) })}>use it</button></span>
                )}
              </div>
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <span>Area x Rs {fig(r.install_per_sqft)} (Pricing Input)</span>
                <span className="tabular-nums">{inst.area_part === null ? ENTER_AREA : fig(inst.area_part)}</span>
                <PartControls changed={inst.area_part_changed} onSave={(v) => void send({ area_cost_override: v })} />
              </div>
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <span>Floor cutting at our cost
                  <span className="block text-xs text-muted-foreground">{fig(fl.metres)} m x Rs {fig(r.tray_cutting)} &middot;{" "}
                    {fl.caught.length} rows &middot;{" "}
                    <button type="button" className="text-primary hover:underline" onClick={() => setShowRows(!showRows)}>
                      {showRows ? "hide rows" : "show rows"}</button></span></span>
                <span className="tabular-nums">{fig(inst.floor_part)}</span>
                <PartControls changed={inst.floor_part_changed} onSave={(v) => void send({ floor_cut_override: v })} />
              </div>
              {showRows && (
                <ul className="text-xs text-muted-foreground list-disc pl-5">
                  {fl.caught.map((c) => <li key={`${c.sheet_name}-${c.excel_row}`}>{c.sheet_name.trim()} row {c.excel_row}: {c.text} &middot; {fig(c.qty)} {c.unit}</li>)}
                </ul>
              )}
              <div className="flex justify-between border-t border-border pt-1.5 font-semibold">
                <span>Installation cost</span><span className="tabular-nums">{inst.total === null ? ENTER_AREA : fig(inst.total)}</span>
              </div>
              {fl.mentioned.length > 0 && (
                <p className="text-xs text-muted-foreground">Mentioned, not added: {fl.mentioned.map((m) =>
                  `row ${m.excel_row} (${m.sheet_name.trim()}, ${fig(m.qty)} ${m.unit}) - ${m.reason}`).join("; ")}.</p>
              )}
              <p className="text-xs text-muted-foreground">An edited figure shows &ldquo;changed by user&rdquo; and &ldquo;Back to system
                figure&rdquo;; area, edits and ticks carry to a new version or revision.</p>
            </div>
            <div className="rounded-md border border-border p-3 space-y-1.5">
              <p className="font-medium">Sheets covered by this installation cost</p>
              {sheets.map((s) => (
                <label key={s.sheet_name} className="flex items-center gap-2">
                  <input type="checkbox" checked={s.ticked} onChange={(e) => setTick(s.sheet_name, e.target.checked)} />
                  {s.sheet_name.trim() || s.sheet_name}
                </label>
              ))}
              <p className="text-xs text-muted-foreground">Electrical sheets start ticked; the user corrects them; only committed data
                sheets are listed.</p>
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs border-collapse">
              <thead><tr className="border-b border-border text-muted-foreground">
                {["Sheet", "BoQ amount", "BCS supply", "BCS installation", "Rows with BCS supply", "Margin"].map((h, i) => (
                  <th key={h} className={i === 0 ? "px-2 py-1.5 text-left font-medium" : "px-2 py-1.5 text-right font-medium"}>{h}</th>))}
              </tr></thead>
              <tbody>
                {ordered.map((l) => {
                  const spanFirst = l.ticked && l === ticked[0];
                  return (
                    <tr key={l.sheet} className="border-b border-border">
                      <td className="px-2 py-1.5">{l.ticked ? "[x] " : ""}{l.sheet.trim() || l.sheet}
                        <SheetExceptionLines ex={l.fig?.exceptions} boqId={boqId} sheet={l.sheet} /></td>
                      <td className={td}>{fig(l.fig?.boqAmount)}</td>
                      <td className={td}>{fig(l.fig?.bcsSupply)}</td>
                      {!l.ticked && <td className={td}>{fig(l.install)}</td>}
                      {spanFirst && <td className={td} rowSpan={ticked.length}>{table.needsArea ? ENTER_AREA : fig(table.block?.install)}</td>}
                      <td className={td}>{l.fig ? rows(l.fig) : ""}</td>
                      {!l.ticked && <td className={td}>{pct(l.margin)}</td>}
                      {spanFirst && <td className={td} rowSpan={ticked.length}>{table.needsArea ? ENTER_AREA : pct(table.block?.margin ?? null)}</td>}
                    </tr>
                  );
                })}
                {table.block && (
                  <tr className="border-b border-border font-medium" data-row="ticked-block">
                    <td className="px-2 py-1.5">Ticked block</td><td className={td}>{fig(table.block.boqAmount)}</td>
                    <td className={td}>{fig(table.block.bcsSupply)}</td>
                    <td className={td}>{table.needsArea ? ENTER_AREA : fig(table.block.install)}</td>
                    <td className={td}>{rows(table.block)}</td>
                    <td className={td}>{table.needsArea ? ENTER_AREA : pct(table.block.margin)}</td>
                  </tr>
                )}
                <tr className="font-semibold" data-row="boq-total">
                  <td className="px-2 py-1.5">BoQ total</td><td className={td}>{fig(table.total.boqAmount)}</td>
                  <td className={td}>{fig(table.total.bcsSupply)}</td>
                  <td className={td}>{table.needsArea ? ENTER_AREA : fig(table.total.install)}</td>
                  <td className={td}>{rows(table.total)}</td>
                  <td className={td}>{table.needsArea ? ENTER_AREA : pct(table.total.margin)}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div className="rounded-md border border-amber-300 bg-amber-50 p-3 text-xs text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-100"
            data-box="how-worked-out">
            <p className="font-medium">How these figures are worked out</p>
            <ul className="mt-1 list-disc pl-5 space-y-0.5">
              <li>BoQ amount = the amount shown on each row (qty x the chosen rate; a row priced on one side only counts its one amount).</li>
              <li>The exceptions are listed by row under each sheet&rsquo;s name.</li>
              <li>A sheet outside the installation block uses the installation entered on its rows; the block uses the one installation figure.</li>
              <li>Margin = 1 - (BCS supply + BCS installation) / BoQ amount.</li>
              <li>A blank means no value yet (never 0). The BoQ total&rsquo;s margin stays blank until every listed sheet has a cost. No area
                entered: installation, block margin and total margin read &ldquo;{ENTER_AREA}&rdquo;.</li>
            </ul>
          </div>
          {loading && <p className="text-xs text-muted-foreground">Loading the sheets&rsquo; figures&hellip;</p>}
          {failed.length > 0 && <p className="text-xs text-destructive">Could not load: {failed.map((f) => f.trim()).join(", ")}.</p>}
        </div>
      )}
    </section>
  );
}

/**
 * The one line on a sheet's own Summary (owner, mockup point B): only when this sheet is ticked in its BoQ's summary and the
 * viewer may see cost. The block margin is live ("- enter the area" when none).
 */
export function BoqSummarySheetLine() {
  const { boqId, sheetName } = useParams<{ boqId: string; sheetName: string }>();
  const { allowed, summary } = useBoqSummary(boqId);
  const ticked = useMemo(() => (summary?.sheets ?? []).filter((s) => s.ticked), [summary]);
  const isTicked = !!sheetName && ticked.some((s) => s.sheet_name === sheetName);
  const { figs } = useSheetFigures(boqId, isTicked ? ticked : []);
  if (!allowed || !summary || !isTicked) return null;
  const t = summaryTable(ticked, figs, summary.installation.total);
  const margin = t.needsArea ? ENTER_AREA : pct(t.block?.margin ?? null);
  return (
    <p className="px-3 py-2 border-t border-border bg-sky-50 dark:bg-sky-950/40 text-xs text-sky-900 dark:text-sky-100">
      This sheet&rsquo;s margin counts installation typed on its rows. The BoQ&rsquo;s installation cost (area x Rs{" "}
      {fig(summary.rates.install_per_sqft)} + floor cutting) is in the BoQ summary on the BoQ&rsquo;s main page: margin there{" "}
      {margin} for the ticked sheets.
    </p>
  );
}
