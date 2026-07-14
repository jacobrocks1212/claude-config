# Generalized Build/Test Runner Skills — Feature Specification

> Generalize the Cognito build/test skill system's outcome contract — authoritative last-line
> banner + followable await + turn-end gate — to claude-config's 7-command gate battery and
> AlgoBooth's heavy `qg` quality gates, as ONE documented contract instantiated per repo.
> Additive only: the working Cognito system is byte-untouched.

**Status:** Draft — baseline locked 2026-07-13 (D2/D3/D4 adopted PARK-PROVISIONAL, ratification pending; see `NEEDS_INPUT_PROVISIONAL.md`)
**Priority:** P1
**Last updated:** 2026-07-13
**Friction-reduction feature:** yes

**Depends on:**

- build-queue-generalization — hard — this feature extends the concrete contracts it locked: the per-repo `build-queue-ops.json` manifest schema (op entries + per-op `deny`), the `build-queue.ps1` wrapper composition seam, the manifest-scoped `build-queue-enforce.sh`, and its locked D4 (Cognito legacy fallback) / D7 (workstation-only) decisions.
- build-queue-eta-priority-lanes — soft — new heavy AlgoBooth ops inherit the manifest `lane` field and ETA/stats mechanics; the design needs the lane surface to exist, not its internals.
- lazy-core-package-decomposition — hard — sequencing: the battery's pytest target layout (`user/scripts/` incl. `user/scripts/tests/test_lazy_core/`) is being settled by the in-flight decomposition (Phases 3–6); this feature executes only after it completes, and specs the battery runner against the stable 7-command contract, not today's file layout.

---

## Executive Summary

Cognito Forms' build/test skill system closed a recurring, expensive failure class: an execution
subagent backgrounds a build/test run, receives only an enqueue/launch echo, and **ends its turn
before the result exists** — stalling the run until a human resumes it (bug
`subagent-backgrounds-verification-ends-turn-before-green`, Fixed; generic recurrence
`generic-execution-surfaces-lack-turn-end-gate`, Concluded 2026-07-13 with 4 recurrences in one
orchestrated run). The Cognito closure has three legs: an **authoritative LAST-stdout-line
outcome banner** (`Format-BuildQueueBanner`, `user/scripts/build-queue-hygiene.ps1:2275`) that
agents trust instead of grepping runner logs; a **followable await**
(`user/scripts/build-queue-await.ps1` — exit 124 = not-done-yet, NEVER success; 125 = malformed)
that lets any later turn re-acquire the result; and the **turn-end gate**
(`user/skills/_components/turn-end-gate.md`, canonical since Round 39) that forbids ending a turn
on in-flight work.

The same failure class was observed live on 2026-07-13 in claude-config: subagents running the
repo's 7-command invariant battery (~4–5 min) hand-rolled it, backgrounded it, and repeatedly
ended their turn before the result. The battery has **no single-command runner, no authoritative
outcome line, and no followable await**. AlgoBooth is halfway there: its `npm run qg` wrapper
already emits an authoritative final `QG_VERDICT: PASS|FAIL (exit N)` line
(`.claude/skill-config/quality-gates.md`), but its compile-heavy gates (`qg -- rust`, `qg --
sidecar`) have no queue routing, no thin skills, no await coverage, and no deny enforcement.

This feature ships the generalization as **one documented contract** — the
**runner-outcome contract** (banner grammar + followable await + turn-end gate by reference) —
plus two per-repo instantiations: a **cross-platform stdlib-Python gate-battery runner** for
claude-config (cloud-compatible; the build queue is workstation-only by locked D7) and
**additive AlgoBooth manifest ops + thin skills** for the heavy `qg` gates (queue-routed through
the existing machine-global serializer). The Cognito system is the reference implementation and
is byte-untouched; a manifest-less repo stays unaffected.

## Ground Truth (verified on disk, 2026-07-13, box DESKTOP-GHTC5K6)

All brief claims re-verified this session:

