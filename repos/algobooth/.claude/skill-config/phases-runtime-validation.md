#### Runtime Assumption Validation Gate (AlgoBooth — BEFORE DRAFTING PHASES)

> **Why this gate exists.** The Hardware Override Protocol was planned and re-planned FOUR times against a code-read assumption (`parameter_id` is stamped correctly) that the *running* sidecar contradicted — it emitted `None` on every hap. Every code review and unit test agreed with the wrong assumption; only live runtime observation at the capnp decode boundary exposed it. When a phase plan rests on how the running system actually behaves, confirm it against the running system before committing the plan. See `docs/features/mixer/hardware-override-protocol/ANALYSIS-actuation-root-cause.md`.

**Step A — Enumerate the plan's runtime-coupled assumptions.** From the boundary analysis (Step 2) and the SPEC, list every assumption the phases depend on that is NOT provable from source alone. Runtime-coupled smells (any of these → validate):
- the runtime shape/contents of data crossing a boundary — what a function/closure actually receives at call time (e.g. the `value` a sidecar resolver sees), not what the type or a unit-test fixture says;
- whether an existing production code path actually fires / is reached (vs. merely exists in source);
- the live output a separate process emits — the sidecar's serialized haps over the capnp / named-pipe wire;
- a rendered/observable audio or effect result (cutoff, gain, routing, mix);
- timing/ordering across the audio-callback thread or IPC.

**Step B — Validate the load-bearing ones against the running app (where appropriate).** AlgoBooth is MCP-testable — use it. Cheap runtime checks available from the orchestrator session:
- Boot/reuse the dev app per `docs/development/CLAUDE.md` (resolve the CURRENT `logs/session-*/` dir fresh — NEVER cache it).
- Drive real input: `update_code` to load a real pattern; `inject_midi` for hardware events; `load_test_tone` for synthetic audio.
- Observe real output: `audio_filter` / `get_audio_buffer` (POST, `capture` feature) for rendered audio + `rms`/`dc_offset`/`scheduler_playing`; `get_console_logs` / `get_session_events` for sidecar/runtime signals; the override/telemetry tools for register state. Authoritative tool list + HTTP methods: `MCP_USAGE_GUIDE.md` + `src-tauri/src/ipc/mcp/registrations.rs` (several `get_*` tools are POST — do not infer from the name).
- For a data-shape assumption at a process boundary, a one-off `tracing::warn!` / `console.error('[DIAG] …')` at a **non-hot-path** boundary (e.g. the capnp decode site, sidecar stderr — **NEVER the audio-callback hot path**), then rebuild + short run + grep the session log, is the decisive check. Revert the instrumentation afterward and leave the tree clean.

Record the OBSERVED ground truth (the actual tool calls + numbers, or the logged value) in a `## Validated Assumptions` note at the top of PHASES.md and in the affected phase's Integration Notes. That note MUST contain a **per-assumption ledger table**:

| assumption | how-confirmed (`grep` / `runtime` / `spike`) | evidence |
|---|---|---|
| … | … | … |

"Code-read" is **not** an allowed `how-confirmed` value for any assumption that carries a runtime-coupled smell (from Step A). An assumption may be marked code-provable only if it carries NONE of those smells — state that determination explicitly in the ledger row, not in free text.

**Boundary-reachability rule (sidecar plans):** for any plan touching the sidecar, the confirmation MUST read the **spawn site / transport wiring** (where the sidecar process is actually launched and how messages reach it), NOT merely a handler `match` arm. `sidecar-watchdog` and `save-form-validation` both planned against code paths that exist in source but are never reached in production — that is the four-attempt trap in a different costume.

**Architecture-topology rule (per-channel / per-cue audio processing):** any plan that proposes per-channel or per-cue data-structure widening MUST cite the actual bus declarations in `callback/mod.rs` (the real fixed bus count) BEFORE proposing that widening. `eq-filter-ui` planned an array-widening the fixed 2-bus engine could never deliver.

