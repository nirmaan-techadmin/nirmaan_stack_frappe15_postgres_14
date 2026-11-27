"""SRS-1 T3 (the split, SRS-D0 D2) - one AI Suggest call cut into one piece per row, exactly as sent and answered.

  + the question is the request before its ROWS block, exactly; each row's input is its own payload element as the
    request serialised it (byte-equal to its slice of the ROWS block), non-ASCII text kept as written;
  + each row's reply is its own element's characters from the reply text (byte-equal to that span);
  + a single-row bare-object reply splits too;
  - a row the reply omitted keeps its input and says "no reply element";
  - an element with no usable id, an id not in the batch, text outside the array, a duplicate id's earlier element and an
    unparseable reply are kept at BATCH level, never on a row;
  + a re-ask's reply replaces the first, and the first goes to earlier_replies;
  + a failed attempt or a ceiling cut carries the rows' inputs and no reply.

Pure: no database. Run: bench --site localhost run-tests --module nirmaan_stack.services.boq_suggest_store.test_split
"""

import json
import unittest

from nirmaan_stack.services.boq_suggest_store import split

ITEMS = [
    {"id": 2, "description": "Supply of 25 mm dia PVC conduit", "notes": {"own": "Ø 25"}, "ancestor_chain": [{"description": "Sheet A "}]},
    {"id": 3, "description": "4 sq.mm FRLS Cu wire", "notes": {}, "ancestor_chain": []},
]
QUESTION = "You read rows.\nATTRIBUTES:\n[{\"id\": \"a\"}]"


def _content(items=ITEMS, question=QUESTION):
    return question + split.rows_block(items)


def _obs(text, items=ITEMS, kind="batch", **kw):
    return dict({"kind": kind, "payload_items": items, "content": _content(items), "text": text, "attempt": 1,
                 "usage": {"input_tokens": 10, "output_tokens": 5}, "mapping": {"2": {"a": {"raw": 1}}}, "drops": {}}, **kw)