| Claim | Evidence |
|-------|----------|
| Cognito reference pieces exist | `user/scripts/build-queue.ps1`, `build-queue-await.ps1` (exit 124 at line 99, 125 at lines 69/96/122), `Format-BuildQueueBanner` (`build-queue-hygiene.ps1:2275`, pure/side-effect-free), 5 Pester suites (`build-queue*.Tests.ps1`) |
| Enforce hook is manifest-scoped, fail-open | `user/hooks/build-queue-enforce.sh:12-26` — reads `<toplevel>/.claude/skill-config/build-queue-ops.json`; manifest-less repo allows everything; Cognito legacy fallback on missing/unparseable manifest; `BUILD_QUEUE_BYPASS=1` override (lines 146-147) |
| AlgoBooth already manifested for builds | `C:\Users\Jacob\repos\AlgoBooth\.claude\skill-config\build-queue-ops.json` — `tauri-build` + `cargo-release`, both `kind: build`, `hygiene: rust-tauri`, `lane: heavy`, with `deny` rows |
| AlgoBooth qg banner exists | `.claude/skill-config/quality-gates.md` — `QG_VERDICT: PASS` / `QG_VERDICT: FAIL (exit N)` final line + the never-pipe-through-tail rule |
| The 7-command battery | `docs/features/lazy-core-package-decomposition/plans/all-phases-lazy-core-package-decomposition-part-2.md` note 1: `python -m pytest user/scripts/ -q`; `lazy-state.py --test`; `bug-state.py --test`; `lazy_parity_audit.py --repo-root .`; `cli_surface_gen.py --check --repo-root .`; `doc-drift-lint.py --repo-root .`; `lint-skills.py` |
| Turn-end gate is canonical | `user/skills/_components/turn-end-gate.md` exists (Round 39); referenced, never copied |
| AlgoBooth path is non-standard | `C:\Users\Jacob\repos\AlgoBooth` (not under `~/source/repos`); `~/.claude/lazy-repos.json` does not exist on this box; hooks key on payload-cwd git toplevel, so per-repo keying is unaffected |
| Turn-end failure class is live | `docs/bugs/_archive/subagent-backgrounds-verification-ends-turn-before-green/` (Fixed, P1); `docs/bugs/generic-execution-surfaces-lack-turn-end-gate/` (Concluded, P1, 4 recurrences 2026-07-13) |

## User Experience (agent-facing)

The "users" are orchestrators and execution subagents.

**claude-config (and any repo that opts in via a battery manifest):**

```bash
# One command replaces the hand-rolled 7-command sequence:
python3 user/scripts/gate-battery.py --repo-root .
# ... runs each manifested gate, streams progress, and prints as its LAST stdout line:
# gate-battery: run=20260713-a1b2 op=battery RESULT=PASS cmds=7 failed=0 (elapsed=241s)
# gate-battery: run=20260713-a1b2 op=battery RESULT=FAIL cmds=7 failed=1 (elapsed=198s) -> first failing gate: doc-drift-lint

# Backgrounded? Follow to the result from any later turn:
python3 user/scripts/gate-battery.py --await 20260713-a1b2
# re-emits the SAME banner as its last line; exit = the run's own exit code
# exit 124 = result not yet present (NEVER success); exit 125 = malformed result
```

Thin skill `/gate-battery` wraps this, tells agents to trust the banner (never grep gate
output to disambiguate), and carries the turn-end gate **by reference** to
`_components/turn-end-gate.md`: a bare launch echo is not an outcome; a subagent may not end its
turn on an in-flight battery.

**AlgoBooth (heavy gates — workstation):**

```
/qg-rust      → build-queue.ps1 -Op qg-rust    (queue-routed; banner: build-queue: seq=N op=qg-rust RESULT=...)
/qg-sidecar   → build-queue.ps1 -Op qg-sidecar (same)
# await: the existing build-queue-await.ps1 -Seq <N> — unchanged, already generic
```

Light gates (`npm run qg -- ts|docs`) stay direct invocations: they already end with the
authoritative `QG_VERDICT:` line, and they are never hook-denied (D3).

**Cognito Forms:** no change. Its skills/manifest/hooks are the reference instantiation of the
same contract and are byte-untouched.

## Technical Design

### D1 — The runner-outcome contract (the generalization deliverable)

One documented contract at **`user/skills/_components/runner-outcome-contract.md`** (new
component), with a pointer row in `user/scripts/CLAUDE.md`. It specifies, surface-neutrally:

