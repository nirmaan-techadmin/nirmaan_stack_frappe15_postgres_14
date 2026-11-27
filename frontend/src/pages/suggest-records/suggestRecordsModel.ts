/**
 * SRS-2 -- the "AI Suggest Records" page's pure model (F4): the server methods, the reply shapes read at ONE typed
 * accessor each (F2), the filters, and the display rules.
 *
 * THE RATES RULE (owner R8, QR-C3 27 Nov 15:03): `rates_status` is the ONLY truth for "priced". The server sends a
 * figure only for a priced row and a kind the pricer priced (`services/boq_suggest_store/records.shown_rates`); every
 * other figure arrives as null and is shown as "-", never as 0. THE BCS SUPPLY (BCS-FX, owner R-BCS-182): the suggested BCS
 * supply worked out at the run (`records.shown_bcs`) -- the server sends a figure, or the text "-" (none) or "not recorded (run
 * before BCS)" (a record made before the BCS merge); `bcsSupplyText` shows it.
 */
import { format } from "date-fns";

import { formatToRoundedIndianRupee } from "@/utils/FormatPrice";

export const SUGGEST_RECORDS_ROUTE = "/suggest-records";
const API = "nirmaan_stack.api.boq.suggest_records";
export const LIST_METHOD = `${API}.list_records`;
export const OPTIONS_METHOD = `${API}.filter_options`;
export const RECORD_METHOD = `${API}.get_record`;
export const EXPORT_METHOD = `${API}.export_records`;

export const PAGE_SIZE = 50;
export const DEFAULT_DAYS = 30;
/** BCS-FX (owner R-BCS-182): a record made before the BCS merge -- never recomputed by the readers (SRS-2's Admin reprice, no
 *  button, re-prices the whole record, BCS included). */
export const BCS_NOT_RECORDED = "not recorded (run before BCS)";
export const CAPS_LINE =
  "Summary: up to 50,000 rows. Full: up to 5,000 rows; narrow the filters for more. The questions go on a second sheet.";
export const EMPTY_TEXT = "No records yet.";
export const NO_FIGURE = "-";

/** The filters the page sends (blank = not filtered). */
export interface SuggestFilters {
  date_from: string;
  date_to: string;
  project: string;
  boq: string;
  sheet_name: string;
  discipline: string;
  category_id: string;
  rates_status: string;
  run_by: string;
  search: string;
}

/** One list row, as `records.list_row` sends it. */
export interface SuggestListRow {
  name: string;
  run_date: string | null;
  project_name: string | null;
  boq: string;
  sheet_name: string;
  excel_row: number;
  description: string | null;
  category_id: string | null;
  first_values: string;
  supply_rate: number | null;
  install_rate: number | null;
  combined_rate: number | null;
  /** BCS-FX: the suggested BCS supply at the run -- a figure, "-" or "not recorded (run before BCS)" (`bcsSupplyText`). */
  bcs_supply_rate: number | string | null;
  rates_status: string | null;
}

export interface SuggestListReply {
  rows: SuggestListRow[];
  total: number;
  page: number;
  page_size: number;
}

export interface FilterOptions {
  projects: { value: string; label: string }[];
  boqs: string[];
  sheets: string[];
  disciplines: string[];
  categories: string[];
  run_by: string[];
  rates_statuses: string[];
}

/** One record's detail, as `records.get_record` sends it. */
export interface SuggestRecordDetail {
  name: string;
  project_name: string | null;
  boq: string;
  committed_version: number | null;
  sheet_name: string;
  excel_row: number;
  boq_node: string | null;
  description: string | null;
  discipline: string | null;
  category_id: string | null;
  run_date: string | null;
  run_id: string | null;
  batch_rows: number | null;
  batch: { calls?: { usage?: { input_tokens?: number; output_tokens?: number } | null }[] } | null;
  catalogue_stamp: string | null;
  ai_input: string | null;
  raw_reply: string | null;
  final_attributes: { attribute: string; value: string; confidence: number | null }[];
  rates: {
    supply_rate: number | null;
    install_rate: number | null;
    combined_rate: number | null;
    /** BCS-FX: the suggested BCS supply at the run -- a figure, "-" or "not recorded (run before BCS)" (`bcsSupplyText`). */
    bcs_supply_rate: number | string | null;
    rates_status: string | null;
    pricing_stamp: string | null;
  };
  question: { name: string; text: string; bytes: number | null; category_id: string | null } | null;
  run: { pass_kind?: string | null; run_by?: string | null; model?: string | null; suggestion_run?: string | null } | null;
}

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null;

