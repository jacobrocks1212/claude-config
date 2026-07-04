# Incident Auto-Capture → Bug Stubs — Feature Specification

> Hooks write `hook-error.json` breadcrumbs and the dispatch guard writes deny-ledger entries, but
> turning a runaway/deny-loop into a `docs/bugs/` entry is manual retro work. A deterministic
> collector that scans breadcrumbs + repeated-deny patterns, clusters them, applies a per-signal
> recurrence bar, dedups against open/archived bug slugs, and enqueues stub-status bugs via the
> existing `--enqueue-adhoc --type bug` path closes the observe→harden loop without waiting for
> `/lazy-batch-retro`. The collector proposes evidence; `/spec-bug` still owns root cause.

**Status:** Draft
**Priority:** P2
**Last updated:** 2026-07-04
**Source:** repo-exploration proposal session 2026-07-04; fleshed out via internal desk research
2026-07-04 (Gemini research skipped by operator directive — see RESEARCH.md)

**Depends on:**
- harness-telemetry-ledger — soft — halt/deny events may migrate onto the telemetry ledger once it exists; v1 reads the existing breadcrumb and deny-ledger artifacts directly.

> Substantive dependencies on **implemented data contracts, not sibling specs**:
> - `hook-error.json` breadcrumbs — the fail-OPEN convention across `user/hooks/*.sh` and
>   `user/scripts/lazy_guard.py` (`_write_breadcrumb`): every hook error path allows AND drops a
>   `{hook, error, at}` crumb.
> - `~/.claude/state/<repo_key>/lazy-deny-ledger.jsonl` — guard denies
>   (`lazy_core.append_deny_ledger_entry`: `ts`/`tool_use_id`/`denied_sha12`/`reason_head`/
>   `prompt_head`/`acked`), `kind: process-friction` entries from the `--cycle-end` friction
>   detector (`append_friction_ledger_entry` ← `detect_cycle_bracket_friction`), and
>   `auto_readmit` events. Read via `lazy_core.read_deny_ledger` (corrupt-line-tolerant).
> - `--enqueue-adhoc --type bug` — the sanctioned enqueue path (`_components/adhoc-enqueue.md`):
>   prepends `docs/bugs/queue.json` via the existing `bug-state.py enqueue_adhoc`, seeds
>   `docs/bugs/<slug>/` + `ADHOC_BRIEF.md`; the pipeline routes the stub to `/spec-bug`.
> - `bug-state.py` stub conventions — `Status: Investigating` → `Concluded` lifecycle
>   (`docs/bugs/CLAUDE.md`), archive-on-fix to `docs/bugs/_archive/` (the dedup scan surface).

---

## Executive Summary

The mission statement says friction observed in a run is a bug report against this repo — but
today that report only materializes if a retro notices it. The harness already emits structured
evidence at the moment of friction: fail-OPEN hooks drop `hook-error.json` breadcrumbs, the
dispatch guard appends every deny to `lazy-deny-ledger.jsonl`, and the `--cycle-end` friction
detector appends `kind: process-friction` entries for torn brackets, unexpected commits, and
branch divergence. Between retros this evidence sits unread — and some of it is actively lost:
the breadcrumb is a single overwritten file (last writer wins), and hook-level denies
(containment trips, noncanonical-sentinel and stray-branch denies, build-queue redirects) are
emitted as PreToolUse JSON and persisted nowhere at all.

The fix is a **read-only, deterministic collector** (stdlib Python, the `toolify-miner.py`
discipline: scans state dirs and artifacts, never mutates them) that clusters signals by a
per-signal key, applies a recurrence bar (one-off fail-OPEN ≠ incident), dedups against every
open and archived bug slug, and — for clusters that clear the bar — enqueues a stub-status bug
through the existing sanctioned `--enqueue-adhoc --type bug` path, seeding an `INCIDENT.md`
evidence capsule beside `ADHOC_BRIEF.md` so `/spec-bug` starts from raw evidence instead of a
cold slug. A small prerequisite phase normalizes persistence so the stub's full signal inventory
is actually observable (append-only events file; the breadcrumb writers keep their current
behavior). The retro remains the deep-analysis pass; this feeds the same pipeline earlier.