**Step C — If validating now is premature** (the behavior doesn't exist until the feature is built), schedule it as an explicit **early runtime spike** deliverable in Phase 0 / the first phase ("instrument and confirm X at the live boundary before building on it") with a `- [ ]` checkbox under **Runtime Verification**. Never let a load-bearing runtime assumption ride unverified into a later phase.

**When to skip (record the reason):** an assumption may be marked code-provable in the ledger ONLY if it carries none of the runtime-coupled smells from Step A — pure logic, types, config, UI layout, or a behavior-preserving refactor with snapshot/golden coverage, with no sidecar/IPC/audio-observable behavior in play. The skip is stated in the ledger row itself; free-text notes outside the ledger are not sufficient.

**Anti-pattern (the four-attempt trap):** reading source to "confirm" a runtime assumption that crosses a boundary. Unit-green and a plausible code read are NOT runtime confirmation. For cross-boundary or runtime-observable behavior, observe the running system before planning on it. This gate pairs with the production-faithful **Testing Strategy** guidance (what you then test) — this gate governs what you *confirm before planning*, that one governs what you *assert when implementing*.

---

#### MCP Tool-Existence Audit (AlgoBooth — BEFORE DRAFTING PHASES)

> **Why this gate exists.** A feature whose `/mcp-test` scenario calls an MCP tool that is not yet registered in AlgoBooth's tool surface used to fail only at Step 9 (pipeline end) — forcing a corrective add-phase or `adhoc-mcp-*` spin-off and 3–6 wasted validation cycles (`d8-effect-chains`, `f5-slip-mode`, `change-queue`, …). See `docs/bugs/mcp-tooling-not-predetermined-at-planning`. Predetermine MCP tool existence HERE, at planning time, and auto-author the build phase up front.

**Step A — Enumerate the MCP tools the SPEC's validation will call.** Read every tool named in the SPEC's `## Validation Criteria`, `## Locked Decisions` (including any required-MCP-tooling decision captured at `/spec`), and the `## Audio Quality Contracts` table (the `Tool` column) where present.

**Step B — Resolve the tool catalog and grep the live registry.** Read `.claude/skill-config/mcp-tool-catalog.md` (the per-repo catalog declaring the live-registry source paths: `scripts/mcp-test/tool-methods.ts` + the Rust `inventory::submit!` sites under `src-tauri/src/ipc/mcp/registrations/`). For each enumerated tool, grep both sources for the tool-name registration and record one ledger row per tool in the catalog's declared format:

| tool-name | registered? | source (file:line, or "no hits") |
|---|---|---|
| … | yes / no | … |

`how-confirmed` is always `grep` here. **Catalog absent → this audit is a no-op** (record the skip reason) — though AlgoBooth always configures it.

**Step C — On a MISS (zero hits in both sources): AUTO-AUTHOR a build phase up front.** Insert an ordinary `- [ ]` build deliverable into the drafted PHASES.md naming the missing tool and citing the driving SPEC decision — e.g. `- [ ] Register MCP tool \`set_slip_pad_template\` exposing <surface> (required by Locked Decision N; absent from the tool catalog)`. This is the DEFAULT per the bug's Locked Decision 2 — NOT a `NEEDS_INPUT.md` halt and NOT a late `/mcp-test` discovery. Predetermine existence + schedule the build; leave the tool's signature/handler shape for `/execute-plan`. The auto-authored row is a PLAIN build deliverable — never a gate-owned row (no status flip / receipt write).

**Step D — NEEDS_INPUT fallback (genuinely-ambiguous only).** Reserve `NEEDS_INPUT.md` for the case where the missing tool's surface/shape cannot be inferred from the SPEC at all (so even a stub deliverable cannot be named). A merely-missing tool with an inferable surface is auto-authored, never halted.

> **Worked example.** A SPEC names `set_slip_pad_template` in `## Validation Criteria`. The audit enumerates `{set_slip_pad_template}`, greps `tool-methods.ts` + the `inventory::submit!` sites via `mcp-tool-catalog.md` — zero hits in both → ledger row `set_slip_pad_template | no | no hits in either source` → auto-authored up-front deliverable `- [ ] Register MCP tool \`set_slip_pad_template\` (required by Validation Criteria; absent from catalog)`. The tool now lands BEFORE `/mcp-test`, eliminating the corrective loop (the `f5-slip-mode` failure mode). A SPEC whose tools all resolve to `registered? = yes` produces a clean ledger and no auto-authored phase.

---

#### Module-Move Inbound-Seam Audit (BEFORE DRAFTING PHASES — when the plan moves/renames/deletes a module or file other code may load)

> **Why this gate exists.** A moved module's OUTBOUND dependencies are visible from inside it; INBOUND consumers that load the OLD path by literal file path are not — and they break at execution (or test collection), not at planning. See `docs/bugs/planning-audit-blind-to-inbound-module-path-loads` in claude-config (the lazy-core-package-decomposition incident: all six outbound lookups were enumerated as WUs; both inbound literal-path loaders were missed and broke, one silently disarming a gate).

For EACH old path the plan retires, grep the whole repo for literal-path loads — `spec_from_file_location` / `importlib.util` file loads, `runpy`, `open()`/`readFile` of the module path, subprocess/`node`/`tsx` invocations of the file, hardcoded path strings (INCLUDING tests' module-scope loaders and script imports in `scripts/`) — and record one ledger row per hit (`consumer file:line | load form | migration deliverable`), enumerating EACH hit as an explicit `- [ ]` deliverable. Zero hits is itself a recorded row (`how-confirmed: grep`, "no inbound literal-path loads of <old path>").

---

#### AGPL / IP Placement Audit (AlgoBooth — BEFORE DRAFTING PHASES)

> **Why this gate exists.** `strudel-sidecar/` is publicly published AGPL code (`docs/legal/AGPL_PUBLICATION_MANIFEST.md`) — every file placed there is disclosed. Placement is an IP decision made at SPEC time; phases must not silently move logic sidecar-side.

**Step A — Locate the SPEC's `## AGPL / IP Placement` section.** It is REQUIRED for any SPEC touching pattern evaluation, the sidecar, or IPC. If the feature touches those surfaces and the SPEC lacks the section: interactive → refuse to draft phases and route back to `/spec` to author it (questions (a)–(d): sidecar-runtime need? per-piece why-not-host-side? new `audio_event.capnp` payload kind? new AGPL dependency / server-side Strudel execution?); `--batch` → `NEEDS_INPUT.md`. If the feature touches none of those surfaces, record the skip reason and move on.

**Step B — Justify every sidecar-side deliverable.** Any phase deliverable that creates or grows a file under `strudel-sidecar/` must map to a sidecar-side piece the section's question (b) justifies (why it can't be host-side computation over data that already crosses the wire). An unjustified sidecar-side deliverable is a placement change — move it host-side or route the placement question back to the SPEC; never draft it as-is.

**Step C — Schedule the coupled legal artifacts.** A phase adding a new kind of payload to `audio_event.capnp` must carry `docs/legal/AGPL_ISOLATION.md` updated **in the same commit** as an explicit deliverable. A phase introducing a new AGPL dependency (e.g. `hydra-synth`) or any server-side Strudel execution must be preceded by a `docs/legal/AGPL_PUBLICATION_MANIFEST.md` entry deliverable (manifest entry first).