/** The SDK's `{message}` envelope, opened at one place (F2). */
export function messageOf<T>(data: unknown): T | null {
  return isObj(data) && isObj(data.message) ? (data.message as unknown as T) : null;
}

/** "yyyy-MM-dd" of a Date (the run-date filter's own format). */
export const isoDay = (d: Date): string => format(d, "yyyy-MM-dd");

/** The default filters: run dates over the last 30 days, nothing else. */
export function defaultFilters(today: Date = new Date()): SuggestFilters {
  const from = new Date(today.getTime());
  from.setDate(from.getDate() - DEFAULT_DAYS);
  return { date_from: isoDay(from), date_to: isoDay(today), project: "", boq: "", sheet_name: "", discipline: "",
    category_id: "", rates_status: "", run_by: "", search: "" };
}

/** The filters as the server takes them (blank values dropped). */
export function filtersPayload(f: SuggestFilters): string {
  return JSON.stringify(Object.fromEntries(Object.entries(f).filter(([, v]) => v.trim() !== "")));
}

/** A rate as shown: a figure only when the server sent one; "-" otherwise -- never a 0 for "not priced". */
export function rateText(v: number | null | undefined): string {
  return typeof v === "number" ? formatToRoundedIndianRupee(v) : NO_FIGURE;
}

/** BCS-FX (owner R-BCS-182): the BCS supply as shown -- a figure in the rates' own style, the server's text as sent, "-" for none. */
export function bcsSupplyText(v: number | string | null | undefined): string {
  if (typeof v === "number") return rateText(v);
  return typeof v === "string" && v.trim() !== "" ? v : NO_FIGURE;
}

export type StatusTone = "priced" | "not_priced" | "not_computed" | "pending";

/** The chip's colour: green "priced", amber "not priced: ...", red "rates not computed: ...", grey "pending". */
export function statusTone(status: string | null | undefined): StatusTone {
  const s = status ?? "";
  if (s === "priced") return "priced";
  if (s.startsWith("not priced")) return "not_priced";
  if (s.startsWith("rates not computed")) return "not_computed";
  return "pending";
}

export const TONE_CLASS: Record<StatusTone, string> = {
  priced: "bg-green-100 text-green-800 border-green-300",
  not_priced: "bg-amber-100 text-amber-800 border-amber-300",
  not_computed: "bg-red-100 text-red-800 border-red-300",
  pending: "bg-gray-100 text-gray-700 border-gray-300",
};

/** A run date as shown: dd-MMM-yyyy HH:mm (the app's date format, with the time the run read the row). */
export function runDateText(v: string | null | undefined): string {
  if (!v) return NO_FIGURE;
  const d = new Date(v.replace(" ", "T"));
  return Number.isNaN(d.getTime()) ? v : format(d, "dd-MMM-yyyy HH:mm");
}

/**
 * The batch's token line. The store keeps each AI call's usage under `usage` (services/boq_suggest_store/split.py), so the
 * counts are read from there; a batch with no recorded usage says so - never "0" for a count that was not recorded.
 */
export function batchTokensText(batch: SuggestRecordDetail["batch"]): string {
  const calls = (batch?.calls ?? []).filter((c) => typeof c.usage?.input_tokens === "number" || typeof c.usage?.output_tokens === "number");
  if (calls.length === 0) return "tokens not recorded";
  const inp = calls.reduce((n, c) => n + (c.usage?.input_tokens ?? 0), 0);
  const out = calls.reduce((n, c) => n + (c.usage?.output_tokens ?? 0), 0);
  return `tokens in ${inp} / out ${out}`;
}

/** "Showing 51 - 100 of 153 records." */
export function pagerText(page: number, total: number, size: number = PAGE_SIZE): string {
  if (total <= 0) return "";
  const first = (page - 1) * size + 1;
  return `Showing ${first} - ${Math.min(page * size, total)} of ${total} records. ${size} per page.`;
}

export const lastPage = (total: number, size: number = PAGE_SIZE): number => Math.max(1, Math.ceil(total / size));