1. **Authoritative last-line banner.** Every conforming runner prints, as its LAST stdout line, a
   single machine-parseable outcome banner:
   `<runner>: <run-key> [op=<op>] RESULT=<PASS|FAIL|...> [counts] [(fidelity)] [-> next-action]`.
   Conforming instances: `build-queue: seq=<N> op=<op> RESULT=... [tests=<T> failed=<F>]
   (result_fidelity=...) [-> next-action]` (Cognito/AlgoBooth builds, existing), `QG_VERDICT:
   PASS|FAIL (exit N)` (AlgoBooth qg, existing — grandfathered verbatim; the contract documents it
   as conforming rather than renaming it), `gate-battery: run=<id> op=battery RESULT=...
   cmds=<n> failed=<k> (elapsed=<s>s) [-> first failing gate: <name>]` (new). Agents trust the
   banner and NEVER grep runner logs or result files to disambiguate an exit code.
2. **Followable await.** A backgrounded run is re-acquirable by key from any later turn via an
   await entrypoint that re-emits the same banner as ITS last line and exits with the run's own
   exit code. Reserved exits: **124** = result not yet present (an await timeout is NEVER
   success), **125** = malformed/unreadable result. (Grammar and exits mirror
   `build-queue-await.ps1` byte-for-byte in semantics.)
3. **Turn-end gate — by reference.** The contract REFERENCES `_components/turn-end-gate.md`
   (never copies it): an enqueue/launch echo is not an outcome; a turn may not end while an owned
   run is in flight; drive to the banner, then consume it.
