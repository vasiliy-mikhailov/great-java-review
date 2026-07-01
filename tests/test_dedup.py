"""M2 + M3 — registry dedup must propagate confidence and must not false-merge distinct bugs.

M2: a confident re-sighting of an already-tracked suspicion bumps _STORE[id]["confidence"], but
    _store_to_suspicions only copies an entry into the scheduler's by_id when it's NOT already
    there — so the bump never reaches scheduling or the registry JSON; the priority stays stale.
M3: _dedup_against_store parses a free-text LLM reply by grabbing the first \\d+ run, so a reply
    like "this is distinct, relates to line 7" merges the new (distinct) suspicion into #7 and the
    real bug is dropped. Only a clean integer id (or NEW) should drive a merge.
"""
from _fakes import PipelineTC
from current_version import suspicion as S


class TestConfidencePropagation(PipelineTC):
    def test_resighting_bump_reaches_scheduler(self):
        # first sighting at low confidence (no dup)
        self.patch_attr(S, "_dedup_against_store", lambda *a, **k: None)
        S._register_suspicion("obs", "bug A", "File.java:10", 0.3)
        by_id = {}
        S._store_to_suspicions(by_id)
        self.assertEqual(by_id[0].confidence, 0.3)

        # more confident re-sighting, deduped onto the same entry
        self.patch_attr(S, "_dedup_against_store", lambda *a, **k: 0)
        S._register_suspicion("obs2", "bug A again", "File.java:10", 0.9)
        self.assertEqual(S._STORE[0]["confidence"], 0.9)  # store bumped (existing behaviour)

        S._store_to_suspicions(by_id)  # must re-sync the already-tracked entry
        self.assertEqual(by_id[0].confidence, 0.9,
                         "the confidence bump never reached the scheduler's suspicion (M2)")


class TestDedupIdParse(PipelineTC):
    def _seed(self, n):
        for i in range(n):
            S._store_add("obs", f"bug {i}", f"File.java:{i}", 0.5)

    def test_prose_mentioning_a_number_is_not_a_merge(self):
        self._seed(8)  # ids 0..7 exist, so a stray "7" would resolve to a real entry
        self.patch_attr(S, "_llm_call", lambda *a, **k: "This looks distinct, though it relates to line 7.")
        res = S._dedup_against_store("new obs", "genuinely new bug", "File.java:99")
        self.assertIsNone(res, "a distinct suspicion was false-merged on a stray number (M3)")

    def test_clean_integer_reply_still_merges(self):
        self._seed(8)
        self.patch_attr(S, "_llm_call", lambda *a, **k: "3")
        self.assertEqual(S._dedup_against_store("o", "b", "l"), 3)

    def test_loose_but_unambiguous_merge_replies_still_merge(self):
        """A real (slightly non-compliant) LLM says 'id 3' / 'same as #3' / 'duplicate of 3' / '3.' — these
        must merge, or each becomes a duplicate _STORE row reproduced independently (budget waste)."""
        self._seed(8)
        for reply in ("id 3", "same as #3", "duplicate of 3", "3.", "it is #3"):
            self.patch_attr(S, "_llm_call", lambda *a, _r=reply, **k: _r)
            self.assertEqual(S._dedup_against_store("o", "b", "l"), 3, f"reply {reply!r} did not merge")

    def test_distinct_with_number_does_not_merge(self):
        self._seed(8)
        for reply in ("distinct, but near id 3", "this is different from 3", "none — it's its own bug 3"):
            self.patch_attr(S, "_llm_call", lambda *a, _r=reply, **k: _r)
            self.assertIsNone(S._dedup_against_store("o", "b", "l"), f"reply {reply!r} wrongly merged")

    def test_hash_integer_reply_still_merges(self):
        self._seed(8)
        self.patch_attr(S, "_llm_call", lambda *a, **k: "#5")
        self.assertEqual(S._dedup_against_store("o", "b", "l"), 5)

    def test_new_reply_is_not_a_merge(self):
        self._seed(8)
        self.patch_attr(S, "_llm_call", lambda *a, **k: "NEW")
        self.assertIsNone(S._dedup_against_store("o", "b", "l"))