Mission criteria served: **effective** (friction becomes a routed work item with evidence
attached, not a memory), **efficient** (no retro-sized token spend to notice a recurring deny;
the collector is a script, not a model), **best-practice-aligned** (the observe→harden loop gets
a deterministic front end; noise control is explicit policy, not vibes).

## Design Decisions

### D1. Collector shape and placement

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** What is the collector, and what is it allowed to touch?
- **Options:**
  - **A — stdlib script `user/scripts/incident-scan.py`, read-only over inputs, writing only
    through the sanctioned enqueue:** scans the per-repo keyed state dir (deny ledger, events
    file, breadcrumbs) + `docs/bugs/**` for dedup; its ONLY mutations are (1) the
    `--enqueue-adhoc --type bug` subprocess and (2) seeding `INCIDENT.md` into the dir that
    enqueue just created (atomic write). `--dry-run` reports proposals without enqueueing.
  - **B — fold into `lazy-state.py`/`bug-state.py`:** puts a scanner on the state-machine compute
    path and forces a coupled-pair mirror for logic that is not per-pipeline.
  - **C — a hook:** hooks are per-tool-call and fail-OPEN; a collector needs batch context and
    must never sit on the hot path.
- **Recommendation:** A — matches the `toolify-miner.py` precedent (standalone analysis tool,
  READ-ONLY over logs, proposes; promotion/enqueue is the deliberate act) and keeps the state
  scripts' compute path untouched. Not a `lazy_core` extension: nothing on the dispatch path
  consumes it.
- **Resolution:** Auto-accepted A; tool placement with a direct house precedent, invisible to the
  operator's workflow.

### D2. Signal-persistence normalization (the breadcrumb-schema standardization the stub asks for)

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** Today's artifacts cannot support the stub's full signal inventory. Inventory of
  actual writers (verified in-repo):
  - `hook-error.json` — written by `lazy-cycle-containment.sh`, `build-queue-enforce.sh`,
    `long-build-ownership-guard.sh` (inline Python `_breadcrumb`) and `lazy_guard.py`
    (`_write_breadcrumb`). The SHAPE is already uniform (`{hook, error, at}`), but: (1) it is a
    single file opened `"w"` — **last writer wins; recurrence is uncountable**; (2) residency is
    split — the bash hooks deliberately write the UN-KEYED base `~/.claude/state/` (documented in
    `lazy-cycle-containment.sh`) while `lazy_guard.py` writes the keyed `claude_state_dir()`;
    (3) the un-keyed crumbs carry no repo attribution.
  - `lazy-deny-ledger.jsonl` — append-only and durable, but ONLY `lazy_guard.py` appends. The
    hook-level denies the stub names as signals (containment trips, noncanonical-sentinel denies,
    stray-branch denies, build-queue redirects, long-build takeovers) are emitted as PreToolUse
    deny JSON and then **lost**.
  How do we make these observable without destabilizing six fail-OPEN hooks?
