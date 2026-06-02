# CLAUDE.md — user/scripts/ (the `/lazy` autonomous pipeline)

This directory holds the **state machine that drives the `/lazy` family** of autonomous
orchestration skills. `lazy-state.py` is the source of truth; the skills are thin LLM
wrappers around it. When the pipeline's behavior needs to change, change the script —
not the wrappers — and keep the wrappers + smoke tests in lockstep (see Coupling Rule).

## What the lazy system is

A **file-driven** autonomous pipeline that walks a queue of work items (features via
`lazy-state.py`; bugs via `bug-state.py` — the lazy-bug family, see
`plans/lazy-bug-family.md`) through a fixed lifecycle, inferring "what to do next"
*purely from on-disk files* — never from
conversational memory. State lives in `**Status:**` lines, plan frontmatter, and
sentinel files. This is why the file contracts are load-bearing, not bureaucracy: a
malformed sentinel or a hand-flipped status corrupts the machine's view of the world.

```
queue.json + per-item SPEC/PHASES/plans/sentinels
        │
        ▼
  lazy-state.py  ──►  JSON { sub_skill, sub_skill_args, terminal_reason, … }
        │
        ▼
  thin skill wrapper  ──►  dispatch ONE sub-skill (or perform a __special_action__) ──► STOP
```

## Files in this directory

| File | Role |
|------|------|
| `lazy-state.py` | **Source of truth** for the feature state machine. Computes the next `/lazy` / `/lazy-cloud` action from `docs/features/`. ~2500 lines incl. an in-file smoke-test harness. Imports `lazy_core`. |
| `lazy_core.py` | Shared, domain-agnostic helpers (sentinel/plan parsing, deliverable counting, receipt writers, diagnostics infra) imported by both `lazy-state.py` and `bug-state.py`. Owns the per-invocation `_DIAGNOSTICS` list. `write_completed_receipt(..., kind=)`/`has_completion_receipt(..., filename=)` are parameterized so the bug pipeline can write `FIXED.md` (`kind: fixed`). |
| `bug-state.py` | Bug-lifecycle state machine over `docs/bugs/`. Same JSON contract as `lazy-state.py`; research/Gemini/stub steps dropped; terminal action is **archive-on-fix** (`__mark_fixed__`). Hybrid ordering (`queue.json` overrides, then severity + Discovered date). In-file `--test` smoke harness. Imports `lazy_core`. |
| `claude-bash-env.sh` | Restores `node`/`cargo` onto PATH for Claude Code's non-login Bash (sourced via `BASH_ENV`). Unrelated to the pipeline. |

## The skill family (thin wrappers)

All wrappers run `lazy-state.py`, dispatch the one named sub-skill (or perform a
`__special_action__`), and stop. They carry **no state-machine logic** of their own.

| Skill | Scope | Wraps | Purpose |
|-------|-------|-------|---------|
| `lazy` | user-level (`user/skills/`) | `lazy-state.py` | One sub-skill per invocation — manual stepping. |
| `lazy-batch` | user-level | `lazy-state.py` | Autonomous loop; spawns one Opus subagent per cycle. |
| `lazy-status` | user-level | `lazy-state.py` (read-only) | Progress dashboard; never acts. |
| `lazy-cloud` | repo (algobooth) | `lazy-state.py --cloud` | Cloud variant; defers Tauri/MCP/device steps. |
| `lazy-batch-cloud` | repo (algobooth) | `lazy-state.py --cloud` | Autonomous cloud loop. |
| `lazy-batch-retro` | repo (algobooth) | — | Audits/grades a completed batch run for skill-compliance. |
| `lazy-bug` | user-level (`user/skills/`) | `bug-state.py` | One sub-skill per invocation over `docs/bugs/`; `__mark_fixed__` archive-on-fix terminal. |
| `lazy-bug-batch` | user-level | `bug-state.py` | Autonomous bug loop; spawns one Opus subagent per cycle. |
| `lazy-bug-status` | user-level | `bug-state.py` (read-only) | Bug dashboard; never acts. |

> **Why some are repo-scoped:** `lazy`/`-batch`/`-status` are user-level but are in
> practice AlgoBooth-flavored (they read `$ALGOBOOTH_REAL_AUDIO_DEVICE`, dispatch
> AlgoBooth skills). The cloud + retro variants were added repo-scoped. The
> **lazy-bug family** (`lazy-bug`, `lazy-bug-batch`, `lazy-bug-status`) is **user-level**,
> mirroring the base trio, and drives `bug-state.py` over `docs/bugs/`. Its archive-on-fix
> terminal is documented in `_components/mark-fixed-archive.md`.

## The per-item lifecycle (features)

```
spec → research → phases → plan → implement (execute-plan)
     → retro (RETRO_DONE.md) → MCP validation (VALIDATED.md / skip / device-defer)
     → mark-complete (writes COMPLETED.md receipt, flips Status → Complete)
```

