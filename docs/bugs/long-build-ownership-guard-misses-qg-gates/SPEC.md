# Bug: long-build-ownership guard does not redirect the heavy qg quality gates

**Status:** Concluded
**Reported via:** `/harden-harness` observed-friction dispatch (2026-07-17, item in flight `hydra-overlay`, AlgoBooth `/lazy-batch` execute-plan part 6, blocking=true)
**Root-cause class:** `missing-contract` (the enforcement layer under an already-advised rule)
**Related:** `docs/specs/turn-routing-enforcement/` (hardening stage); `user/hooks/long-build-ownership-guard.sh`; `repos/algobooth/.claude/skill-config/long-build-ownership.md`; `user/skills/lazy-batch/SKILL.md` Step 1d; hardening-log Round 45 (`cycle-subagent-over-cap-aggregate-gate-auto-backgrounds` — the PROSE layer this round enforces).

## Symptom (verified)

On the `hydra-overlay` `/execute-plan` part-6 run, cycle subagents ran the AlgoBooth heavy
quality gates to verify a work-unit before committing:

- `qg-rust` = `npm run qg -- rust` — queue-routed Rust build + clippy + fmt + test (~5-10 min).
- `qg-ts` = `npm run qg -- ts` — vue-tsc + eslint + vitest + vite build (~4-6 min).

Both exceed a single subagent turn, so the subagent backgrounded the gate and then yielded its
turn. The subagent process tree is torn down at the turn boundary:

- the backgrounded `qg-ts` (a bare `npm`/vite process) simply DIES, leaving no artifact;
- the `qg-rust` queue wrapper is reaped, ORPHANING the underlying `cargo` process and leaving a
  stale `active.lock` in the machine-global build queue;
- the subagent transcript is reaped (unresumable — `SendMessage` returns "No transcript found").

Net: a gate-PASSING work-unit is left UNCOMMITTED, and the orchestrator must manually wait out
the orphaned `cargo`, clear the stale lock, and re-run the gates orchestrator-owned. **Observed
live TWICE this run.**

The `long-build-ownership-guard.sh` PreToolUse(Bash) hook exists precisely to redirect this class
of self-terminating background build to ORCHESTRATOR ownership — but its matcher `_LONG_BUILD_RE`
covers only `tauri build` / `cargo build --release` / `npm run build`. The qg gate commands walk
straight past it, so no takeover signal fires and the subagent is free to background them.

**Cost:** per-occurrence orphaned `cargo` + stale lock + a lost work-unit commit + an
orchestrator-owned gate re-run. Blocking (orchestrator awaited the foreground harden).

## Root cause

**`missing-contract` — the enforcement layer for an already-advised rule was absent.** Round 45
(`cycle-subagent-over-cap-aggregate-gate-auto-backgrounds`) added PROSE telling the cycle subagent
to decompose an over-cap aggregate gate and never background a long gate. Prose is advisory; the
request-time GUARD that makes the rule un-bypassable enumerates only the three packaged-build
signatures. The heavy qg gates are long builds/tests by the SAME definition (exceed a subagent
turn; die identically when backgrounded from a subagent) but were never added to the guard's
signature set, nor to the SKILL.md Step 1d guard-takeover enumeration, nor to the AlgoBooth
`long-build-ownership.md` doc.

Two sub-facts distinguish the two commands:

- `qg-rust` (and `qg-sidecar`) ARE registered in `repos/algobooth/.claude/skill-config/build-queue-ops.json`
  as heavy queue ops — so `_queue_routing_hint` already fires for them (it reads that manifest);
  the guard just never DENIED them for ownership.
- `qg-ts` is NOT in the manifest (it is not queue-serialized — no cargo target-lock contention,
  no filtered script), so a purely manifest-driven ownership check would miss it. It still needs
  orchestrator ownership.

## Fix scope

Extend `_LONG_BUILD_RE` in `long-build-ownership-guard.sh` with an enumerated arm
`npm\s+run\s+(?:qg|quality-gate)\s+--\s+(?:rust|ts|sidecar)(?:\s|$)` (heavy targets only — the
fast `arch`/`docs`/`lint` groups and a bare `npm run qg` are deliberately NOT matched, preserving
the guard's near-zero-false-positive charter D1). The existing `_queue_routing_hint` fires
unchanged for qg-rust/qg-sidecar (manifest ops) and correctly stays silent for qg-ts. Mirror the
signature into the deny message, the guard header RULE comment, the SKILL.md Step 1d
guard-takeover paragraph, and the AlgoBooth `long-build-ownership.md` doc. Add hook tests
(deny qg-rust/qg-ts/qg-sidecar + `quality-gate` alias + cd-prefixed; allow the fast qg groups /
bare qg / `ts-foo`).

**Known over-fit (recorded, spun off — not blocking):** enumerating `rust|ts|sidecar` in the
generic guard DUPLICATES the heavy-op SSOT that already lives in `build-queue-ops.json` for
qg-rust/qg-sidecar; the next heavy qg target would gap again. The durable generalization —
making the ownership guard manifest-driven (with an ownership-only op marker so qg-ts joins the
manifest instead of a hardcoded guard signature) — is front-enqueued as a `/spec-bug` and does
not block this fix.
