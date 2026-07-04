---
kind: research-summary
feature_id: operator-halt-notifications
date: 2026-07-04
source: codebase-survey (cloud session; Gemini research skipped per operator direction)
---

# Research Summary — operator-halt-notifications

Honest codebase survey verifying every surface the SPEC names, at the CURRENT tree (the SPEC's
line anchors were written before harness-telemetry-ledger / queue-dependency-dag /
code-doc-provenance-linkage / incident-auto-capture landed, so several drifted — all re-verified
below).

## Surfaces verified (with drift notes)

| SPEC claim | Verified reality (this tree) |
|---|---|
| `_state(..., terminal_reason=, notify_message=)` at `lazy-state.py` ~111 | Confirmed: `def _state(` at `user/scripts/lazy-state.py:111`. Every feature-pipeline halt flows through it. |
| `bug-state.py` mirror at ~260 | Drifted name, not shape: the bug pipeline's output helper is `_bug_state(` at `user/scripts/bug-state.py:257` (same kwargs incl. `terminal_reason` / `notify_message`). |
| Terminal-emission chokepoint in `main()` "~line 10109" | Drifted: the single post-`compute_state` emission is now `sys.stdout.write(json.dumps(state, indent=2) + "\n")` at `lazy-state.py:11453` and `bug-state.py:7009`. All earlier `return`s in `main()` are special-action handlers (`--run-start`, `--apply-pseudo`, …) that print their OWN JSON and never carry a `compute_state` terminal — so "immediately before the state-JSON write" is still the one true chokepoint. |
| `notify_message` already composed + item-naming | Confirmed (e.g. `NEEDS INPUT: {feature_name} — {writer} halted on an ambiguous decision.` at `lazy-state.py:2833-2838`); the in-file `--test` harness asserts terminal notify messages name the feature. |
| `parse_sentinel` available for `decisions:` | Confirmed (`lazy_core.py:784`) — BUT it `_die()`s (error JSON to stdout + `sys.exit(2)`) on unreadable/malformed frontmatter. Calling it from the notifier could corrupt the halt JSON, so the notifier uses a tolerant local read of the same fence contract (SPEC D5 implementation note added). |
| Per-repo keyed state dir via `claude_state_dir()` | Confirmed (`lazy_core.py:9722`): `LAZY_STATE_DIR` set ⇒ exact dir (hermetic tests); unset ⇒ `~/.claude/state/<repo_key>/`. `create=False` read discipline available for the ledger read path. |
| `_atomic_write` / `_diag` conventions | Confirmed (`lazy_core.py:105` / `:91`). NOTE: `_diag` appends to `lazy_core._DIAGNOSTICS`, but `_state()` COPIES that list into the state dict — a `_diag` call made after `compute_state` returns does NOT reach the printed JSON. The notifier therefore appends its send-attempt trail directly to `state["diagnostics"]` (the call site runs before the JSON print, so the line lands). |
| `hook-error.json` breadcrumb pattern | Confirmed (single overwritten at-a-glance file; countable history is `hook-events.jsonl`). `notify-error.json` mirrors the single-overwritten-file shape via `_atomic_write`. |
| `SANCTIONED_STOP_TERMINAL` sibling placement | Confirmed (`lazy_core.py:9781`). D3's note holds: `needs-research` / `queue-blocked-on-research` ARE sanctioned stops and ARE attention terminals — the new frozenset is not the complement. |
| Attention-set terminal spellings | All 11 locked ids verified as live literals: `blocked`, `blocked-misnamed`, `needs-input`, `needs-spec-input`, `needs-research`, `queue-blocked-on-research`, `completion-unverified`, `stale_upstream` (underscore — verified in BOTH scripts: `lazy-state.py:5553`, `bug-state.py` `TR_STALE_UPSTREAM = "stale_upstream"`), `queue-exhausted-all-parked`, `queue-exhausted-budget-deferred` (feature-only), `queue-missing`. |
| Clean stops (opt-in set) | `all-features-complete`, `all-bugs-fixed`, `cloud-queue-exhausted`, `device-queue-exhausted`, `host-capability-saturated` — all live literals. |
| `--neutralize-sentinel` rename convention | Confirmed — dedup keyed on `(…, mtime_ns, size)` of the sentinel file self-clears on rename (path gone ⇒ a re-halt writes a new file ⇒ new identity). |
| `detect_noncanonical_blocker` for the `blocked-misnamed` stray | Confirmed (`lazy_core.py:4892`, returns the stray `Path` or `None`, never raises). |
| Parity audit | `lazy_parity_audit.py::audit_state_script_parity` currently enumerates SIX coupled-pair surfaces (active-repo binding, `--reorder-queue`, `--reassert-owner`, host-capability fail-fast, `cycle_prompt_ref`, `--sync-deps`); `test_lazy_parity.py::TestStateScriptParity` stubs mirror the list in LOCKSTEP (docstring names the count). This feature adds surface #7 (`lazy_core.notify_halt(` present in both scripts) — the fixtures and docstrings move six → seven together. |

