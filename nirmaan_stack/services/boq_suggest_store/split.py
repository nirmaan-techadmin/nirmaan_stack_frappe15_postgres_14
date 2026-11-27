"""SRS-1 (SRS-D0 D2): split ONE AI Suggest call into one piece per row, exactly as it was sent and answered.

A Suggest call (`extraction._extract_batch`) sends up to 20 rows of one category in ONE request and gets ONE reply
holding a JSON array, one element per row (each element's `id` = the row's Excel row). This module cuts that call
into per-row pieces for the Suggest run store, and keeps whatever cannot be cut at batch level.

The rule (owner-accepted, SRS-D0 review 2026-11-27):
  * the QUESTION is the request text before its `ROWS:` block (the block is an exact suffix: 668 / 668 measured);
  * a row's INPUT is its own payload element, serialised exactly as the request serialised it into `ROWS:`
    (`json.dumps(item, ensure_ascii=False)` - the same call `batch_prompt_content` makes for the whole list);
  * a row's REPLY is the reply-array element whose id is that row - its own characters from the reply (its span
    inside the array). The array is read by THE PRODUCT'S parser (`ai_voter._extract_json_array`) and ids by the
    product's rule (`extraction._reply_row_id`), imported, never copied, so the store can never read a reply
    differently from the run;
  * a duplicate id keeps the LAST element, as the run does (`out[rid] = row_out`); the earlier ones go to batch level;
  * what cannot be split (text outside the array, an element with no usable id, an id not in the batch, an
    unparseable reply) is kept once, at batch level; a row the reply omitted gets `REPLY_NONE` and keeps its input.

Pure: no database, no frappe call (frappe is only imported by the two product modules it reads helpers from).
"""

import hashlib
import json

from nirmaan_stack.services.boq_category.ai_voter import _balanced_span, _extract_json_array
from nirmaan_stack.services.boq_rate_master.extraction import _reply_row_id

ROWS_MARKER = "\n\nROWS:\n"
REPLY_OK = "ok"
REPLY_NONE = "no reply element"
REPLY_UNPARSEABLE = "reply not parseable"


def rows_block(payload_items):
    """The `ROWS:` block exactly as `extraction.batch_prompt_content` appends it to the request."""
    return ROWS_MARKER + json.dumps(payload_items, ensure_ascii=False)


def question_of(content, payload_items):
    """(question_text, exact) - the request text before its ROWS block. `exact` is False only when the block is not
    the request's suffix (never measured); the whole request is then the question, so nothing is lost."""
    block = rows_block(payload_items)
    if content.endswith(block):
        return content[: len(content) - len(block)], True
    return content, False


def fingerprint(text):
    """The Question's name: sha256 of the FILLED question text (UTF-8)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def row_input(item):
    """One row's AI input, as the request serialised it."""
    return json.dumps(item, ensure_ascii=False)


def _element_spans(text, start, end):
    """The character spans of the top-level elements of the JSON array text[start:end] (start = its '[').
    String-aware, like the product's `_balanced_span`."""
    spans = []
    depth = 0
    in_str = False
    escaped = False
    el_start = None
    for i in range(start, end):
        ch = text[i]
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            if depth == 1 and el_start is None:
                el_start = i
            continue
        if ch in "[{":
            depth += 1
            if depth == 2 and el_start is None:
                el_start = i
            continue
        if ch in "]}":
            depth -= 1
            if depth == 0:
                if el_start is not None:
                    spans.append((el_start, _rstrip_index(text, el_start, i)))
                return spans
            continue
        if depth == 1:
            if ch == ",":
                if el_start is not None:
                    spans.append((el_start, _rstrip_index(text, el_start, i)))
                el_start = None
            elif not ch.isspace() and el_start is None:
                el_start = i
    return spans


def _rstrip_index(text, start, stop):
    while stop > start and text[stop - 1].isspace():
        stop -= 1
    return stop


def _array_span(text, parsed):
    """(start, end) of the array span the product's parser returned, found by the parser's own scan (first balanced
    '[' span that parses to a list of dicts), or None when the reply was a bare object (the single-row path)."""
    i = text.find("[")
    while i != -1:
        end = _balanced_span(text, i, "[", "]")
        if end is None:
            return None
        try:
            got = json.loads(text[i:end])
        except ValueError:
            i = text.find("[", i + 1)
            continue
        if isinstance(got, list) and all(isinstance(el, dict) for el in got) and got == parsed:
            return i, end
        i = text.find("[", i + 1)
    return None