class TestSplit(unittest.TestCase):
    def test_question_is_the_request_before_its_rows_block(self):
        q, exact = split.question_of(_content(), ITEMS)
        self.assertEqual((q, exact), (QUESTION, True))
        q2, exact2 = split.question_of("no rows block here", ITEMS)
        self.assertEqual((q2, exact2), ("no rows block here", False))

    def test_each_row_input_is_its_own_slice_of_the_rows_block_non_ascii_kept(self):
        reply = '[{"id": 2, "attributes": {}}, {"id": 3, "attributes": {}}]'
        out = split.split_call(_obs(reply))
        block = json.dumps(ITEMS, ensure_ascii=False)
        for item in ITEMS:
            piece = out["rows"][item["id"]]["ai_input"]
            self.assertEqual(piece, json.dumps(item, ensure_ascii=False))
            self.assertIn(piece, block)          # the exact characters the request sent
        self.assertIn("Ø 25", out["rows"][2]["ai_input"])
        self.assertEqual(out["question"], QUESTION)

    def test_each_row_reply_is_its_own_element_span(self):
        el2 = '{"id": 2, "attributes": {"a": {"value": 25, "confidence": 0.9}}}'
        el3 = '{\n  "id": 3,\n  "attributes": {"a": {"value": "x [y]", "confidence": 0.5}}\n}'
        reply = "[\n  " + el2 + ",\n  " + el3 + "\n]"
        out = split.split_call(_obs(reply))
        self.assertEqual(out["rows"][2]["raw_reply"], el2)
        self.assertEqual(out["rows"][3]["raw_reply"], el3)
        self.assertEqual({r["reply_status"] for r in out["rows"].values()}, {split.REPLY_OK})
        self.assertNotIn("outside_array", out["batch"])
        self.assertEqual(out["rows"][2]["coercion_trail"], {"a": {"raw": 1}})

    def test_a_single_row_bare_object_reply(self):
        el = '{"id": 2, "attributes": {"a": {"value": 1, "confidence": 1}}}'
        out = split.split_call(_obs(el, items=ITEMS[:1]))
        self.assertEqual(out["rows"][2]["raw_reply"], el)

    def test_an_omitted_row_keeps_its_input_and_says_no_reply_element(self):
        out = split.split_call(_obs('[{"id": 2, "attributes": {}}]'))
        self.assertEqual(out["rows"][3]["reply_status"], split.REPLY_NONE)
        self.assertIsNone(out["rows"][3]["raw_reply"])
        self.assertEqual(out["rows"][3]["ai_input"], json.dumps(ITEMS[1], ensure_ascii=False))
        self.assertEqual(out["batch"]["rows_omitted"], [3])

    def test_what_cannot_be_split_stays_at_batch_level(self):
        reply = ('Here you go:\n[{"id": 2, "attributes": {"a": 1}}, {"attributes": {"a": 9}}, {"id": 99, "attributes": {}},'
                 ' {"id": 3, "attributes": {"a": 2}}, {"id": 3, "attributes": {"a": 3}}]\nThanks.')
        out = split.split_call(_obs(reply))
        b = out["batch"]
        self.assertEqual(b["items_no_id"], ['{"attributes": {"a": 9}}'])
        self.assertEqual(b["ids_not_in_batch"], ['{"id": 99, "attributes": {}}'])
        self.assertEqual(b["earlier_duplicates"], ['{"id": 3, "attributes": {"a": 2}}'])   # the run keeps the LAST
        self.assertEqual(out["rows"][3]["raw_reply"], '{"id": 3, "attributes": {"a": 3}}')
        self.assertIn("Here you go:", b["outside_array"])
        self.assertIn("Thanks.", b["outside_array"])
        for r in out["rows"].values():
            self.assertNotIn("99", r["raw_reply"])

    def test_an_unparseable_reply_is_kept_whole_at_batch_level(self):
        out = split.split_call(_obs('[{"id": 2, "attributes": {'))     # truncated: the product's parser raises
        self.assertIn("unparseable", out["batch"])
        self.assertEqual(out["batch"]["reply_text"], '[{"id": 2, "attributes": {')
        self.assertEqual({r["reply_status"] for r in out["rows"].values()}, {split.REPLY_UNPARSEABLE})

    def test_a_reask_reply_replaces_the_first_and_the_first_goes_to_earlier_replies(self):
        first = split.split_call(_obs('[{"id": 2, "items": []}, {"id": 3, "items": [{"a": 1}]}]'))
        again = split.split_call(_obs('[{"id": 2, "items": [{"a": 7}]}]', items=ITEMS[:1], reask=True))
        again["batch"]["reask"] = True
        final = split.merge_calls([first, again])
        self.assertEqual(final[2]["raw_reply"], '{"id": 2, "items": [{"a": 7}]}')
        self.assertEqual(final[2]["earlier_replies"], [{"reply": '{"id": 2, "items": []}', "replaced_by": "re-ask"}])
        self.assertTrue(final[2]["reasked"])
        self.assertEqual(final[3]["raw_reply"], '{"id": 3, "items": [{"a": 1}]}')
        self.assertEqual(final[3]["earlier_replies"], [])

    def test_a_failed_attempt_or_ceiling_cut_carries_inputs_and_no_reply(self):
        for kind in ("attempt_failed", "ceiling_cut"):
            out = split.split_call(_obs(None, kind=kind, error="RuntimeError('x')"))
            self.assertEqual(out["batch"]["kind"], kind)
            self.assertEqual({r["reply_status"] for r in out["rows"].values()}, {split.REPLY_NONE}, kind)
        final = split.merge_calls([split.split_call(_obs(None, kind="attempt_failed")),
                                   split.split_call(_obs('[{"id": 2, "attributes": {}}, {"id": 3, "attributes": {}}]'))])
        self.assertEqual(final[2]["raw_reply"], '{"id": 2, "attributes": {}}')
        self.assertEqual(final[2]["earlier_replies"], [])

    def test_fingerprint_is_the_sha256_of_the_utf8_text(self):
        self.assertEqual(split.fingerprint("abc"), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