Step-by-step dispatch (see the `compute_state()` docstring + body for the authoritative
table): Step 2 find current item → Step 3 BLOCKED/NEEDS_INPUT → Step 4 SPEC → Step 4.5
stub-spec → Step 4.6 upstream realign → Step 5 research gate → Step 6 PHASES → Step 7
plan/execute → **Step 8 retro → Step 9 MCP gate → Step 10 mark-complete**.

## Three environments + the device axis

Two orthogonal axes; three environments. See `docs/features/CLAUDE.md` (in AlgoBooth) for
the full table. In short:

- **cloud** (`--cloud`) — no Tauri/MCP/device; defers MCP steps via `DEFERRED_NON_CLOUD.md`.
- **no-real-device workstation** (`--real-device no`, the default; `auto` reads
  `$ALGOBOOTH_REAL_AUDIO_DEVICE`) — runs MCP under the HeadlessPumpDriver; sustained-timing
  assertions are **deferred** via `DEFERRED_REQUIRES_DEVICE.md`, not skipped.
- **real-device workstation** (`ALGOBOOTH_REAL_AUDIO_DEVICE=1`) — re-opens device-deferred
  assertions and certifies them.

**Skip ≠ defer.** `SKIP_MCP_TEST.md` = permanent waiver (untestable on any host).
`DEFERRED_*` = re-opened later on the right host. Faking one for the other is the
anti-pattern the lint warns on.

## Completion is receipt-gated

An item is genuinely done only when `**Status:** Complete` **and** a `COMPLETED.md` receipt
exists. The receipt is written **only** by the completion-integrity gate inside
`__mark_complete__`. A `Complete` claim with no receipt is a hard error
(`completion-unverified` halt; `spec-complete-requires-receipt` lint). `Superseded` is
exempt. `--backfill-receipts` grandfathers pre-gate completions as
`provenance: backfilled-unverified` (honest debt, not silenced).

## Sentinel / plan / receipt schemas

Canonical schema: `user/skills/_components/sentinel-frontmatter.md` (mirrored in
AlgoBooth's `scripts/check-docs-consistency.ts` `SENTINEL_SCHEMAS` — keep the two in
lockstep). Every sentinel and plan file begins with a `---`-delimited YAML frontmatter
block; the markdown body is human context only (one exception: `NEEDS_INPUT.md`, whose
body is load-bearing). Plan files: `kind ∈ {implementation-plan, retro-plan, fix-plan,
realign-plan}`, `status` transitioned only by `/execute-plan`.

## CLI surface

```bash
python3 lazy-state.py                       # next workstation action (JSON on stdout)
python3 lazy-state.py --cloud               # cloud variant
python3 lazy-state.py --real-device auto    # resolve host audio capability from env
python3 lazy-state.py --skip-needs-research # batch: skip research-pending items
python3 lazy-state.py --repo-root <path>    # operate on a specific repo
python3 lazy-state.py --enqueue-adhoc …     # prepend an ad-hoc item to the queue
python3 lazy-state.py --backfill-receipts   # grandfather pre-gate completions
python3 lazy-state.py --test                # run the in-file fixture smoke tests
```

Exit codes: `0` success (even if terminal), `2` malformed input (bad YAML/queue.json).

## Coupling Rule (HARD REQUIREMENT)

When the state machine changes:

1. **Change `lazy-state.py` first** — it is the single source of truth.
2. **Keep the paired wrappers in sync** — at minimum `lazy` and `lazy-cloud` (they share a
   dispatch contract); update `lazy-batch`/`-cloud` if the terminal set changes.
3. **Keep `--test` green.** The in-file smoke harness (~30 fixtures) is the regression net.
   Run `python3 lazy-state.py --test` after every change; add a fixture for every new
   state branch.
4. **Keep schemas in lockstep** — `_components/sentinel-frontmatter.md` ↔
   `check-docs-consistency.ts` (features) / `check-bugs-consistency.ts` (bugs) ↔ these
   scripts' sentinel readers (`lazy_core.py`).

## Testing

`lazy-state.py --test` and `bug-state.py --test` build temp-dir fixtures and assert the
computed state. They are the only fast, hermetic check for state-machine correctness — **a
refactor that keeps `--test` green has preserved behavior.** Because both scripts share
`lazy_core.py`, any change there MUST keep BOTH suites green (and `lazy-state.py --test`
byte-identical to `tests/baselines/lazy-state-test-baseline.txt`, normalizing the per-run
`tempfile` suffix); `test_lazy_core.py` characterizes the shared helpers directly. Green
smoke tests are the acceptance gate before touching anything downstream.

## Related

- `plans/lazy-bug-family.md` — implementation plan for the bug-side pipeline.
- AlgoBooth `docs/features/CLAUDE.md` — the file contracts the script consumes.
- AlgoBooth `docs/bugs/CLAUDE.md` — bug-doc conventions (being aligned to the above).
- `user/skills/lazy/SKILL.md` — the canonical wrapper, fully commented.
