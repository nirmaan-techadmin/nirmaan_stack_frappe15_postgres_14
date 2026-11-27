/**
 * CAT-3 (owner 2026-11-26 00:18, R5: item notes are Admin-only; 01:14 the mockup). The Notes cell and the Labels cell of one Rate Master
 * row. Everyone reads the note; only an Admin sees the pencil, whose editor saves through the page's `onSaveNote` (the server gates it
 * again, first). The Labels cell shows grey chips in the row's OWN words and, for a row the rule could not label, the amber chip
 * (ANSWER 2: never an internal label value).
 */
import { useState } from "react";
import { Pencil } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { FLAG_TOOLTIP, flagChips, labelChips, type LabelFlag } from "./catalogueLabelChips";

export const NOTE_COPY = {
  title: (label: string) => `Note on ${label}`,
  hint: "A fact about this row, shown here and where the row prices. Only an Admin can edit it.",
  save: "Save note",
  cancel: "Cancel",
};

export function ItemNoteCell({ note, label, canEdit, disabled, onSave }: {
  note: string | null | undefined;
  label: string;
  canEdit: boolean;
  disabled?: boolean;
  onSave?: (text: string) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const text = note ?? "";
  return (
    <div className="flex items-start gap-1">
      <span className="whitespace-pre-line text-xs" data-testid="item-note">{text || "-"}</span>
      {canEdit && onSave ? (
        <Button size="icon" variant="ghost" className="h-6 w-6 shrink-0" aria-label="Edit note" disabled={disabled}
          onClick={() => { setDraft(text); setErr(null); setOpen(true); }}>
          <Pencil className="h-3.5 w-3.5" />
        </Button>
      ) : null}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>{NOTE_COPY.title(label)}</DialogTitle></DialogHeader>
          <p className="text-xs text-muted-foreground">{NOTE_COPY.hint}</p>
          <Textarea value={draft} onChange={(e) => setDraft(e.target.value)} rows={4} data-testid="item-note-editor" />
          {err ? <p className="text-xs text-destructive" role="alert">{err}</p> : null}
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>{NOTE_COPY.cancel}</Button>
            <Button disabled={busy} onClick={async () => {
              if (!onSave) return;
              setBusy(true); setErr(null);
              try { await onSave(draft); setOpen(false); } catch (e) { setErr((e as { message?: string })?.message ?? "Save failed"); } finally { setBusy(false); }
            }}>{NOTE_COPY.save}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export function ItemLabelsCell({ item }: {
  item: { labels?: Record<string, string> | null; label_flags?: LabelFlag[] | null; attributes?: Record<string, unknown> | null };
}) {
  const chips = labelChips(item);
  const flags = flagChips(item);
  if (!chips.length && !flags.length) return <span className="text-xs text-muted-foreground">-</span>;
  return (
    <div className="flex flex-wrap gap-1" data-testid="item-labels">
      {chips.map((c) => <Badge key={c.key} variant="secondary" className="font-normal" data-testid="label-chip">{c.text}</Badge>)}
      {flags.map((f) => (
        <Badge key={`flag-${f.key}`} variant="outline" title={FLAG_TOOLTIP} data-testid="label-flag-chip"
          className="border-amber-500/60 bg-amber-50 font-normal text-amber-900 dark:bg-amber-950/30 dark:text-amber-200">{f.text}</Badge>
      ))}
    </div>
  );
}
