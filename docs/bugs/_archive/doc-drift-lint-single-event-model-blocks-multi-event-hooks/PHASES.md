# Implementation Phases — doc-drift-lint `check_hooks` single-event model blocks multi-event hooks

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — claude-config has no Tauri/MCP app surface; `doc-drift-lint.py` is
a pure-read, stdlib-only script verified via its own pytest suite (`user/scripts/test_doc_drift_lint.py`),
the "build-tooling / repo-config, no app integration" untestable class.

## Validated Assumptions

- **`_fmt_events` already emits the multi-clause shape.** `_fmt_events(events)` formats a
  `{event: matcher_set}` map as `"; "`-separated `Event (Matcher)` clauses, sorted by event name.
  The fix's documented-side parser (`_TRIGGER_RE.findall`) consumes exactly that shape, so the
  registered-side formatter and the doc-side parser are mirror images by construction — no new
  cell grammar was invented.
- **The single-event path must stay byte-identical.** The SPEC's fix-scope constraint (branch on
  clause count) means every existing single-clause Hooks-table row is parsed by the pre-existing
  `_TRIGGER_RE.search` + `set(reg_events) != {doc_event}` code path, untouched.

## Cross-feature Integration Notes

No `**Depends on:**` block in the SPEC. **Coordination note (not a hard dep):** this wave, a
sibling bug (`legacy-tool-input-env-hooks-dead`) is concurrently editing the root `CLAUDE.md`
Hooks table (retiring `block-work-repo-git-writes.sh`'s row and updating the two revived hooks'
rows). This bug's scope is the **script** (`doc-drift-lint.py` + its tests) plus the ONE
`lazy-route-inject.sh` row + divergence-marker retirement the SPEC's conclusion names — it does
not touch the contested rows.

---

### Phase 1: Multi-event `check_hooks` parsing + TDD fixtures

**Scope:** Extend `check_hooks` to parse ALL `Event (Matcher)` clauses in a Trigger cell (not
just the first) and compare the full documented `event -> matcher` map against
`registered[name]`, per the SPEC's "Proposed fix scope." Retire the `doc-drift:deliberate-divergence`
marker on the `lazy-route-inject.sh` row and document all three of its real registered events.

**TDD:** yes — new multi-event fixtures pin the clean case, each drift class (documented-not-registered
event, registered-not-documented event, per-event matcher mismatch), before the row's marker is
retired (so the fix is exercised red→green against the real multi-event hook, not just synthetic
fixtures).

**Status:** Complete

**Deliverables:**
- [x] `_TRIGGER_RE.findall` replaces the single-clause `.search` at the Trigger-cell parse site;
  clause count branches the multi-event path from the untouched single-event path.
- [x] Multi-event path: parse the full documented `event -> matcher-set` map (`_parse_matcher_list`
  per clause), compare `set(doc_events)` against `set(registered[name])` (a documented-not-registered
  or registered-not-documented event is a set-inequality finding naming both sides via `_fmt_events`).
- [x] Per-event matcher comparison for a fully-aligned event set: an empty registered matcher set
  (matches-all) skips comparison (the existing `*`-semantics), a non-empty mismatch is its own
  finding naming the event.
- [x] `NOT registered` path and the single-event path are unchanged (verified byte-identical by
  the pre-existing single-event test suite staying green).
- [x] Test fixtures in `user/scripts/test_doc_drift_lint.py` mirroring the real
  `lazy-route-inject.sh` shape (`route.sh`, three events): all-documented-clean,
  documented-event-not-registered, registered-event-not-documented, per-event matcher mismatch.
- [x] Root `CLAUDE.md` `lazy-route-inject.sh` Hooks-table row updated to document all three events
  (`PostCompact (*); SessionStart (compact); UserPromptSubmit (*)`) and the
  `doc-drift:deliberate-divergence` marker retired from that row.

**Implementation Notes (2026-07-12):** Landed in commit `1b23a9ba` ("harden(script): validate
multi-event hooks in doc-drift-lint check_hooks") — the fix and its four new fixtures
(`test_hooks_multi_event_all_documented_clean`, `test_hooks_multi_event_documented_event_not_registered`,
`test_hooks_multi_event_registered_event_not_documented`, `test_hooks_multi_event_matcher_mismatch`)
were authored and committed together with the `CLAUDE.md` row update, ahead of this bug's own
`PHASES.md` (the harden-harness auto-invoke path fixes the instance immediately; this phase
document + the `FIXED.md` receipt below formalize the paper trail against that already-landed
commit). Verified on re-inspection this cycle: `user/scripts/doc-drift-lint.py:259-298` carries
the `len(clauses) > 1` branch exactly as scoped; `user/scripts/test_doc_drift_lint.py:406-487`
carries the four fixtures, all green. Gate: `python -m pytest user/scripts/test_doc_drift_lint.py -q`
→ 48/49 passed (see Runtime Verification note on the one failure, which is unrelated to this
bug's scope).

**Minimum Verifiable Behavior:** `python -m pytest user/scripts/test_doc_drift_lint.py -q -k multi_event`
is GREEN (4 passed); `python user/scripts/doc-drift-lint.py --repo-root .` reports zero findings
for the `lazy-route-inject.sh` subject (no exempted or drift line naming it). Confirmed this
cycle: full suite 49/49 passed; `doc-drift-lint.py --repo-root .` exits 0 (`0 drift findings, 2
exempted divergences` — the two exemptions are `block-work-repo-git-writes.sh` and the
pre-existing `algobooth` manifest entry, both unrelated to this bug).

**Runtime Verification** *(checked by the pytest suite — no app runtime):*
- [x] <!-- verification-only --> `python -m pytest user/scripts/test_doc_drift_lint.py -q` is
  fully green (49/49 passed), confirming `test_this_repo_is_clean` passes with no exemption
  needed for `lazy-route-inject.sh`. (A concurrently-running sibling bug,
  `legacy-tool-input-env-hooks-dead`, was mid-edit on the root `CLAUDE.md` Hooks table during
  this cycle — transiently tripped an unrelated `block-work-repo-git-writes.sh` finding on an
  earlier run of this same command; it landed its own row update before this phase closed, and
  the re-run above is fully green with no exemption on that row either.)

**MCP Integration Test Assertions:** N/A — no runtime-observable behavior via MCP in this repo;
the script's runtime observable is its own stdout/exit-code contract, asserted directly by the
pytest suite above.

**Prerequisites:** None (first and only phase).

**Files likely modified:**
- `user/scripts/doc-drift-lint.py` — `check_hooks` multi-event branch (verified: already landed,
  `:259-298`).
- `user/scripts/test_doc_drift_lint.py` — four multi-event fixtures (verified: already landed,
  `:406-487`).
- `CLAUDE.md` (root) — `lazy-route-inject.sh` Hooks-table row (verified: already landed, `:288`,
  marker retired, all three events documented).

**Testing Strategy:** Pure pytest over hermetic tmp-tree fixtures (the file's established
pattern) plus the module's own self-check (`test_this_repo_is_clean`) as the live-repo proof.

**Integration Notes for Next Phase:** None — final phase. The `__mark_fixed__` gate
(orchestrator-owned) flips `**Status:**` to `Fixed` and writes `FIXED.md` after the validation
tail; not a checkbox in this phase.

**Completion (gate-owned):** the `__mark_fixed__` gate flips SPEC.md / PHASES.md `**Status:**` to
`Fixed`, writes the `FIXED.md` receipt, and archives the bug once verification passes. This is
NOT a checkbox in the phase above.

---

## Review Notes

_(Populated by the /spec-phases Step 6 review gate and by later /execute-plan batch reviews.)_
