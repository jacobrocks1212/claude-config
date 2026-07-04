# Research — Incident Auto-Capture → Bug Stubs

**Status: Gemini deep research intentionally skipped (operator directive, 2026-07-04).** This
feature was fleshed out via internal desk research instead: a survey of the in-repo prior art it
builds on, plus prior-art knowledge of comparable external systems. This file is the canonical
"research satisfied" marker for this repo (direct RESEARCH.md drop, per claude-config/CLAUDE.md),
so the pipeline routes Step 5 → /spec Phase 3 (integrate research + finalize) — which surfaces the
SPEC's OPEN product-behavior decisions to the operator via NEEDS_INPUT.md before planning starts.

## In-repo prior art

- **Half the design already exists as the routed-hardening-debt loop.** `lazy_guard.py` appends
  every dispatch deny to `lazy-deny-ledger.jsonl` (`append_deny_ledger_entry`); the `--cycle-end`
  friction detector (`detect_cycle_bracket_friction` → `append_friction_ledger_entry`) appends
  `kind: process-friction` entries for bracket tears, unexpected commits, and branch divergence;
  `pending_hardening()` counts unacked entries and the probe withholds the forward route until
  the debt is retired via `--emit-dispatch hardening`. That loop handles *individual events
  within a run*. What is missing — and what this feature adds — is the *pattern* layer: the same
  signature recurring across runs (including after an ack) currently reaches a bug slug only if a
  retro notices.
- **Signal-persistence inventory (verified against the actual writers).**
  - `hook-error.json`: `lazy-cycle-containment.sh`, `build-queue-enforce.sh`, and
    `long-build-ownership-guard.sh` each carry an inline `_breadcrumb(err)` writing
    `{hook, error, at}` with `open(..., "w")`; `lazy_guard.py::_write_breadcrumb` writes the same
    shape via `write_text`. Uniform shape — but single-file overwrite (recurrence uncountable)
    and split residency: the bash hooks deliberately target the un-keyed base
    `~/.claude/state/` (comment in `lazy-cycle-containment.sh`: "the breadcrumb ... stays at the
    base — it never needs repo-keying") while `lazy_guard.py` uses the keyed
    `claude_state_dir()`.
  - Hook-level denies: a `grep -l append_deny_ledger` across `user/hooks/*.sh` + the guard
    scripts hits ONLY `lazy_guard.py`. Containment trips, noncanonical-blocker denies,
    stray-branch denies, build-queue redirects, and long-build takeovers emit PreToolUse deny
    JSON and persist nothing. This is the concrete gap behind SPEC D2 — without it, most of the
    stub's named signals are unobservable.
- **The read-only-miner precedent.** `toolify-miner.py` establishes the collector's discipline:
  stdlib-only, READ-ONLY over logs (tests hash the fixture dirs before/after), ranks and
  *proposes*; the consequential act (promotion there, enqueue here) is separate and deliberate.
- **The sanctioned enqueue path.** `_components/adhoc-enqueue.md` +
  `bug-state.py::enqueue_adhoc`: prepend to `docs/bugs/queue.json` (atomic, duplicate-id no-op),
  seed `docs/bugs/<slug>/` + `ADHOC_BRIEF.md`, and the stub flows through `/spec-bug` →
  `/plan-bug` → fix → `__mark_fixed__` untouched. The collector inherits idempotency and
  atomicity by shelling this path instead of reimplementing it.
- **Dedup surface.** `docs/bugs/CLAUDE.md` + `bug-state.py`: open bugs are one-level dirs under
  `docs/bugs/` (auto-discovered), fixed bugs move to `docs/bugs/_archive/` (39 archived dirs
  today, all with `FIXED.md`). Scanning both for an `incident_key` frontmatter marker gives
  deterministic dedup against open AND concluded work.
- **Retro relationship.** `/lazy-batch-retro` (+ `audit-table-validator.md`) is the deep grading
  pass; the root `CLAUDE.md` mission text ("friction observed in a run is a bug report against
  this repo") is the operator mandate this feature mechanizes for the between-retro window.

## External prior art & concepts

(Training-knowledge survey, not live research.)

- **Crash reporters that auto-file bugs.** Mozilla Socorro and Google ClusterFuzz are the direct
  analogs: crashes are fingerprinted (signature = normalized stack head), grouped, and a bug is
  auto-filed only when a signature clears volume thresholds AND no existing open/closed bug
  carries the fingerprint; regressions after a fix file a NEW bug linked to the old one.
  ClusterFuzz's dedup-against-closed-issues + "reopen as new, link the old" behavior is the model
  for SPEC D5-A.
- **Alert grouping and flap suppression (Prometheus Alertmanager, PagerDuty, Sentry).**
  Fingerprint-based grouping keys, time-windowed thresholds, and rate caps are the standard
  answer to "one-off blip ≠ incident". Sentry's issue-grouping (deterministic fingerprint first,
  fuzzy only as opt-in) supports keeping the clustering key pure string composition (SPEC D4).
- **SRE practice: page on persistent symptoms, ticket the rest.** The recurrence bar maps to the
  classic Rob-Ewaschuk guidance — transient self-healing events become logs/tickets, only
  sustained patterns escalate. Here "escalate" = a stub in the bug queue, deliberately the
  lowest-ceremony artifact the pipeline has.
- **Test-flake detectors (Chromium/LUCI flake portal, GitHub flaky-test bots).** Same shape:
  deterministic recurrence counting over structured logs, auto-filing with dedup, humans own root
  cause. Their main documented failure mode — threshold too low → bug-tracker spam → humans
  ignore the bot — is the pitfall driving the per-scan cap and the OPEN status of the thresholds.

## Alternatives analysis

- **Collector placement (D1).** Standalone script vs state-script fold-in vs hook. The state
  scripts are the wrong home: the collector is cross-run analysis, not dispatch computation, and
  a fold-in would demand coupled-pair mirroring for un-pipelined logic. A hook is per-event and
  fail-OPEN — structurally unable to do windowed counting. The standalone read-only miner has a
  direct precedent (`toolify-miner.py`) and keeps blast radius at zero (nothing imports it).
- **Persistence gap (D2).** Read-only-what-exists vs additive events file vs hook rewrite.
  Reading only what exists silently drops containment trips and sentinel denies — the stub's
  highest-value signals — and the single overwritten breadcrumb cannot support recurrence at all.
  A rewrite of six load-bearing fail-OPEN guards for logging is disproportionate risk. The
  additive appender copies the deny ledger's proven contract (append-only, swallow errors,
  corrupt-line-tolerant reader) and leaves `hook-error.json` byte-identical, making the change
  testable as "outputs unchanged + one extra line appended".