4. **Never-pipe-through-tail rule** (generalized from AlgoBooth's quality-gates.md): a pipeline
   masks the runner's exit code; read the guaranteed final banner line or the exit code, never a
   piped tail's status.

The contract also names the composition seam: **the seam between repos is this documented
grammar, not shared code** — the PowerShell queue plane and the Python battery runner conform
independently (D4).

### D2 — Op classes: serialize vs banner-only (PARK-PROVISIONAL)

Two op classes, decided per op:

- **Heavy ops** (compile-heavy, shared-compiler/artifact contention): join the existing
  machine-global FIFO queue as manifested `build-queue-ops.json` entries. This feature adds
  AlgoBooth `qg-rust` and `qg-sidecar` (both compile; contention with `tauri-build`/
  `cargo-release` is real). Workstation-only (locked D7, inherited).
- **Light ops** (pure CPU, no shared state, no artifact hygiene): runner + banner + await
  WITHOUT queue admission. The claude-config battery and AlgoBooth `qg -- ts|docs` are light —
  concurrent batteries ran fine all session; serialization is not the needed piece, the outcome
  contract is. Light ops never touch `~/.claude/state/build-queue/` and never require PowerShell,
  which is what keeps the battery cloud-compatible.

The `build-queue-ops.json` manifest schema is NOT grown an "unserialized" lane value in v1 —
light ops simply don't live in that manifest (they have their own battery manifest, D5). This
keeps the queue manifest's meaning exactly "ops admitted to the machine-global slot."

### D3 — Enforcement scope (PARK-PROVISIONAL)

- **Heavy manifested ops get deny rows** — additive `deny` entries on the new AlgoBooth ops
  (`npm run qg -- rust`, `npm run qg -- sidecar`, and bare `npm run qg` since it runs the rust
  gate), denied by the EXISTING `build-queue-enforce.sh` manifest machinery with a redirect
  naming the op's skill. No hook logic changes: the hook already compiles per-op deny patterns
  onto its segment-start anchor.
- **Light ops are NEVER hook-denied** — raw `python -m pytest user/scripts/`, raw
  `npm run qg -- ts|docs` remain allowed. Routing to the runner is advisory (skill prose +
  repo CLAUDE.md). Rationale: the false-deny cost is real and recent (3 guard false-deny bug
  variants: `block-terminal-kill-false-denies-quoted-argument-tokens`,
  `lazy-cycle-containment-lifecycle-patterns-still-unanchored`,
  `adhoc-blocker-write-hook-overbroad-scope`), and pytest is a high-frequency, many-shapes
  invocation surface where deny-pattern precision cannot be guaranteed.
- **Named risk — deny-pattern precision:** the deny for bare `npm run qg` must not catch
  `npm run qg -- ts`. The manifest deny rows must be authored so the more-specific allowed forms
  are not shadowed (pattern order / negative lookahead at the hook's existing compile step —
  implementation detail for phases, flagged here because it is exactly the false-deny class).

### D4 — Runner language seam (PARK-PROVISIONAL)

The claude-config battery runner is **stdlib-only Python** (`user/scripts/gate-battery.py`),
cross-platform, no PowerShell dependency, runnable in cloud sessions (build-queue is
workstation-only by locked D7; the battery MUST still run in cloud). It conforms to the contract
grammar independently — it does NOT shell `build-queue.ps1`, does not share code with the
PowerShell plane, and does not import the queue's state. Results live under
`~/.claude/state/gate-battery/<repo-key>/results/<run-id>.json` (same per-repo keying convention
as the queue: repo key from the git toplevel); state-dir-unwritable degrades gracefully (banner
still prints; await unavailable — noted in the banner's next-action).

### D5 — Battery manifest (SSOT for the 7 commands)

The battery's command list is a committed per-repo manifest:
**`.claude/skill-config/gate-battery.json`** (`{version, gates: [{id, cmd, cwd?}]}`), seeded in
claude-config with the 7-command battery **as commands** (the stable contract), not as a file
listing — the decomposition may reshape `user/scripts/` internals without touching the manifest.
`gate-battery.py` refuses (exit 2) without a manifest at the invoking repo's toplevel — a
manifest-less repo is unaffected by construction, mirroring the enforce hook's opt-in property.
The runner is thereby generic: any repo (cloud or workstation) opts in by committing a manifest.

### D6 — Thin skills

- **`/gate-battery`** — user-level skill (`user/skills/gate-battery/`), generic: runs the current
  repo's declared battery via the runner, trusts the banner, backgrounds long runs with the
  §await contract, and carries the turn-end gate by reference. Available in any repo; refuses
  cleanly (runner exit 2) where no manifest exists.
- **`/qg-rust`, `/qg-sidecar`** — AlgoBooth repo-scoped skills
  (`repos/algobooth/.claude/skills/`), same shape as `/tauri-build`/`/cargo-release`: enqueue via
  `build-queue.ps1 -Op <op>`, trust the `build-queue:` banner, `build-queue-await.ps1 -Seq <N>`
  for backgrounded follows, turn-end gate by reference.
- Existing Cognito skills (`/msbuild`, `/mstest`, `/nxbuild`, `/nxtest`) and AlgoBooth build
  skills are untouched; Phase 0 may add a one-line "conforms to runner-outcome-contract" pointer
  in docs only (never editing the skills themselves is acceptable if the pointer lands in
  `user/scripts/CLAUDE.md` instead).

### D7 — AlgoBooth manifest additions (additive)

New ops in `C:\Users\Jacob\repos\AlgoBooth\.claude\skill-config\build-queue-ops.json`:
`qg-rust`, `qg-sidecar` — `kind: test`-class exec scripts (thin `.claude/scripts/qg-*-filtered.ps1`
wrappers shelling `npm run qg -- rust|sidecar`), `hygiene: none` (qg compiles for checking; it
does not produce the Tauri artifacts the `rust-tauri` profile quarantines — phases may revisit),
`lane: heavy` (minutes-long compiles), `skill: /qg-rust|/qg-sidecar`, `deny` per D3. The runner
(`build-queue-runner.ps1`) and status/ETA surfaces need zero changes — the ops ride the existing
manifest-driven machinery.

### D8 — Path discovery note

AlgoBooth's non-standard path (`C:\Users\Jacob\repos\AlgoBooth`) is invisible to
`~/source/repos/*` globs (fleet discovery). Enforcement and queue keying are unaffected (payload
cwd git-toplevel keying, verified). `~/.claude/lazy-repos.json` does not exist on this box; a pin
entry is needed only if the fleet view must see AlgoBooth — documented as a one-line recipe in
the contract component's notes, not implemented here.

## Locked Decisions

| ID | Decision |
|----|----------|
| L1 | The generalization deliverable is ONE documented contract — `user/skills/_components/runner-outcome-contract.md` (banner grammar + followable await with 124/125 semantics + turn-end gate BY REFERENCE to `_components/turn-end-gate.md`, never copied) — instantiated per repo; the cross-repo seam is the documented grammar, not shared code. |
| L2 | **PARK-PROVISIONAL (ratification pending):** light ops (claude-config battery, AlgoBooth `qg -- ts` / `qg -- docs`) get runner+banner+await WITHOUT machine-global queue admission; heavy AlgoBooth gates (`qg -- rust`, `qg -- sidecar`) join the existing queue as manifested ops. The queue manifest gains no "unserialized" lane value. |
| L3 | **PARK-PROVISIONAL (ratification pending):** hook-deny only for heavy manifested ops (additive AlgoBooth `deny` rows on the existing manifest machinery); raw light invocations (`pytest user/scripts/`, `npm run qg -- ts` / `-- docs`) are NEVER hook-denied — advisory routing only. |
| L4 | **PARK-PROVISIONAL (ratification pending):** the claude-config battery runner is stdlib-only cross-platform Python (`user/scripts/gate-battery.py`) conforming to the contract grammar independently of the PowerShell queue plane; it must run in cloud sessions (queue stays workstation-only per locked D7). |
| L5 | Battery command SSOT is the committed per-repo `.claude/skill-config/gate-battery.json`; the runner refuses without one (manifest-less repo unaffected by construction); claude-config seeds it with the 7-command battery as commands (stable contract), not file paths. |
| L6 | Cognito Forms is byte-untouched: no edits to its manifests, skills, `build-queue*.ps1` behavior, or the enforce hook's legacy fallback; all 5 Pester suites must stay green as a completion gate. |
| L7 | Sequencing: implementation begins only after `lazy-core-package-decomposition` completes (hard dep, machine-enforced via `--sync-deps` at `/spec-phases` Step 1.6). |
| L8 | Required MCP tooling: none — every Validation Criteria row is CLI/pytest/Pester-verifiable; claude-config has no MCP runtime (Step 9 exemption via operator-granted `SKIP_MCP_TEST.md` per `.claude/skill-config/quality-gates.md`), and no MCP tool must exist or be built for this feature's validation. |

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| Battery runs as one command with authoritative banner | `python3 user/scripts/gate-battery.py --repo-root .` (all gates green) | LAST stdout line matches the `gate-battery:` grammar with `RESULT=PASS cmds=7 failed=0`; process exit 0 | terminal output; `~/.claude/state/gate-battery/<key>/results/<run>.json` |
| Failure identification | one gate forced red | banner `RESULT=FAIL failed=1 -> first failing gate: <id>`; exit non-zero | terminal; pytest test |
| Followable await — in flight | `--await <run-id>` before completion | exit **124**, output contains no success language | pytest test (fixture result dir) |
| Followable await — done | `--await <run-id>` after completion | banner re-emitted as last line; exit = run's own exit code | pytest test |
| Malformed result | corrupted `results/<run>.json` + `--await` | exit **125** | pytest test |
| Manifest-less repo unaffected | runner invoked in a repo without `gate-battery.json` | refuse with exit 2 and a one-line reason; zero state written | pytest test |
| Cloud compatibility | battery run in a cloud session (no PowerShell) | identical banner/results behavior; zero PS invocations | cloud session log during this feature's own pipeline run |
| Cognito untouched | run all 5 `build-queue*.Tests.ps1` Pester suites at HEAD | all pass; `git diff` shows zero changes under the Cognito manifest/skills | Pester output (workstation) |
| AlgoBooth heavy op queue-routed | `/qg-rust` on workstation | `build-queue: seq=<N> op=qg-rust RESULT=...` as last line; result recorded | `~/.claude/state/build-queue/results/<seq>.json`; `/build-queue-status` |
| AlgoBooth deny + redirect | raw `npm run qg -- rust` in AlgoBooth | hook deny naming `/qg-rust`; `npm run qg -- ts` still allowed | hook fixture tests (`user/scripts/` hook test suite) |
| Light ops never queue | battery run while a queue build is active | battery proceeds; no queue state touched | state dir inspection; pytest test |
| Turn-end gate wired by reference | lint pass over new skills | each new skill injects/references `_components/turn-end-gate.md`; no copied gate text | `lint-skills.py` + grep |

## Implementation Phases

- **Phase 0 — Contract.** Author `user/skills/_components/runner-outcome-contract.md`
  (grammar, await semantics, turn-end-gate reference, never-pipe-through-tail, seam statement,
  AlgoBooth path-discovery note); add the `user/scripts/CLAUDE.md` pointer row. Docs-only;
  cloud-safe.
- **Phase 1 — Battery runner.** `user/scripts/gate-battery.py` (stdlib; manifest-driven; banner;
  results file; `--await` with 124/125; exit-2 refusal without manifest) + seed
  `.claude/skill-config/gate-battery.json` with the 7 commands + pytest suite under
  `user/scripts/tests/`. Cloud-safe.
- **Phase 2 — `/gate-battery` skill.** User-level thin skill wrapping the runner; turn-end gate
  by reference; `lint-skills.py` + projection green. Cloud-safe.
- **Phase 3 — AlgoBooth ops.** `qg-rust`/`qg-sidecar` manifest entries + exec wrappers + deny
  rows (D3 precision risk addressed with fixture tests) + repo-scoped thin skills. Workstation.
- **Phase 4 — Validation + docs.** Full battery via the new runner (dogfood), all 5 Pester
  suites, `lint-skills.py`, `doc-drift-lint.py` (CLAUDE.md script/hook tables updated),
  KPI-note wiring, `SKIP_MCP_TEST.md` per repo policy. Mixed.

## KPI Declaration

```json
{
  "id": "generalized-runner-raw-invocation-deny-recurrence",
  "system": "generalized-runner",
  "title": "Raw heavy-gate invocation deny recurrence (AlgoBooth)",
  "friction": "Agents hand-rolling raw heavy quality gates (npm run qg -- rust|sidecar) instead of the queue-routed skills burn a hook deny plus a redirect turn each time; recurrence measures whether the generalized skill-routing lesson sticks outside Cognito.",
  "signal": { "source": "deny-ledger", "selector": "build-queue-enforce-deny-count" },
  "unit": "count/30d",
  "direction": "down-is-good",
  "baseline": { "value": null, "captured_at": null, "window": "30d", "provenance": "pending" },
  "band": null,
  "review_by": "2026-11-01",
  "repo_scope": "algobooth",
  "notes": "Same selector as the cognito-forms row build-queue-raw-invocation-deny-recurrence, scoped to AlgoBooth once the qg deny rows land (this feature's Phase 3). Honest NO-DATA until denies are ledgered (the existing hook-side ledgering follow-up applies here too)."
}
```

```json
{
  "id": "runner-turn-end-stall-recurrence",
  "system": "generalized-runner",
  "title": "Premature turn-end on in-flight gate batteries (non-Cognito)",
  "friction": "Execution subagents hand-roll the claude-config 7-command battery, background it, and end their turn before the result — the exact class the Cognito banner/await/turn-end contract closed; each recurrence costs a manual resume plus a redone verification pass (4 recurrences observed in one orchestrated run, 2026-07-13).",
  "signal": { "source": "deny-ledger", "selector": "process-friction-count" },
  "unit": "count/30d",
  "direction": "down-is-good",
  "baseline": { "value": null, "captured_at": null, "window": "30d", "provenance": "pending" },
  "band": null,
  "review_by": "2026-11-01",
  "repo_scope": "claude-config",
  "notes": "Counted from friction-class ledger entries whose signature matches premature-turn-end / hand-rolled-battery incidents (incident-scan clusters these). Honest NO-DATA where no such entries exist. The implementation MAY register a dedicated gate-battery signal source+selector (ordinary selector addition — canary-trip-precision precedent) and re-point this row then."
}
```

## Open Questions

1. **Ratification of L2/L3/L4** — parked provisionally under the operator's park-provisional
   directive; enumerated with alternatives in `NEEDS_INPUT_PROVISIONAL.md`. Implementation may
   proceed on the recommended options; a reversal before Phase 3 is cheap (the manifest/deny
   surface is additive and isolated).
2. Whether AlgoBooth's light `qg -- ts|docs` ops later register in a `gate-battery.json` for
   await coverage (v1 leaves them direct — they already carry the `QG_VERDICT:` banner).
3. Whether a dedicated `gate-battery` KPI signal source/selector is registered during
   implementation (see the second KPI row's notes).
4. `hygiene` profile for `qg-rust`/`qg-sidecar` — `none` locked provisionally in D7's design
   text; phases re-check whether qg's cargo invocations can poison shared target dirs.

## Research References

No Gemini deep-research run — per repo policy (claude-config: negligible research volume;
research resume is a direct `RESEARCH.md` drop) this feature's grounding is the committed
operator brief (`ADHOC_BRIEF.md`, field-verified against both target repos on 2026-07-13) plus
this session's on-disk re-verification. See `RESEARCH_SUMMARY.md` for the recon findings that
shaped D1–D8, and the Ground Truth table above for per-claim citations.
