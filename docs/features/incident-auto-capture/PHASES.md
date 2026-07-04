# Implementation Phases — Incident Auto-Capture → Bug Stubs

> Phases for [`SPEC.md`](./SPEC.md)

**Status:** Complete
<!-- All 4 phases implemented + validated 2026-07-04 (pytest gate suite 1228 passed / 2 sanctioned skips incl. test_hooks 130 + test_incident_scan 15; --test smokes green; parity audit exit 0; lint/projection clean). NOT Complete on the
     SPEC — the __mark_complete__ integrity gate owns the SPEC Complete flip + COMPLETED.md
     receipt. Phase-4 live-run tuning row deferred (no workstation ledger history in this cloud lane). -->

**MCP runtime:** not-required — pure claude-config harness mechanics (a stdlib Python collector, additive bash-hook appender lines, orchestrator/skill prose). No Tauri app, no MCP-reachable surface; validation is `pytest` (`test_incident_scan.py`, `test_hooks.py`, `test_lazy_core.py`), the state-script `--test` smoke baselines, `lazy_parity_audit.py`, and `lint-skills.py`/`project-skills.py`. This is the `standalone — no app integration` untestable class → `SKIP_MCP_TEST.md` at the MCP gate.

## Cross-feature Integration Notes

`**Depends on:** harness-telemetry-ledger — soft` (not yet implemented; v1 reads the existing artifacts directly, per the SPEC's dependency note — no upstream PHASES.md to integrate against). Substantive dependencies are **shipped data contracts**, all verified in `RESEARCH_SUMMARY.md`:

- **`hook-error.json` breadcrumbs** — the fail-OPEN convention across `user/hooks/*.sh` + `lazy_guard.py::_write_breadcrumb`. Phase 1 ADDS an events append beside these sites; the breadcrumb writes stay byte-identical (migration note: the crumb remains the at-a-glance "is a hook broken" file; the events file is the countable history).
- **`lazy-deny-ledger.jsonl`** — guard denies (`append_deny_ledger_entry`), `kind: process-friction` entries (`append_friction_ledger_entry`), `auto_readmit` / dispatch-by-reference audit events. Read via `lazy_core.read_deny_ledger` (corrupt-line-tolerant); the collector must SKIP the audit-event shapes (allows, not denies).
- **`--enqueue-adhoc --type bug`** — the sanctioned enqueue path (`lazy-state.py::enqueue_adhoc_bug` → `bug-state.py::enqueue_adhoc`, duplicate-id no-op, `_atomic_write` queue write, `ADHOC_BRIEF.md` seed). The collector shells it; it never re-implements a queue write.
- **`docs/bugs/` stub conventions** — open one-level dirs + `docs/bugs/_archive/` (the D5 dedup surface); `/spec-bug` owns root cause downstream.

---

### Phase 1: Event persistence (D2)

**Phase kind:** integration

**Scope:** Make hook denies/errors countable without destabilizing the fail-OPEN guards. Shared fail-open appender (Python form in `lazy_core`; bash-callable form = the per-hook inline `_append_hook_event` snippet, the `_breadcrumb` pattern), writing append-only `hook-events.jsonl` entries `{ts, kind: "error"|"deny", hook, repo_root, signature, detail}` into the keyed state dir when resolvable, else the base dir. Hooks change NOTHING else — `hook-error.json` writes and deny/allow JSON stay byte-identical.

**Deliverables:**
- [x] `lazy_core.append_hook_event(kind, hook, signature, detail, repo_root=None, now=None)` — swallow-everything fail-open JSONL appender (contract mirror of `append_friction_ledger_entry`); writes `claude_state_dir()/hook-events.jsonl`.
- [x] Deny-site appends (additive) in `lazy-cycle-containment.sh` (per-trip signature tokens), `block-noncanonical-blocker-write.sh` (`noncanonical-blocker`), `block-sentinel-write-on-stray-branch.sh` (`stray-branch-sentinel`), `long-build-ownership-guard.sh` (`LONG-BUILD-OWNERSHIP-TAKEOVER`), `build-queue-enforce.sh` (the classified op, e.g. `dotnet-build`).
- [x] Error-site appends beside every existing breadcrumb write: the three bash `_breadcrumb` writers + `lazy_guard.py::_write_breadcrumb` (guard DENY sites deliberately excluded — already ledgered; see SPEC D2 implementation note).
- [x] `test_hooks.py` additions (registered in `_TESTS`): deny output byte-unchanged + event line appended per hook; append failure (events path unwritable) swallowed — deny still emitted, exit 0.

**Minimum Verifiable Behavior:** Piping a deny-producing PreToolUse payload through an edited hook with `LAZY_STATE_DIR` set yields the byte-identical deny JSON AND exactly one parseable `hook-events.jsonl` line (`kind: "deny"`, correct `hook`/`signature`); making the events path unwritable changes nothing about the deny.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [x] Deny/allow outputs byte-unchanged with the appender failing and succeeding. *(Evidence: `test_hooks.py` new deny+event / fail-open fixtures, suite green.)* <!-- verification-only -->
- [x] Events appended on deny/error across the wired hooks. *(Evidence: `test_hooks.py` per-hook event assertions.)* <!-- verification-only -->

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface

**Prerequisites:** None (first phase).

**Files likely modified:** `user/scripts/lazy_core.py`, `user/scripts/lazy_guard.py`, `user/hooks/lazy-cycle-containment.sh`, `user/hooks/block-noncanonical-blocker-write.sh`, `user/hooks/block-sentinel-write-on-stray-branch.sh`, `user/hooks/long-build-ownership-guard.sh`, `user/hooks/build-queue-enforce.sh`, `user/scripts/test_hooks.py`, `user/scripts/test_lazy_core.py`.

**Testing Strategy:** TDD via the existing `test_hooks.py` pipe-test harness (`LAZY_STATE_DIR` fixture dirs; `_run_bash` + decision extractor). `append_hook_event` unit-tested in `test_lazy_core.py` (registered in `_TESTS`). Existing matrices untouched — they pin byte-identity.

**Integration Notes for Next Phase:** Phase 2's collector reads the exact entry shape this phase writes; signature tokens chosen here ARE the D4 hook-deny cluster signatures.

---

### Phase 2: Collector core

**Phase kind:** design

**Scope:** `user/scripts/incident-scan.py` — stdlib, deterministic, read-only over inputs. Readers (deny ledger via `read_deny_ledger`; `hook-events.jsonl` keyed + attributed base-dir entries; legacy `hook-error.json` counted only when the events file has no error entry for that hook), D4 clustering `(repo_key, signal_class, signature)`, D3 recurrence bars as a top-of-script config block, D5 dedup mechanics (`incident_key` scan over open + archived `INCIDENT.md` + `queue.json` ids), `--dry-run` report, `--now` injection for hermetic windows.

**Deliverables:**
- [x] `incident-scan.py` with `--repo-root` / `--dry-run` (+ hidden `--now` test seam); config block `SIGNAL_BARS` + `ENQUEUE_CAP` + `EXCERPT_CAP` at the top.
- [x] Signal classes: `deny` (ledger, `denied_sha12` + first `reason_head` token; skips `auto_readmit`/by-reference audit events; `acked` still counts), `friction` (`kind: process-friction` by `reason_head`), `hook-error` (events `kind: error` per hook), `hook-deny` (events `kind: deny` per hook+signature).
- [x] Deterministic slugs `adhoc-incident-<signal-class>-<short-hash>`; idempotent scans (same inputs → same clusters/keys/slugs).
- [x] `test_incident_scan.py` (pytest): seeded fixtures → expected clusters; below-bar never proposes; dedup vs open + archived keys; input dirs hashed before/after (read-only bar); `--dry-run` prints `would-enqueue` and mutates nothing.

**Minimum Verifiable Behavior:** A seeded state dir with 3 same-signature denies in-window and 2 of another produces exactly one above-bar cluster in `--dry-run` output, and the SHA-256 walk of the state dir + `docs/bugs/` is unchanged by the scan.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [x] Collector is read-only over its inputs (hash before/after equal on dry-run and on the non-sanctioned surfaces of a real run). *(Evidence: `test_incident_scan.py` hash-guard fixtures.)* <!-- verification-only -->
- [x] Recurrence bars hold (2-of-3 denies → no proposal; bar-clearing cluster → proposal). *(Evidence: `test_incident_scan.py` bar fixtures.)* <!-- verification-only -->

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface

**Prerequisites:** Phase 1 (entry shape + signatures).

**Files likely modified:** `user/scripts/incident-scan.py` (new), `user/scripts/test_incident_scan.py` (new).

**Testing Strategy:** Pure pytest, hermetic via `LAZY_STATE_DIR` + temp repo roots; injected `--now` pins the windows. No `--test` in-file harness (the collector is not a state script); mirrors `test_toolify_miner.py`'s hash-the-inputs discipline.

**Integration Notes for Next Phase:** Phase 3 consumes `propose()`'s ordered cluster list; the capsule writes and the enqueue subprocess are the ONLY mutations and both live behind the `--dry-run` gate.

---

### Phase 3: Enqueue integration (D7)

**Phase kind:** integration

**Scope:** For bar-clearing, non-deduped clusters (≤ cap, highest recurrence first): shell `lazy-state.py --enqueue-adhoc --type bug --id <slug> --name <title> --brief <summary> --repo-root <root>` (env inherited unchanged — the C3 guard's verdict applies to the real caller), then atomically write the `INCIDENT.md` capsule (`kind: incident-capture`, `incident_key`, `signal_class`, `occurrences`, `window`, `first_ts`/`last_ts`, `recurrence_of` when D5-A applies; body = capped verbatim ledger/event lines). One announce line per enqueue (adhoc-enqueue component format) + the one-line scan summary.

**Deliverables:**
- [x] Enqueue subprocess + capsule writer (via `lazy_core._atomic_write`) + `recurrence_of:` for archived-key recurrences (suffix-slugged so the archive dir is never collided with, never mutated).
- [x] ≤2-per-scan cap (config), highest recurrence first, deterministic tie-break; reported-only remainder still printed.
- [x] Announce lines + `incident-scan: N clusters observed, M cleared the bar, K enqueued, D deduped` summary; empty scan exits 0 with the summary line.
- [x] `test_incident_scan.py` end-to-end fixtures: queued stub + correct capsule; second run no-op (dedup vs the new open key); archived-only key → new stub carrying `recurrence_of`; removed-then-recurring dir-present behavior (no re-enqueue while the key exists); cap fixture (5 clearing clusters → 2 enqueued).

**Minimum Verifiable Behavior:** An end-to-end fixture run yields `docs/bugs/<slug>/` containing `ADHOC_BRIEF.md` + a well-formed `INCIDENT.md`, the queue head is the stub, and an immediately repeated scan enqueues nothing.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [x] Bar clears → stub at queue head with correct capsule; second run is a no-op. *(Evidence: `test_incident_scan.py` end-to-end + idempotency fixtures.)* <!-- verification-only -->
- [x] Enqueue cap: 5 bar-clearing clusters, cap 2 → 2 enqueued, 3 reported-only. *(Evidence: `test_incident_scan.py` cap fixture.)* <!-- verification-only -->

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface

**Prerequisites:** Phases 1–2.

**Files likely modified:** `user/scripts/incident-scan.py`, `user/scripts/test_incident_scan.py`.

**Testing Strategy:** pytest end-to-end against a temp repo (real `lazy-state.py`/`bug-state.py` subprocesses, `LAZY_STATE_DIR` temp dir) — the enqueue path is exercised for real, not mocked.

**Integration Notes for Next Phase:** Phase 4 wires the invocation points only; the collector's CLI surface is frozen after this phase.

---

### Phase 4: Wiring + docs (D6-A)

**Phase kind:** chore

**Scope:** End-of-run step in the `/lazy-batch` orchestrator prose (inside the existing §1c.6 halt policy — before `--run-end` on every terminal/halt path), mirrored to `/lazy-batch-cloud` per the coupled-pair discipline (no divergence ⇒ no Differences-block row; parity audit exit 0 — no new headings, so no manifest change). On-demand `user/skills/incident-scan/SKILL.md`. Doc rows (root `CLAUDE.md` + `user/scripts/CLAUDE.md` script tables; `user/hooks/CLAUDE.md` events-appender note). Projection + lint green.

**Deliverables:**
- [x] `/lazy-batch` §1c.6 incident-scan paragraph (BEFORE `--run-end`, once per run, non-blocking on error) + `/lazy-batch-cloud` mirror.
- [x] `user/skills/incident-scan/SKILL.md` (thin wrapper: run the script, relay its report; `--dry-run` pass-through).
- [x] Doc rows: root `CLAUDE.md` Scripts table, `user/scripts/CLAUDE.md` files table, `user/hooks/CLAUDE.md` appender note.
- [x] Full gate suite + `project-skills.py` (lane-local output dir) + `lint-skills.py` + `lazy_parity_audit.py --repo-root .` all green.
- **DEFERRED (workstation-only, not a completion blocker):** live tuning of D3 thresholds against real accumulated ledgers — this cloud lane has no workstation ledger history to scan; the config-block defaults ship as approved and tuning is the operator's first-capture review (SPEC Phase 4 "empirical checks" bullet).

**Minimum Verifiable Behavior:** `lint-skills.py` + `project-skills.py` clean with the new skill; parity audit exit 0 with the mirrored prose; a manual `incident-scan.py --dry-run --repo-root .` on this repo prints the summary line and exits 0.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [x] Parity audit exit 0 after the coupled-pair prose edit. *(Evidence: `lazy_parity_audit.py --repo-root .` in the gate suite.)* <!-- verification-only -->
- **DEFERRED (workstation-only, not a completion blocker):** a real run's end-of-run flush produces a scan report in the run log + false-positive review of the first captures. *(Deferred — requires a live workstation batch run; not reachable in this lane. The on-demand `--dry-run` smoke on this repo stands in.)* <!-- verification-only -->

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface

**Prerequisites:** Phases 1–3.

**Files likely modified:** `user/skills/lazy-batch/SKILL.md`, `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md`, `user/skills/incident-scan/SKILL.md` (new), `CLAUDE.md`, `user/scripts/CLAUDE.md`, `user/hooks/CLAUDE.md`.

**Testing Strategy:** Docs/lint/parity gates + the `--dry-run` smoke; no behavior change outside the prose.