- **Recurrence bars (D3).** Global bar vs per-signal bars. A bracket tear (integrity break) and a
  repeated deny (possibly one stubborn subagent) are not equally alarming; per-signal thresholds
  cost four config lines. Counting acked entries is deliberate: an acked-then-recurring signature
  is the "hardening didn't stick" case that most deserves a bug. The cap (≤2/scan) is the
  bot-spam lesson from flake-detector prior art.
- **Dedup key (D5 mechanics).** `incident_key` frontmatter in the seeded dir vs a collector-side
  state file mapping keys → slugs. The frontmatter travels WITH the bug (survives archive,
  visible to `/spec-bug`, greppable by hand); a side state file is machine-local, invisible, and
  one more thing to rot. Chosen: frontmatter.
- **Cadence (D6).** End-of-run vs scheduled vs on-demand. End-of-run matches when evidence is
  fresh and requires no standing infrastructure; scheduling belongs to the
  `scheduled-autonomous-runs` sibling (a scan is then one line in its run template). On-demand
  alone recreates the human-memory dependency the feature exists to remove.

## Pitfalls & risks

- **Noise flooding the bug queue.** The failure mode that kills every auto-filer. Mitigations are
  layered: recurrence bars, dedup (open + archived), the per-scan cap, and stub-status (a bad
  capture costs one `/spec-bug` glance, not a pipeline run). Falsifiability: track
  captures-closed-as-not-a-bug vs captures-that-led-to-fixes; if the false-positive fraction
  stays high after Phase 4 tuning, the bars are wrong or the feature is dead weight — the counts
  are trivially computable from `INCIDENT.md` frontmatter vs archive outcomes (and are natural
  `friction-kpi-registry` rows if that sibling ships).
- **Hook regression risk (Phase 1).** Any edit to the fail-OPEN guards can break deny/allow
  behavior. Contained by: additive-only appender calls at existing sites, the swallow-everything
  contract, and `test_hooks.py` byte-comparison of hook outputs with the appender both working
  and failing.
- **Double-reporting with the hardening loop / retro.** The collector consumes patterns, the
  hardening loop consumes individual unacked denies, the retro grades runs; dedup keys prevent
  two slugs for one incident. The collector must NEVER ack ledger entries — acks are the
  guard/orchestrator's; violating this would silently drain `pending_hardening` and disarm the
  probe's withholding.
- **Operator-removed stubs re-appearing.** Handled: dedup is keyed on the on-disk `incident_key`,
  so a removed-but-still-present dir suppresses re-enqueue; a fully deleted dir means the
  operator wants it gone — and a later recurrence legitimately re-proposes (documented behavior,
  not a bug).
- **Cloud blind spot.** Cloud-run state dirs aren't scanned in v1; friction that only manifests
  in cloud runs still surfaces via the orchestrator-side ledger, but with lower fidelity. Noted
  in the SPEC; the telemetry-ledger soft dep is the structural fix.

## Recommendations summary

| Decision | Recommendation | Confidence |
|----------|----------------|------------|
| D1 collector shape | Standalone read-only `incident-scan.py`; writes only via sanctioned enqueue + capsule | High (auto-accepted) |
| D2 persistence normalization | Additive fail-open `hook-events.jsonl` appender; `hook-error.json` unchanged; migration note recorded | High (auto-accepted) |
| D3 signals + bars | Four signal classes with per-signal thresholds + ≤2/scan cap, as config constants | Medium (OPEN — thresholds are the operator's noise budget) |
| D4 clustering key | `(repo_key, signal_class, signature)` string composition; deterministic slug | High (auto-accepted) |
| D5 dedup + regression policy | `incident_key` frontmatter scan incl. `_archive/`; recurrence after fix → new stub with `recurrence_of:` | Medium-high (mechanics high; policy OPEN) |
| D6 cadence | End-of-run orchestrator step + on-demand skill; no scheduling in v1 | Medium (OPEN) |
| D7 enqueue shape | Sanctioned `--enqueue-adhoc --type bug` + `INCIDENT.md` evidence capsule; never acks the ledger | High (auto-accepted) |
| D8 retro relationship | Earlier feeder; retro stays the deep pass; dedup arbitrates | High (auto-accepted, operator-locked) |
