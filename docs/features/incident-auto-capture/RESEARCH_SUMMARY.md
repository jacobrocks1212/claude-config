---
kind: research-summary
feature_id: incident-auto-capture
date: 2026-07-04
source: codebase-survey (cloud session; Gemini research skipped per operator direction)
---

# Research Summary — incident-auto-capture

Codebase survey verifying every surface the SPEC names, at this lane's baseline
(`b5c1021`). SPEC line-anchors verified against the live tree; drift and one deliberate
implementation divergence are called out explicitly.

## Verified surfaces (SPEC assumptions that held)

| SPEC claim | Verified location | Notes |
|---|---|---|
| `lazy_guard.py::_write_breadcrumb` writes `{hook, error, at}` to the KEYED `claude_state_dir()` | `user/scripts/lazy_guard.py` (function at ~line 84; `claude_state_dir(create=True)`) | single-file `write_text` — last writer wins, as the SPEC says |
| Inline `_breadcrumb(err)` writers targeting the UN-KEYED base dir | `user/hooks/lazy-cycle-containment.sh` (`_breadcrumb`, `STATE_DIR` = `LAZY_STATE_DIR` or `~/.claude/state`), `user/hooks/long-build-ownership-guard.sh`, `user/hooks/build-queue-enforce.sh` | comment in lazy-cycle-containment confirms the deliberate base-dir residency |
| Hook-level denies persisted NOWHERE | all five hooks emit `permissionDecision: deny` JSON only; `grep append_deny_ledger user/hooks/*.sh` → no hits | the concrete D2 gap |
| `block-noncanonical-blocker-write.sh` / `block-sentinel-write-on-stray-branch.sh` have NO breadcrumb writer at all | verified — both fail open silently (`except Exception: sys.exit(0)`) | for these two, only the DENY site gets the appender (there is no error/breadcrumb site to wire) |
| `lazy_core.append_deny_ledger_entry` shape (`ts`/`tool_use_id`/`denied_sha12`/`reason_head`/`prompt_head`/`acked`) | `user/scripts/lazy_core.py` ~line 12592 | plain append (not `_atomic_write`) — deliberate, torn-line-tolerant reader |
| `append_friction_ledger_entry` → `kind: process-friction` entries with `reason_head`/`detail` | `lazy_core.py` ~line 12645 | same file as denies (`lazy-deny-ledger.jsonl`) |
| `read_deny_ledger` corrupt-line-tolerant reader | `lazy_core.py` ~line 12977 | reused by the collector |
| Ledger ALSO carries `auto_readmit: true` events (`acked: true`) and dispatch-by-reference audit events | `append_auto_readmit_event` ~line 12700, `append_dispatch_by_reference_event` ~line 11239 | **collector must skip these** — they are allows, not denies (not in the SPEC's inventory prose but consistent with it) |
| Sanctioned enqueue: `lazy-state.py --enqueue-adhoc --type bug` → `enqueue_adhoc_bug` → `bug-state.py --enqueue-adhoc` subprocess + `ADHOC_BRIEF.md` seed | `lazy-state.py` lines 582–760, handler at ~9853; `bug-state.py::enqueue_adhoc` ~line 1482 (duplicate id → `status: duplicate` no-op) | idempotency + `_atomic_write` queue write inherited, exactly as the SPEC claims. Handler is guarded by `refuse_if_cycle_active("--enqueue-adhoc")` (C3) — the collector must not launder past it (it inherits the caller's env unchanged) |
| Dedup surface: open one-level dirs under `docs/bugs/` + `docs/bugs/_archive/` | verified in-tree (claude-config itself has `docs/bugs/queue.json` + `_archive/` with archived dirs) | collector scans `docs/bugs/*/INCIDENT.md`, `docs/bugs/_archive/*/INCIDENT.md`, and `queue.json` ids |
| `toolify-miner.py` read-only-miner precedent (tests hash fixture dirs before/after) | `user/scripts/toolify-miner.py` + `test_toolify_miner.py` | discipline copied for `incident-scan.py` tests |
| Keyed state dir + `LAZY_STATE_DIR` override semantics | `lazy_core.claude_state_dir` ~line 9209 (`LAZY_STATE_DIR` set → exact dir; unset → `~/.claude/state/<repo_key>/`) | appender + collector honor the identical override so every hook pipe-test stays hermetic |

## Integration points

- **Hook edits (D2):** additive appender at the deny sites of the five bash hooks + the error
  (`_breadcrumb`/`_write_breadcrumb`) sites of the three that have one, plus `lazy_guard.py`'s
  error site. Deny/allow JSON output and `hook-error.json` writes stay byte-identical
  (`test_hooks.py` pins this).
- **Python form:** `lazy_core.append_hook_event(...)` (sibling of
  `append_friction_ledger_entry`, same swallow-everything fail-open contract) for
  `lazy_guard.py`; the bash-callable form is the per-hook inline `_append_hook_event` snippet
  (the `_breadcrumb` pattern the SPEC itself cites), which tries the keyed dir via `lazy_core`
  when a scripts dir is resolvable and falls back to the base dir.
- **Collector:** `user/scripts/incident-scan.py` imports `lazy_core` for
  `set_active_repo_root`/`claude_state_dir`/`read_deny_ledger`/`repo_key` but is NOT imported by
  any state script (off the compute path).
- **Orchestrator wiring (D6-A):** one additive paragraph inside the EXISTING
  `### 1c.6` section of `user/skills/lazy-batch/SKILL.md`, mirrored into
  `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md`. Placing it under an existing
  heading means `lazy-parity-manifest.json` needs NO new `headings[]` entries (C1 audits
  headings, not body prose) — verified against `lazy_parity_audit.py` C1–C6 logic.
- **Skill:** `user/skills/incident-scan/SKILL.md` (thin wrapper — presentation only; all logic
  in the script), validated by `lint-skills.py` + `project-skills.py`.

## Spec assumptions that proved wrong / were tightened

1. **"wire the appender into the deny/error sites of … `lazy_guard.py`"** — `lazy_guard.py`'s
   deny sites ALREADY persist durably to the deny ledger (it is the ledger's only writer).
   Appending the same denies to `hook-events.jsonl` would count one incident in two signal
   classes (`deny` + `hook-deny`) under two distinct D4 cluster keys, which D5's key-equality
   dedup cannot fold — two stubs for one incident. Implemented conservatively: the appender is
   wired at `lazy_guard.py`'s fail-open ERROR site only. Recorded in the SPEC under D2's
   Resolution (2026-07-04).
2. **`hook-error.json` as a countable input** — it is a single overwritten file, so it can add
   at most ONE occurrence, and post-D2 that occurrence is always a duplicate of the newest
   `kind: error` event line (the appender fires at the same sites). Deterministic rule adopted:
   the crumb counts as one occurrence ONLY when the events file has no error entry for that hook
   (legacy pre-D2 crumbs); otherwise it is ignored.
3. **Severity on the enqueue** — `enqueue_adhoc_bug` accepts a `severity` kwarg but the
   `--enqueue-adhoc` CLI handler never passes it; the queue entry lands `severity: null`. This
   matches D7 ("never sets severity beyond the enqueue default") — the collector simply omits it.
4. **UX example's `incident_key`** shows a repo NAME prefix (`claude-config|deny|…`); D4's
   cluster key names `repo_key`. Since a scan is always scoped to ONE repo and dedup matches
   keys inside that repo's own `docs/bugs/`, the readable basename form from the UX example is
   used verbatim (deterministic; no cross-repo ambiguity is possible on the dedup surface).

## Environment constraints (this lane)

- Linux container, python3.11 + pytest + pyyaml; no PowerShell (irrelevant here — no `.ps1`
  surface in this feature). All tests hermetic via `LAZY_STATE_DIR` / temp repo-root fixtures.
- `~/.claude/*` symlinks absent — everything repo-relative; the end-of-run prose keeps the
  `~/.claude/scripts/` invocation form used by every sibling skill (resolved on the live
  machine by the symlink farm).