def reply_elements(text):
    """Parse a raw reply the product's way. Returns (elements, leftovers) where elements = [(element, its own
    characters)] in reply order and leftovers = {"outside_array": str?, "element_text_reserialised": n?,
    "unparseable": str?}. Never raises."""
    leftovers = {}
    if text is None:
        return [], {"unparseable": "no reply text"}
    try:
        parsed = _extract_json_array(text)
    except Exception as exc:  # noqa: BLE001 -- the run's own parser failed the same way; kept at batch level
        return [], {"unparseable": "%s: %s" % (type(exc).__name__, str(exc)[:200])}
    if isinstance(parsed, dict):
        parsed = [parsed]
    span = _array_span(text, parsed)
    pieces = []
    if span is not None:
        start, end = span
        outside = (text[:start] + text[end:]).strip()
        if outside:
            leftovers["outside_array"] = text[:start] + "…" + text[end:]
        spans = _element_spans(text, start, end)
        if len(spans) == len(parsed):
            for el, (a, b) in zip(parsed, spans):
                piece = text[a:b]
                try:
                    same = json.loads(piece) == el
                except ValueError:
                    same = False
                pieces.append(piece if same else None)
        else:
            pieces = [None] * len(parsed)
    else:
        # the single-row bare-object reply: the object's own balanced span
        j = text.find("{")
        end = _balanced_span(text, j, "{", "}") if j != -1 else None
        if end is not None and len(parsed) == 1:
            pieces = [text[j:end]]
            outside = (text[:j] + text[end:]).strip()
            if outside:
                leftovers["outside_array"] = text[:j] + "…" + text[end:]
        else:
            pieces = [None] * len(parsed)
    out = []
    reserialised = 0
    for el, piece in zip(parsed, pieces):
        if piece is None:
            reserialised += 1
            piece = json.dumps(el, ensure_ascii=False)
        out.append((el, piece))
    if reserialised:
        leftovers["element_text_reserialised"] = reserialised
    return out, leftovers


def split_call(obs):
    """Split one observed call (the dict `_extract_batch` adds to its capture context) into
    {"question": text, "question_exact": bool, "rows": {excel_row: {...}}, "batch": {...batch-level leftovers...}}.

    `obs` keys: payload_items, content, text, usage, attempt, model, mapping, drops, reask, kind ("batch" /
    "attempt_failed" / "ceiling_cut"). Only a "batch" observation carries per-row replies."""
    items = obs.get("payload_items") or []
    question, exact = question_of(obs.get("content") or "", items)
    ids = []
    rows = {}
    for item in items:
        rid = _reply_row_id(item)
        if rid is None:
            continue
        ids.append(rid)
        rows[rid] = {"ai_input": row_input(item), "raw_reply": None, "reply_status": REPLY_NONE,
                     "coercion_trail": (obs.get("mapping") or {}).get(str(rid))}
    batch = {
        "kind": obs.get("kind"),
        "rows": ids,
        "question_exact": exact,
        "attempt": obs.get("attempt"),
        "reask": bool(obs.get("reask")),
        "usage": obs.get("usage"),
        "stop_reason": obs.get("stop_reason"),
    }
    if obs.get("error"):
        batch["error"] = obs["error"]
    if obs.get("kind") != "batch":
        return {"question": question, "question_exact": exact, "rows": rows, "batch": batch}
    elements, leftovers = reply_elements(obs.get("text"))
    batch.update(leftovers)
    if "unparseable" in leftovers:
        for r in rows.values():
            r["reply_status"] = REPLY_UNPARSEABLE
        batch["reply_text"] = obs.get("text")
    no_id, not_in_batch, earlier_duplicates = [], [], []
    for el, piece in elements:
        rid = _reply_row_id(el)
        if rid is None:
            no_id.append(piece)
            continue
        if rid not in rows:
            not_in_batch.append(piece)
            continue
        if rows[rid]["raw_reply"] is not None:
            earlier_duplicates.append(rows[rid]["raw_reply"])   # the run keeps the LAST element; so does the store
        rows[rid]["raw_reply"] = piece
        rows[rid]["reply_status"] = REPLY_OK
    if no_id:
        batch["items_no_id"] = no_id
    if not_in_batch:
        batch["ids_not_in_batch"] = not_in_batch
    if earlier_duplicates:
        batch["earlier_duplicates"] = earlier_duplicates
    omitted = sorted(rid for rid, r in rows.items() if r["reply_status"] == REPLY_NONE)
    if omitted:
        batch["rows_omitted"] = omitted
    so = ((obs.get("drops") or {}).get("second_opinion_verdicts")) or {}
    for rid, r in rows.items():
        if str(rid) in so:
            r["second_opinion"] = so[str(rid)]
    return {"question": question, "question_exact": exact, "rows": rows, "batch": batch}


def merge_calls(splits):
    """Fold the calls made for ONE sub-batch (a ceiling cut, the main call, a re-ask) into the final piece per row:
    the LAST call that answered a row is its reply (a re-ask's reply wins, as the run's `ai_out[rid] = v`), and every
    earlier answer goes to `earlier_replies`. Returns {excel_row: piece} for every row any call carried."""
    final = {}
    for sp in splits:
        reask = bool(sp["batch"].get("reask"))
        for rid, piece in sp["rows"].items():
            prev = final.get(rid)
            if prev is None:
                final[rid] = dict(piece, earlier_replies=[], question=sp["question"])
                continue
            if piece["reply_status"] == REPLY_OK:
                if prev.get("raw_reply") is not None:
                    prev["earlier_replies"].append({"reply": prev["raw_reply"],
                                                    "replaced_by": "re-ask" if reask else "later call"})
                prev.update(raw_reply=piece["raw_reply"], reply_status=REPLY_OK, ai_input=piece["ai_input"],
                            coercion_trail=piece.get("coercion_trail"), question=sp["question"])
                if reask:
                    prev["reasked"] = True
    return final