## Integration points with freshly-landed siblings

- **harness-telemetry-ledger:** `--emit-prompt` already appends a `halt` telemetry event when
  `terminal_reason ∈ lazy_core.TELEMETRY_HALT_TERMINAL_REASONS` (`lazy_core.py:14565`, wired at
  `lazy-state.py:~11405` / `bug-state.py:~6975`). The notifier COMPOSES with it, never duplicates:
  telemetry records (marker-gated, `--emit-prompt`-only, JSONL history); notify pages (config-gated,
  every terminal emission, dedup-ledgered). The `notify_halt` call site sits AFTER the telemetry
  block (physically at the final JSON write), touching neither. The two attention sets are
  deliberately different objects: telemetry's 6-element halt-dwell set vs. the notifier's 11-element
  operator-action set — no shared constant is factored (their semantics differ; D3 is locked on the
  11-element list).
- **queue-dependency-dag:** added the `queue-exhausted-dependency-gated` clean terminal. It is in
  NEITHER notify set (not in the locked D3 attention list; not one of the five named clean stops),
  so it never pages — consistent with D3's "pages mean you are needed" (holds re-open by
  themselves as deps complete). Documented as a boundary, not an accident.
- **code-doc-provenance-linkage / incident-auto-capture:** no overlap with the terminal-emission
  path; `incident-scan.py` reads state-dir ledgers but only `lazy-deny-ledger.jsonl` /
  `hook-events.jsonl` / `hook-error.json` — `notify-ledger.json` / `notify-error.json` are new
  filenames it ignores by construction.
- **`--test` smoke harnesses:** both scripts' `run_smoke_tests()` build fixtures and call
  `compute_state` directly — which never calls the notifier (main()-only call site), so every
  existing fixture is untouched. The new call-site fixtures drive `main()` in-process (patched
  `sys.argv` + captured stdout + `LAZY_NOTIFY_URL` + a monkeypatched module-level ntfy sender) so
  the wiring itself is exercised; baselines re-pinned only via `_normalize_smoke_output`.
- **`pipeline_visualizer` / `lazy-queue-doc.py`:** shell the state scripts (`probe_state`), so a
  halted repo IS re-observed by every dashboard refresh — exactly the D4 dedup motivation. With no
  config in those environments the notifier is a no-op; with config, the ledger caps it at one page.

## Spec assumptions that proved wrong / adjusted

1. **`parse_sentinel` is not fail-OPEN-safe** (dies loudly on malformed input — correct for the
   state machine, fatal for an observer). Adjusted: tolerant local frontmatter read in the
   notifier; recorded as a D5 implementation note in SPEC.md.
2. **`_diag()` after `compute_state` cannot reach the output JSON** (the state dict holds a copy).
   Adjusted: the notifier appends its trail to `state["diagnostics"]` directly (only on send
   attempts — the inert path never mutates the dict, preserving byte-identity).
3. **Line anchors** (`main()` ~10109; `bug-state.py` `_state` ~260) drifted as expected; re-anchored
   above. No behavioral assumption broke.
4. **ntfy header encoding:** `notify_message` strings routinely carry em-dashes (non-latin-1);
   `http.client` rejects non-latin-1 header values. The ntfy sender RFC-2047-encodes (`=?UTF-8?B?…?=`,
   which ntfy documents support for) the `Title`/`Click` headers when needed — otherwise the very
   first real page would trip the fail-OPEN path instead of delivering.

## What this feature does NOT touch (verified boundaries)

- The §1c.6 `PushNotification` orchestrator prose (all four `/lazy*` batch skills) — zero edits.
- `compute_state` in either script — the notifier is main()-only, post-compute.
- The repo work tree — the notifier writes only under `claude_state_dir()` (ledger + breadcrumb).
- `queue.json` / ROADMAP / any other feature's directory.
