---
kind: adhoc-brief
feature_id: generalized-build-test-runner-skills
enqueued_by: lazy-adhoc
date: 2026-07-13
---

# Ad-hoc task: Generalized build/test runner skill system

Operator-requested 2026-07-13 (interactive session, mid `lazy-core-package-decomposition` run):
generalize the Cognito Forms build/test skill system to claude-config and AlgoBooth. **The
Cognito system is working well and must not break** — additive generalization only.

## Motivating friction (observed live, same session)

Execution subagents running claude-config's 7-command invariant battery (~4–5 min) hand-rolled
it, backgrounded it, and repeatedly ended their turn before the result — the exact class the
Cognito skills closed with the authoritative last-line banner + `build-queue-await.ps1` +
the §4 turn-end gate (now generalized as `_components/turn-end-gate.md`, Round 39). The battery
has no single-command runner, no authoritative outcome line, no followable await.

## The reference architecture (Cognito — keep working)

- `user/scripts/build-queue.ps1` — machine-global FIFO serializer, manifest-driven
  (`.claude/skill-config/build-queue-ops.json` per repo: `{op: {exec, kind, hygiene, skill,
  deny, lane}}`).
- Authoritative LAST-stdout-line banner (`Format-BuildQueueBanner`:
  `build-queue: seq=N op=X RESULT=PASS|FAIL ...`) — agents trust it, never grep runner logs.
- `build-queue-await.ps1` — followable wait; exit 124 = not-done-yet (NEVER success), 125 =
  malformed.
- `user/hooks/build-queue-enforce.sh` — manifest-scoped deny of raw invocations; segment-start
  anchored; `BUILD_QUEUE_BYPASS=1` override; Cognito legacy fallback (locked D4).
- Thin per-repo skills (`/msbuild`, `/mstest`, `/nxbuild`, `/nxtest`; AlgoBooth `/tauri-build`,
  `/cargo-release`) carrying the §4 turn-end contract.

## Ground truth per target repo (verified on this box, 2026-07-13)

**This box is `DESKTOP-GHTC5K6`** (personal workstation; see
`C:\Users\Jacob\algobooth-windows-native-setup.md`). Note the stale workspace-CLAUDE.md claim
that AlgoBooth is cloud-only — **AlgoBooth IS checked out natively here.**

### claude-config (`C:\Users\Jacob\source\repos\claude-config`)

- Gate surface = the 7-command battery: `python -m pytest user/scripts/ -q`,
  `lazy-state.py --test`, `bug-state.py --test`, `lazy_parity_audit.py --repo-root .`,
  `cli_surface_gen.py --check --repo-root .`, `doc-drift-lint.py --repo-root .`,
  `lint-skills.py`. No runner script, no banner, no skill, no manifest.
- Contention profile: light (pure CPU, no shared compiler state, no artifact hygiene);
  concurrent batteries ran fine all session → machine-global serialization is probably NOT the
  needed piece; the banner/await/turn-end contract is.

### AlgoBooth (`C:\Users\Jacob\repos\AlgoBooth` — NON-standard path, not under ~/source/repos)

- Already manifested: `tauri-build` + `cargo-release` (heavy lane, `rust-tauri` hygiene).
- Test/gate surface NOT covered: `npm run qg -- {ts|rust|sidecar|docs}` (composite quality
  gate; rust/sidecar gates compile → legitimately heavy) plus e2e/vitest surfaces.
- `qg` already emits an authoritative final line: `QG_VERDICT: PASS` / `QG_VERDICT: FAIL
  (exit N)` (see `.claude/skill-config/quality-gates.md`, incl. the never-pipe-through-tail
  rule) — i.e. AlgoBooth already has the banner half; missing: queue routing for the heavy
  gates, thin skills, await coverage, deny enforcement.

## Design forks for /spec (do not decide in the brief)

1. **Serialize vs banner-only per op class:** light ops (claude-config battery, qg -- ts/docs)
   may want a runner+banner WITHOUT queue admission; heavy ops (qg -- rust/sidecar, cargo test)
   plausibly join the existing queue. Manifest could grow a `lane`/`kind` value for
   "unserialized" ops — or light ops skip the manifest entirely.
2. **Enforcement:** does raw `pytest user/scripts/` / raw `npm run qg` get hook-denied like raw
   msbuild? False-deny cost is real (see the guard false-deny bug class, 3 variants). Maybe
   enforcement only for heavy ops; advisory for light.
3. **Runner language for claude-config:** the queue plane is PowerShell; claude-config gates
   are Python and must also run in cloud sessions (build-queue is workstation-only by locked
   D7). A cross-platform Python runner emitting the banner (mirroring `Format-BuildQueueBanner`
   format) may serve both; decide the seam.
4. **Banner contract as a shared component:** formalize "authoritative last-line banner +
   followable await + turn-end gate" as ONE documented contract (component or
   `user/scripts/CLAUDE.md` section) that all three repos' skills instantiate — the
   generalization deliverable, distinct from the per-repo ops.
5. **AlgoBooth path discovery:** fleet/queue tooling that globs `~/source/repos/*` will miss
   `C:\Users\Jacob\repos\AlgoBooth`; verify per-repo keying (hooks key on payload cwd git
   toplevel — fine) and note `~/.claude/lazy-repos.json` pinning if needed.

## Constraints

- Cognito Forms manifests/skills/hooks: byte-untouched unless provably additive; its Pester
  suites + the enforce hook's legacy fallback must stay green.
- `build-queue-enforce.sh` is manifest-scoped — new repos opt in via their own
  `build-queue-ops.json`; a manifest-less repo stays unaffected (preserve this property).
- The §4 turn-end gate now lives canonically in `_components/turn-end-gate.md` (Round 39) —
  new skills reference it, never copy it.