- **Options:**
  - **A — additive append-only events file:** a shared, best-effort JSONL appender (bash-callable,
    mirroring `append_friction_ledger_entry`'s swallow-everything contract) writes
    `hook-events.jsonl` entries `{ts, kind: "error"|"deny", hook, repo_root, signature, detail}`
    into the keyed state dir when the repo is resolvable, else the base dir. Hooks ADD one
    appender call at their existing breadcrumb/deny sites and change nothing else —
    `hook-error.json` keeps being written byte-identically (migration note: it stays the
    at-a-glance "is a hook broken" file and the back-compat surface; the events file is the
    countable history; revisit retiring the single-file crumb only after the collector has run
    for a while, and note the soft dep — these events are exactly what would migrate onto
    `harness-telemetry-ledger` if it ships).
  - **B — collector reads only what exists today:** deny ledger + the single breadcrumb. Honest
    but silently drops most of the stub's signal list — a containment trip, the highest-value
    incident class, would remain invisible.
  - **C — rewrite hooks to log richly:** maximal data, maximal regression risk on load-bearing
    fail-OPEN guards.
- **Recommendation:** A. It is the smallest change that makes the operator's stated signal list
  real, it is fail-open at every site (an append failure can never change a hook's deny/allow
  output — same sacred rule as the deny ledger), and it is covered by the existing
  `test_hooks.py` harness. Signature fields reuse what each hook already computes (deny-signature
  string, `denied_sha12`, blocker kind) — no new inference.
- **Resolution:** Auto-accepted A; invisible plumbing with the fail-open contract preserved, and
  the stub explicitly requests the standardization + migration note this delivers.

### D3. Signal inventory + per-signal recurrence bars (v1)

- **Classification:** `product-behavior (OPEN — operator confirmation required via the pipeline's
  needs-input round before implementation)`
- **Question:** Which signals can create a bug stub in v1, and how many occurrences within what
  window clear the bar? This decides what shows up in the operator's bug queue — the core
  noise-control policy (one-off fail-OPEN ≠ incident).
- **Options:** proposed v1 table (all values estimated — confirm here, tune during Phase 4):

  | Signal | Source | Bar (default) |
  |--------|--------|---------------|
  | Repeated deny signature | deny ledger `reason_head`+`denied_sha12` | ≥3 same-signature entries in 24h |
  | Process friction | ledger `kind: process-friction` `reason_head` | ≥2 same reason (any window) — bracket tears are never routine |
  | Hook fail-OPEN errors | events file `kind: error` per hook | ≥2 same hook in 7d |
  | Hook-level denies (post-D2) | events file `kind: deny` per hook+signature | ≥3 same cluster in 24h |

  Plus a per-scan enqueue cap (≤2 new stubs per scan, highest-recurrence first) so a pathological
  burst cannot flood the queue. Alternative shapes: a single global bar (simpler, but a bracket
  tear and a noisy deny genuinely differ in seriousness); no cap (trusts dedup alone).
- **Recommendation:** the table + cap as defaults. Thresholds live in one config block at the top
  of the script (numbers, not judgment) so tuning is a one-line diff. `acked` deny entries still
  count toward recurrence: an acked deny means a hardening round was *routed*, and recurrence
  after that is precisely the "hardening didn't stick" incident worth a bug.
- **Resolution:** OPEN — recommendation is the table + ≤2/scan cap; awaiting operator
  confirmation.

### D4. Clustering key + slug derivation

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** What makes two events "the same incident", and what slug does a cluster get?
- **Options:** cluster key = `(repo_key, signal_class, signature)` where signature is per-class:
  deny → `denied_sha12` + the first deny-signature token of `reason_head`; friction →
  `reason_head` (e.g. `cycle-bracket-break`) + optional `feature_id` from `detail`; hook
  error/deny → hook name + signature field. Slug = `adhoc-incident-<signal-class>-<short-hash>`
  with the human-readable cluster description in the enqueue `--name`/`--brief`. Alternatives
  (free-text similarity, LLM grouping) violate the deterministic constraint.
- **Recommendation:** as above — pure string composition over fields the artifacts already carry,
  so the same cluster always derives the same key and slug (idempotent scans).
- **Resolution:** Auto-accepted; internal derivation with no operator-visible alternative worth a
  round-trip.

### D5. Dedup mechanics + regression-reopen policy

- **Classification:** `product-behavior (OPEN — operator confirmation required via the pipeline's
  needs-input round before implementation)` — the *policy* half; the mechanics are mechanical.
- **Question:** Mechanics (auto-accepted): every enqueued stub's `INCIDENT.md` carries
  `incident_key: <cluster key>` in frontmatter; the collector dedups by scanning
  `docs/bugs/*/INCIDENT.md` AND `docs/bugs/_archive/*/INCIDENT.md` (plus `queue.json` ids) for
  the key before enqueueing — deterministic, survives renames of nothing (keys, not paths). The
  OPEN half: what happens when a cluster recurs after its bug was **fixed and archived**?
- **Options:**
  - **A — new slug carrying `recurrence_of: <archived-slug>`:** the archived record stays
    immutable (archive-on-fix is a completed receipt trail); the new stub's capsule links the
    prior investigation so `/spec-bug` starts warm. Matches `docs/bugs/CLAUDE.md`'s
    append-only spirit.
  - **B — suppress (archived key = permanently handled):** silently masks regressions — the worst
    outcome for a self-hardening harness.
  - **C — re-open the archived dir:** mutates the archive and confuses the bug pipeline's
    exhaustion logic (`_archive/` is skipped by design).
- **Recommendation:** A. B hides exactly the signal ("the fix didn't hold") this feature exists to
  surface; C breaks the archive contract.
- **Resolution:** OPEN — recommendation is A; awaiting operator confirmation.

### D6. Run cadence

- **Classification:** `product-behavior (OPEN — operator confirmation required via the pipeline's
  needs-input round before implementation)`
- **Question:** When does the collector run?
- **Options:**
  - **A — end-of-run orchestrator step + on-demand skill:** the `/lazy-batch` family runs
    `incident-scan.py` once at the end-of-run flush (alongside the existing deferred-features
    flush, before `--run-end`), and a thin `/incident-scan` skill runs it on demand. Pros: fires
    exactly when fresh evidence exists; zero standing infrastructure; the enqueue lands at the top
    of the bug queue for the *next* run. Cons: a repo with no batch runs only gets on-demand
    scans; touches the coupled orchestrator pair (mirror + parity discipline).
  - **B — scheduled (cron/Routine):** catches idle-repo drift, but standing schedules are the
    `scheduled-autonomous-runs` sibling's domain; duplicating that machinery here is scope creep.
  - **C — on-demand only:** simplest; relies on the operator remembering — the exact failure mode
    (evidence evaporating between retros) this feature fixes.
- **Recommendation:** A for v1; if `scheduled-autonomous-runs` ships, a scheduled scan is a
  one-line addition to its run template rather than machinery here.
- **Resolution:** OPEN — recommendation is A; awaiting operator confirmation.

### D7. Enqueue behavior — stub-status, evidence capsule, announce line

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** What exactly does a bar-clearing cluster produce? (The auto-enqueue direction and
  "/spec-bug owns root cause" are operator-locked in the stub.)
- **Options:** the collector shells the sanctioned path —
  `python3 ~/.claude/scripts/lazy-state.py --enqueue-adhoc --type bug --id <slug> --name <title>
  --brief <one-paragraph cluster summary>` — then atomically writes `INCIDENT.md` into the seeded
  `docs/bugs/<slug>/`: frontmatter `kind: incident-capture`, `incident_key`, `signal_class`,
  `occurrences`, `window`, `first_ts`/`last_ts`, `recurrence_of` (when D5-A applies); body = the
  raw matching ledger/event lines (verbatim excerpts, capped) so the investigation starts from
  evidence. One announce line per enqueue (the adhoc-enqueue component's format). The stub enters
  the queue as an ordinary ad-hoc bug: `/spec-bug` investigates root cause; the collector never
  writes a SPEC, never sets severity beyond the enqueue default, never acks deny-ledger entries
  (acks belong to the guard/orchestrator hardening loop — the collector is not a debt consumer).
- **Recommendation:** as above; reusing `enqueue_adhoc` end-to-end means idempotency (duplicate id
  → no-op) and queue-file atomicity are inherited, not reimplemented.
- **Resolution:** Auto-accepted; the operator locked the direction — this fixes the file shapes.

### D8. Relationship to `/lazy-batch-retro` and the hardening loop

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** How does this avoid double-reporting with the retro and the routed-hardening-debt
  machinery (`pending_hardening` / `--emit-dispatch hardening`)?
- **Options / boundaries:** the collector is an **earlier, shallower feeder**: it packages
  recurrence evidence into stubs; the retro remains the deep grading pass and may cite the same
  ledger entries. The hardening loop consumes *individual* unacked denies within a run; the
  collector consumes *patterns* across runs — an acked-but-recurring signature is its core
  signal, not a conflict (see D3). Dedup (D5) prevents the retro and the collector from opening
  two slugs for one incident: whichever writes the `incident_key` first wins, and the retro is
  encouraged (retro-side, later) to check `INCIDENT.md` keys before enqueueing spin-offs.
- **Recommendation:** as above — feeder-not-replacement is operator-locked; the boundary
  definitions are internal.
- **Resolution:** Auto-accepted; restates the stub's locked relationship with mechanical edges.

## User Experience

### End-of-run (per D6 outcome)

```
$ python3 ~/.claude/scripts/incident-scan.py --repo-root .
incident-scan: 4 clusters observed, 1 cleared the bar, 1 enqueued, 0 deduped
➕ Enqueued ad-hoc bug **Repeated deny: LONG-BUILD-OWNERSHIP-TAKEOVER (5×/24h)**
   (`adhoc-incident-deny-3f9a2c`) at the top of the bugs queue
```

`--dry-run` prints the same report with `would-enqueue` instead of writing anything. A scan with
nothing above the bar prints the one summary line and exits 0 (empty state is normal, not an
error).

### What the operator finds in the queue

`docs/bugs/adhoc-incident-deny-3f9a2c/` containing `ADHOC_BRIEF.md` (the enqueue seed) and
`INCIDENT.md`:

```markdown
---
kind: incident-capture
incident_key: claude-config|deny|3f9a2c-LONG-BUILD-OWNERSHIP-TAKEOVER
signal_class: deny
occurrences: 5
window: 24h
first_ts: 2026-07-03T21:14:09Z
last_ts: 2026-07-04T14:02:51Z
---

# Incident Evidence

Raw deny-ledger lines (verbatim, newest last):
{"ts": ..., "denied_sha12": "3f9a2c...", "reason_head": "LONG-BUILD-OWNERSHIP-TAKEOVER ...", ...}
...
```

The next bug-pipeline probe routes the stub to `/spec-bug`, which investigates root cause with the
evidence already in the dir. If the operator disagrees with a capture, the stub is removed like
any queue item (`bug-state.py --reorder-queue --id <slug> --to remove`) — the collector will not
re-enqueue it while the dir (and its `incident_key`) exists.

## Technical Design

```
 signal sources (read-only)                     collector (stdlib, deterministic)        sanctioned writes
 ~/.claude/state/<repo_key>/
   lazy-deny-ledger.jsonl  ──read_deny_ledger─▶  cluster by (repo_key, class,   ──▶  lazy-state.py --enqueue-adhoc
   hook-events.jsonl (D2)  ──read─────────────▶  signature) → recurrence bar          --type bug (subprocess)
   hook-error.json         ──read─────────────▶  (D3) → dedup vs incident_key   ──▶  docs/bugs/<slug>/INCIDENT.md
 docs/bugs/**/INCIDENT.md  ──dedup scan───────▶  scan (D5) → cap → enqueue           (atomic write, evidence capsule)
 (incl. _archive/)                               │
                                                 └─ --dry-run: report only, zero writes
```

- **Honors the house invariants:** read-only miner over state dirs + logs (the `toolify-miner.py`
  contract — Phase tests hash the input dirs before/after a scan); every direct write is
  `lazy_core._atomic_write`-equivalent and there are exactly two (capsule + the enqueue's own
  atomic queue write, which is `bug-state.py`'s, not ours); per-repo keyed state dir addressed via
  the same resolution the hooks use; stdlib-only; thresholds are config constants, never
  LLM-inferred; fail-OPEN preserved at every D2 hook site (append failure changes nothing).
- **Not on the compute path:** neither state script imports the collector; a broken collector can
  never mis-route the pipeline.
- **D2 appender:** a small shared shell/Python snippet (pattern: the hooks' existing inline
  `_breadcrumb`) appending one JSON line, `try/except`-swallowed. Hook edits are additive lines at
  existing error/deny sites; `test_hooks.py` pipe-tests assert deny/allow outputs are
  byte-unchanged with the appender failing and succeeding.
- **Idempotency:** same inputs → same clusters → same slugs; an existing `incident_key` (open or
  archived) short-circuits before any write; `enqueue_adhoc`'s duplicate-id no-op is the second
  net.
- **Cloud note:** cloud runs have their own state dirs; v1 scans the workstation's dirs only
  (cloud friction still reaches the ledger the orchestrator runs against). Revisit under the
  telemetry-ledger migration (soft dep).

## Implementation Phases

- **Phase 1 — Event persistence (D2).** Shared fail-open appender; wire into the deny/error sites
  of `lazy-cycle-containment.sh`, `block-noncanonical-blocker-write.sh`,
  `block-sentinel-write-on-stray-branch.sh`, `long-build-ownership-guard.sh`,
  `build-queue-enforce.sh`, `lazy_guard.py`. Proven by `test_hooks.py`: deny/allow outputs
  byte-unchanged; events appended on deny/error; append failure swallowed.
- **Phase 2 — Collector core.** `incident-scan.py`: readers, clustering (D4), recurrence bars
  (D3 defaults), dedup scan (D5 mechanics), `--dry-run` report. Proven by pytest fixtures: seeded
  ledgers/events produce expected clusters; inputs hashed before/after (read-only); below-bar and
  deduped clusters never propose.
- **Phase 3 — Enqueue integration (D7).** Sanctioned enqueue subprocess + `INCIDENT.md` capsule +
  cap + announce lines; `recurrence_of` per the D5 outcome. Proven by: end-to-end fixture run
  yields a queued stub with correct capsule; second run is a no-op; removed-then-recurring
  behavior matches the confirmed policy.
- **Phase 4 — Wiring + tuning.** End-of-run step in the batch orchestrators (coupled-pair mirrors
  + parity audit) and/or `/incident-scan` skill per the D6 outcome; run against real accumulated
  ledgers; tune D3 thresholds from observed noise. Proven by: a real run's flush produces a scan
  report in the run log; false-positive review of the first captures.

Estimate: ~3 sessions (Phases 1-2 one; 3 one; 4 one).

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| Hook outputs unchanged by D2 | Pipe-test each edited hook pre/post | Byte-identical deny/allow JSON; event line appended | `test_hooks.py` |
| Appender is fail-open | Unwritable events file during a deny | Deny still emitted; no exception | `test_hooks.py` fixture |
| Collector is read-only | Scan over seeded state dir | Input dir hash unchanged (except sanctioned writes) | pytest before/after hash |
| Recurrence bar holds | 2 same-signature denies in window (bar 3) | No proposal | pytest fixture |
| Bar clears → stub | 3+ same-signature denies | Queue head = new stub; `INCIDENT.md` capsule correct | pytest + manual queue read |
| Dedup vs open slug | Re-scan with stub present | No second enqueue (`incident_key` hit) | pytest |
| Dedup vs archived slug | Key present only in `_archive/` | Behavior per D5 outcome (`recurrence_of` stub) | pytest |
| Enqueue cap | 5 bar-clearing clusters, cap 2 | 2 enqueued (highest recurrence), 3 reported-only | pytest |
| Dry-run inert | `--dry-run` on bar-clearing state | Report printed; zero file mutations | pytest |
| /spec-bug pickup | Next bug-pipeline probe after enqueue | Stub routes to `/spec-bug` with brief + capsule readable | manual pipeline run |

## Open Questions

- **D3 — signal inventory + recurrence bars:** confirm the four v1 signal classes, the per-signal
  thresholds/windows, and the ≤2-per-scan enqueue cap. Standing recommendation: the D3 table as
  defaults, thresholds as top-of-script config.
- **D5 — regression-reopen policy:** when a cluster recurs after its bug was fixed and archived —
  new stub with `recurrence_of:` vs suppress vs re-open the archive. Standing recommendation: new
  stub carrying `recurrence_of:` (never suppress a failed fix; never mutate the archive).
- **D6 — cadence:** end-of-run orchestrator step + on-demand `/incident-scan` skill vs scheduled
  vs on-demand only. Standing recommendation: end-of-run + on-demand; defer scheduling to
  `scheduled-autonomous-runs`.
- Deferred empirical checks (implementation, not decisions): real false-positive rate of the
  default bars over the first weeks of ledger history (Phase 4 tuning); whether the un-keyed
  base-dir breadcrumbs carry enough volume to matter or the events file makes them redundant;
  capsule excerpt cap size.

## Research References

- `RESEARCH.md` — internal desk research (Gemini deep research intentionally skipped by operator
  directive, 2026-07-04). Key influences: the deny-ledger/friction-detector loop as the existing
  half of this design; crash-reporter auto-filing (fingerprint dedup, recurrence thresholds) as
  external prior art.
- `user/scripts/lazy_core.py` — `append_deny_ledger_entry` / `append_friction_ledger_entry` /
  `read_deny_ledger` / `pending_hardening` / `detect_cycle_bracket_friction`.
- `user/scripts/lazy_guard.py` `_write_breadcrumb`; the inline `_breadcrumb` writers in
  `user/hooks/lazy-cycle-containment.sh`, `build-queue-enforce.sh`,
  `long-build-ownership-guard.sh`.
- `_components/adhoc-enqueue.md` + `bug-state.py::enqueue_adhoc` — the sanctioned enqueue path.
- Siblings: `harness-telemetry-ledger` (soft dep — future event substrate);
  `friction-kpi-registry` (measures friction systems; this feature's capture counts are natural
  KPI inputs); `/lazy-batch-retro` (the deep-analysis pass this feeds, not replaces).
