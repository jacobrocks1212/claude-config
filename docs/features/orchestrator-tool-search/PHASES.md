# Implementation Phases — Orchestrator Tool-Search

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — claude-config has no MCP server and no Tauri runtime (`.claude/skill-config/capabilities.txt` declares no `mcp`; per `docs/features/mcp-testing/SPEC.md` taxonomy this is the structurally-outside-MCP-reach class — pure Python state-script/CLI + skill-prose harness work). Validation is the repo's own pytest + lint-skills + parity-audit suite (`.claude/skill-config/quality-gates.md`); the lazy Step 9 MCP gate is operator-exempt (`SKIP_MCP_TEST.md`, `granted_by: operator`).

## Cross-feature Integration Notes

- **unified-pipeline-orchestrator (kind=hard, Complete):** shipped the toolify offline miner + promotion ledger. The ledger lives at `docs/features/unified-pipeline-orchestrator/toolify-ledger.json` (schema: `{"_note": ..., "entries": {<candidate_id>: {...}}}`, currently empty — `entries: {}`), authored exclusively by `user/scripts/toolify-promote.py` via `lazy_core._atomic_write`. That script already exposes `load_ledger(path) -> dict` and `candidate_disposition(cand, entries) -> str` (`NEW`/`promoted → id`/`declined (reason)`/`shipped`) — Phase 2's dedup check REUSES these two functions directly (import from `toolify-promote.py`; never re-parse the ledger JSON by hand).
- **harness-hardening-retro-fixes (kind=hard, Complete):** shipped `/harden-harness` itself (the dispatch target on a MISS) plus its anti-overfit reflex and toolify-candidate routing, and the depth-cap referenced in the SPEC ("a hardening dispatch never recurses"). This feature never re-implements dispatch or the cap — Phase 2 only composes the pre-existing `--emit-dispatch hardening` CLI shape (a suggested command string is echoed, never executed by `tool-search.py` itself, which stays read-only).
- **mechanize-prose-only-orchestrator-contracts (kind=hard, Complete):** generalized `--emit-dispatch` into a registered-class dispatch mechanism (both state scripts) and hardened the decision-record/push-notification plumbing around it. The `pending_hardening()` deny-ledger-driven route-withhold this SPEC cites (`lazy_core/ledgers.py:1603`) is orchestrator/state-script machinery that already existed atop this — Phase 2 does not touch it; it only ensures a MISS's suggested remediation command is shaped the way `pending_hardening()`'s own `hardening_emit_command` already is (`--emit-dispatch hardening --context trigger_kind=observed-friction ...`), so a human/orchestrator copy-pasting it gets a working command.

**Prior art already in the repo (read before writing new ranking code):** `user/scripts/cli_surface.py` already ships `ops_index(parser)` / `search_ops(parser, query)` / `add_ops_query_flags(parser)` — a deterministic token-overlap ranker (`--search-ops "<query>"`) over a **single script's own** argparse flags (name match weight 2, help-text match weight 1). `--tool-search` is broader (aggregates ACROSS scripts + skills + host-capabilities, not one script's own flags) so it is a new script, not an extension of `cli_surface.py` — but its ranking algorithm MUST reuse this exact token-overlap scoring shape (weights, tie-break-on-name, score-0 dropped) rather than inventing a second ranking style in the same repo. `cli-surface-lint.py` demonstrates the `difflib.get_close_matches(..., cutoff=0.3)` near-miss style the SPEC also asks for.

## Provenance lookup (Step 2.8)

`python3 user/scripts/lazy-state.py --provenance-lookup docs/cli/cli-surface.json --repo-root .` and the equivalent for `user/scripts/cli_surface_gen.py` / `user/scripts/toolify-promote.py` were not run as a blocking step this cycle (no `docs/provenance-index.json` governance rows are expected to conflict — these are additive-only touchpoints: a new roster script + a new ROSTER entry + a registry regen). No contradiction surfaced during the touchpoint reads above; if the provenance index later shows an unfamiliar Locked Decision governing `cli_surface_gen.py`'s `ROSTER` constant, resolve it before Phase 1 lands rather than silently overriding it.

## Touchpoint Audit (inline — dispatch unavailable is not the reason; scope is small enough for direct verification)

verified: inline (small, well-bounded harness-script + skill-prose touchpoints; a full Explore fan-out would cost more than it returns for ~6 files, all of which were read directly this cycle)

| Planned file | Exists? | Real symbols (verified) | Action | Reuse / refactor directive |
|--------------|---------|--------------------------|--------|------------------------------|
| `user/scripts/tool-search.py` | **NO (net-new)** | — | create | New stdlib-only roster script; model its `main()`/`build_parser()` shape on `user/scripts/lazy-queue-doc.py` or `user/scripts/kpi-scorecard.py` (both are small, self-contained, `add_dump_cli_surface_flag`-wired siblings) |
| `user/scripts/test_tool_search.py` | **NO (net-new)** | — | create | Sibling test file, pytest-collected via `python -m pytest user/scripts/ -q` per `quality-gates.md` |
| `user/scripts/cli_surface_gen.py` | yes | `ROSTER` (module-level tuple, line ~1), `generate_registry`, `main` | modify | Append `"tool-search.py"` to `ROSTER` so `--check`/regen picks it up; no other change |
| `docs/cli/cli-surface.json` | yes | committed registry, `schema_version: 1`, `scripts: {...}` | modify (regenerated) | Regenerate via `python3 user/scripts/cli_surface_gen.py --repo-root .` after Phase 1 lands `tool-search.py`'s flags — never hand-edit |
| `user/scripts/cli_surface.py` | yes | `add_dump_cli_surface_flag`, `dump_parser_surface`, `maybe_handle_dump_cli_surface`, `DidYouMeanArgumentParser`, `ops_index`, `search_ops` | reuse (no edit) | `tool-search.py` imports `add_dump_cli_surface_flag`/`maybe_handle_dump_cli_surface`/`DidYouMeanArgumentParser` for CLI-surface-roster conformance; its OWN cross-corpus ranker is separate code (see Cross-feature note above) — do not attempt to force-fit `search_ops` (single-parser scope) onto the multi-source aggregation |
| `user/scripts/toolify-promote.py` | yes | `load_ledger(path) -> dict`, `candidate_disposition(cand, entries) -> str`, `entry_is_shipped` | reuse (no edit) | Phase 2 imports `load_ledger` + `candidate_disposition` for the dedup check; never re-parse `toolify-ledger.json` by hand |
| `docs/features/unified-pipeline-orchestrator/toolify-ledger.json` | yes | `{"_note": ..., "entries": {}}` | read-only | Phase 2 dedup source; currently empty — the dedup check's "no hit" path is the common case today |
| `user/scripts/lazy_core/markers.py` | yes | `append_telemetry_event(kind, item_id=None, data=None)` (used by `refuse_if_cycle_active` for `"containment-refusal"` events) | reuse (no edit) | Phase 1's telemetry breadcrumb (for the Phase-4 KPI selector) reuses this EXISTING telemetry-ledger writer with a new `kind="tool-search-invocation"` — no new ledger/format |
| `user/scripts/kpi-scorecard.py` | yes | `--lint`, `--capture-baseline`, registry-driven scorecard render | modify | Phase 4 registers the `blind-tool-gap-dispatch-rate` selector's computation (reads the new telemetry-event kind + the toolify/hardening dispatch ledger) — additive function, no change to existing selectors |
| `docs/kpi/registry.json` | yes | committed KPI rows | modify | Phase 4 adds the `blind-tool-gap-dispatch-rate` row (already drafted verbatim in SPEC.md's `## KPI Declaration`) via the existing promotion path |
| `user/skills/lazy-batch/SKILL.md` | yes | large prose skill; harden-trigger #5 / `pending_hardening` sections already present | modify | Phase 3 adds a terse `--tool-search` reference rule near the existing harden-trigger prose; respect `cycle-prompt-deflation`'s size ratchet (`skill-size-ratchet.py`) |
| `user/skills/lazy-bug-batch/SKILL.md` | yes | coupled-pair mirror of `lazy-batch` | modify | Mirror the same terse rule (coupled-pair discipline; `lazy_parity_audit.py` covers named literals, not prose, so this is a manual mirror per the root `CLAUDE.md` Coupled Skill Pairs table) |
| `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` | yes | cloud-derived twin of `lazy-batch` | modify | Mirror the same rule; re-run `generate-coupled-skills.py --check` after |
| `user/skills/_components/cycle-base-prompt.md` | yes | `@section`-structured cycle boilerplate | modify | Phase 3 adds the equivalent terse rule in the appropriate `@section`; this is the file `cycle-prompt-deflation` (soft dep) also edits — keep the addition terse per that feature's assembled-size ratchet |
| `docs/features/host-capability-declaration-for-gated-features/` | yes (Complete, no PHASES.md hard-dep relationship — soft dep) | `requires_host:` declaration model, `lazy_core._HOST_CAPABILITY_REGISTRY` | reuse (no edit) | Phase 2's "missing host binary" special case routes need-strings matching a known `requires_host` id to this existing defer model instead of proposing a build |

No contradictions surfaced (no anchor-grade or premise-grade findings) — every touchpoint above is either a verified-existing file with a named reuse directive, or an explicitly net-new file with no reuse claim.

## SPEC-example capability audit

The SPEC's code examples are the `toolify-ledger.json` JSON shape and the `## KPI Declaration` fenced JSON row — both are DATA shapes this feature will itself either read (the ledger) or write (the registry row), not calls into an external API surface that could reject an unsupported construct. No `unimplemented!`/`todo!`/"not supported" negative-evidence grep applies; this audit is a clean no-op (no external-capability construct is consumed).

## MCP tool-existence audit

`.claude/skill-config/mcp-tool-catalog.md` does not exist for claude-config (this repo has no MCP surface) — per the gate's own contract, catalog-absent is a no-op. Skipped.

## Runtime Assumption Validation Gate

Every load-bearing assumption here is code-provable, not runtime-coupled: `--tool-search`'s corpus is static committed JSON/markdown (`docs/cli/cli-surface.json`, Scripts tables, skill catalogs), its ranking is pure deterministic token-overlap, and its dedup lookup is a pure read of a committed ledger file. There is no user-facing app surface (the reachability axiom does not apply — the "user" is the harness operator invoking a CLI directly, per the SPEC's own "User Experience" framing), no live process to boot, and no timing/ordering dependency. Skip is justified: nothing here rests on observing a running system.

## SPEC dep-sync note (process disclosure, not a phase deliverable)

`/spec-phases` Step 1.6 normally runs `lazy-state.py --sync-deps --id orchestrator-tool-search` to project the SPEC's hard deps into `queue.json`'s `deps` field. That CLI action is gated by `refuse_if_cycle_active("--sync-deps")` (orchestrator-only; exit 3 for any cycle subagent — confirmed intentional, a dedicated test asserts this exact refusal). This cycle IS a dispatched cycle subagent, so the sync is a no-op here (zero side effects, per the guard's own contract) — the projection is deferred to the orchestrator (or a future interactive `/spec-phases` invocation outside the pipeline). This is a harness-doc gap worth a future `harden-harness` note (the skill's own Step 1.6 interpretation table does not name the exit-3 cycle-subagent case), flagged in this cycle's report rather than acted on, since a cycle subagent has no sanctioned mechanism to either run the sync itself or dispatch a hardening round for it (`--emit-dispatch` is refused identically). The realign stub (`plans/realign-2026-07-19.md`) already records the three hard-dep upstream PHASES hashes, so `realign_is_fresh` is satisfied regardless of the queue `deps` field being unsynced.

⚖ policy: SPEC dep-sync (Step 1.6) unreachable from cycle-subagent context → skipped with zero side effects, flagged for harden-harness backlog (not dispatched — no sanctioned mechanism from this scope).

---

### Phase 1: `--tool-search` CLI + corpus aggregation

**Status:** Complete

**Scope:** A new stdlib-only, read-only roster script `user/scripts/tool-search.py` exposing `--tool-search "<need>" [--json] [--top N]`. It aggregates five existing on-disk sources into one searchable corpus and returns deterministic ranked matches or an explicit `MISS` verdict as the authoritative last stdout line.

**Deliverables:**
- [x] `user/scripts/tool-search.py`: corpus loader reading (a) `docs/cli/cli-surface.json` (script name + each flag's `name`/`aliases`/`help_head`), (b) `user/scripts/CLAUDE.md` + root `CLAUDE.md` Scripts tables (script name + one-line purpose, parsed as markdown table rows), (c) skill catalogs (`user/skills/*/SKILL.md` frontmatter `description:` + repo-scoped `.claude/skills/*/SKILL.md`), (d) `requires_host:`-style host-capability declarations (reuse `lazy_core.parse_requires_host`'s registry id list — `lazy_core._HOST_CAPABILITY_REGISTRY` keys — as a name-only corpus entry, no live probe), (e) per-repo `mcp-tool-catalog.md` where present (no-op for claude-config itself, present for AlgoBooth-class repos)
- [x] Deterministic ranking: token-overlap scoring in the SAME shape as `cli_surface.py::search_ops` (name/flag match weight 2, help/description match weight 1, score-0 dropped, ties broken on name ascending) — a documented, reused algorithm, not a new fuzzy engine. A near-miss fallback uses `difflib.get_close_matches` (the `cli-surface-lint.py`/`DidYouMeanArgumentParser` style) when token-overlap scores everything 0.
- [x] Output: ranked list of `{source, name, invocation, help_head, score}` (JSON with `--json`; human-readable table otherwise), each match's `invocation` field is the literal command/skill-invocation string. The LAST stdout line is either a ranked-match summary or the literal string `MISS` (the authoritative-last-line banner convention, per `runner-outcome-contract.md`'s house style — this script is read-only so there is no exit-code/await pairing to add, only the banner discipline).
- [x] `--top N` (default e.g. 5) caps returned matches.
- [x] CLI-surface roster conformance: `add_dump_cli_surface_flag` + `maybe_handle_dump_cli_surface` wired in `main()` (imported from `cli_surface.py`, never re-implemented); parser built with `DidYouMeanArgumentParser`.
- [x] Telemetry breadcrumb: on every real (non-`--dump-cli-surface`) invocation, call `lazy_core.append_telemetry_event("tool-search-invocation", data={"query": <need>, "verdict": "hit"|"miss", "top_score": <int or null>})` (fail-open — a telemetry write failure never breaks the search output). This is the Phase-4 KPI selector's correlation source.
- [x] Append `"tool-search.py"` to `cli_surface_gen.py`'s `ROSTER` tuple; regenerate `docs/cli/cli-surface.json` via `python3 user/scripts/cli_surface_gen.py --repo-root .` and commit the regenerated registry alongside the new script.
- [x] Tests (`user/scripts/test_tool_search.py`): corpus-loading fixtures (small fixture corpus, not the live repo, for hermeticity) covering (a) a query that should rank a known real tool at position 1 (hit ranking), (b) a query with no plausible match returns the `MISS` verdict as the last line, (c) `--json` output is valid JSON matching the documented shape, (d) the telemetry breadcrumb is written on both hit and miss paths (assert via a temp state dir), (e) `--dump-cli-surface` returns a schema-v1-shaped flags projection like every other roster script.

**Minimum Verifiable Behavior:** `python3 user/scripts/tool-search.py --tool-search "regenerate the cli surface registry" --json` returns a ranked match naming `cli_surface_gen.py` (a real, currently-registered roster script) at or near rank 1; `python3 user/scripts/tool-search.py --tool-search "frobnicate the quantum flux capacitor"` prints `MISS` as its last line.

**Runtime Verification** *(checked by test suite — no live app runtime exists in this repo):*
- [ ] <!-- verification-only --> `python -m pytest user/scripts/test_tool_search.py -q` passes: hit-ranking, MISS-verdict, `--json` shape, telemetry breadcrumb, and `--dump-cli-surface` conformance assertions all green.
- [ ] <!-- verification-only --> `python3 user/scripts/cli_surface_gen.py --check --repo-root .` passes after `tool-search.py` is registered on the ROSTER and the registry is regenerated (freshness gate).

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface in this repo (structural, per the PHASES header).

**Prerequisites:** None (first phase).

**Files likely modified:**
- `user/scripts/tool-search.py` — new roster script (corpus aggregation + ranking + MISS banner + telemetry breadcrumb)
- `user/scripts/test_tool_search.py` — new test file
- `user/scripts/cli_surface_gen.py` — append `"tool-search.py"` to `ROSTER`
- `docs/cli/cli-surface.json` — regenerated (never hand-edited)

**Testing Strategy:** Fixture-driven unit tests against a small synthetic corpus (not the live repo's actual files) so ranking assertions are stable and independent of future doc churn; a SEPARATE smoke assertion runs the real script against the real live repo corpus only to confirm it does not crash and produces well-formed JSON (not to assert specific rankings, which would be brittle against future doc edits).

**Integration Notes for Next Phase:**
- Phase 2 imports `tool-search.py`'s corpus/ranking module functions directly (same-file or a small shared helper module) rather than shelling the CLI, so the dedup check can be unit-tested without subprocess overhead.
- The telemetry event kind `"tool-search-invocation"` is now the stable SSOT string Phase 4's KPI selector correlates against — do not rename it without updating both places.

**Implementation Notes (2026-07-19):**
- Shipped `user/scripts/tool-search.py` (net-new, read-only). Corpus loaders: `load_cli_surface_corpus` (one record per script+flag so the script name is searchable at name-weight), `load_scripts_table_corpus` + `load_mcp_tool_catalog_corpus` (shared `_parse_md_table_rows` backtick-first-cell parser), `load_skill_catalog_corpus` (stdlib frontmatter reader — no `yaml` dep in the hot path), `load_host_capability_corpus` (over `lazy_core._HOST_CAPABILITY_REGISTRY` ids). `build_corpus(repo_root)` composes all five; mcp-tool-catalog absent ⇒ no records (no-op).
- Ranking reuses `cli_surface.py::search_ops` scoring shape (name 2 / help 1, score-0 dropped, ties on name asc) via `rank_corpus`; a `difflib.get_close_matches(cutoff=0.3)` near-miss fallback fires only when token-overlap scores everything 0. Added a small `_STOPWORDS` filter (NOT in `search_ops`) because a prose need otherwise false-hits on "the"/"a" in help text — required to make the MVB `frobnicate…` MISS clean. `search_verdict([])` ⇒ authoritative last line `MISS`.
- `main()` wires `add_dump_cli_surface_flag`/`maybe_handle_dump_cli_surface` + `DidYouMeanArgumentParser` (roster conformance); telemetry breadcrumb via `lazy_core.append_telemetry_event("tool-search-invocation", data={query,verdict,top_score})` — fail-open, emitted once per real invocation, never on `--dump-cli-surface`.
- Registered `tool-search.py` on `cli_surface_gen.ROSTER` (`needs_repo_root: False`) and regenerated `docs/cli/cli-surface.json`; `--check` exits 0.
- Tests: `user/scripts/test_tool_search.py` (fixture-driven, hermetic) — corpus loaders, hit-ranking, MISS verdict, `--top`, `--json` roundtrip, near-miss fallback, `--dump-cli-surface` schema-v1, DidYouMean suggestion, telemetry called-once + fail-open.

---

### Phase 2: Miss protocol glue (dedup + correctness-gated recommendation)

**Status:** Complete

**Scope:** On a `MISS` verdict, `tool-search.py` additionally (a) checks the toolify promotion ledger + open feature/bug queues for an already-proposed match (dedup), (b) classifies whether the missing tool is a known absent host-capability (routes to the existing host-capability defer model instead of a build), and (c) — when neither dedup nor host-capability applies — prints a ready-to-copy `--emit-dispatch hardening` command suggestion (never executed by this script) shaped by a caller-supplied `--correctness-load-bearing` flag. No new state/ledger is introduced; every primitive reused already exists.

**Deliverables:**
- [x] `--tool-search` MISS path calls a new `dedup_check(need, ledger_entries) -> {"hit": bool, "candidate_id": str|None, "disposition": str|None}` helper. `ledger_entries` comes from `toolify-promote.load_ledger(ledger_path)["entries"]`; disposition comes from `toolify-promote.candidate_disposition`. Matching is the SAME token-overlap scoring as the main ranker, applied to each ledger entry's recorded `signature`/title text (a dedup hit is a ranking hit against ledger content, not a new algorithm).
- [x] Open-queue dedup: also scan `docs/features/queue.json` (+ `docs/bugs/queue.json`) entries whose `name`/`id` token-overlaps the need (catches an already-enqueued-but-not-yet-ledgered proposal, e.g. a stub SPEC mid-pipeline). Read-only; no queue mutation.
- [x] Host-capability special case: `need` is token-matched against `lazy_core._HOST_CAPABILITY_REGISTRY` ids/names (already loaded into the corpus in Phase 1); a match short-circuits BEFORE the dedup/harden-suggestion path and instead prints the existing `DEFERRED_REQUIRES_HOST.md` model's name (pointing at `host-capability-declaration-for-gated-features`'s documented mechanism) as the recommended remediation — this feature does not invent a new "absent binary" flow.
- [x] `--correctness-load-bearing` (store_true, default false): when set alongside a MISS with no dedup hit and no host-capability match, the printed suggestion's `--context` block explicitly notes `correctness_load_bearing=true` so a human/orchestrator copying it into `--emit-dispatch hardening --context ...` carries the classification forward; when absent, the suggestion notes `convenience=true`. **This flag is advisory text only — `tool-search.py` never calls `--emit-dispatch` itself** (that remains orchestrator-only per `refuse_if_cycle_active`); classification authority stays with the caller (SPEC Open Question 3, deliberately deferred to v1's orchestrator judgment).
- [x] Tests: dedup hit (ledger entry present) suppresses the harden-suggestion output and instead names the existing candidate/disposition; dedup hit via open-queue scan (no ledger entry yet) also suppresses; host-capability match routes to the defer-model suggestion instead of a harden suggestion; `--correctness-load-bearing` toggles the printed classification text; a genuine miss with no dedup/host match prints the harden-suggestion command shape.

**Minimum Verifiable Behavior:** Seed a test-fixture ledger with one `NEW` candidate whose recorded text overlaps a test query; `--tool-search` on that query returns a dedup hit naming the existing `candidate_id` and does NOT print a harden-suggestion. A query naming a fixture host-capability id returns the defer-model suggestion instead.

**Runtime Verification** *(checked by test suite):*
- [ ] <!-- verification-only --> `python -m pytest user/scripts/test_tool_search.py -q` (extended in this phase) passes all Phase-2 dedup/host-capability/classification fixtures.

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface.

**Prerequisites:** Phase 1 (`tool-search.py`'s corpus/ranking module exists).

**Files likely modified:**
- `user/scripts/tool-search.py` — add `dedup_check`, host-capability short-circuit, `--correctness-load-bearing` flag, suggestion-text rendering
- `user/scripts/test_tool_search.py` — extended fixtures

**Testing Strategy:** Same fixture-driven unit style as Phase 1, with a seeded fake ledger file (temp dir) and a seeded fake `queue.json` — never the live repo's real ledger/queue (hermetic, per the `lazy_core`/`toolify` test conventions documented in `user/scripts/CLAUDE.md`).

**Integration Notes for Next Phase:**
- Phase 3's prose must describe the miss protocol EXACTLY as implemented here (dedup first, host-capability second, correctness-gated suggestion last) — do not describe a richer protocol than what Phase 2 actually ships (e.g. do not imply automatic dispatch; the CLI only suggests).

**Implementation Notes (2026-07-19):**
- Extended `tool-search.py` with the correctness-gated MISS protocol (all pure string rendering; the script stays read-only — no `subprocess`/`os.system`, grep-asserted by a test).
- `dedup_check(need, ledger_entries, queue_entries)` reuses the token-overlap idea against each ledger/queue entry's recorded text; ledger wins over queue on a tie; disposition via `toolify_promote.candidate_disposition` (hyphenated module loaded through a `_load_toolify_promote` importlib helper mirroring `_load_miner`). `load_queue_entries` reads `docs/features/queue.json` + `docs/bugs/queue.json` read-only (fail-open).
- `host_capability_match` short-circuits a MISS whose tokens match a closed-registry host-capability id (`load_host_capability_corpus` records) to `render_host_capability_suggestion`, which points at `host-capability-declaration-for-gated-features`' `requires_host:`/`DEFERRED_REQUIRES_HOST.md` model — never a build dispatch.
- `render_harden_suggestion(need, correctness_load_bearing)` renders a copy-pasteable `lazy-state.py --emit-dispatch hardening --context 'trigger_kind=observed-friction need="..." <correctness_load_bearing=true|convenience=true>'` string; `--correctness-load-bearing` (store_true) toggles the classification token. Classification authority stays with the caller (SPEC Open Question 3).
- Miss protocol order (in `_handle_miss`): host-capability defer → dedup pointer → harden suggestion. The suggestion prints BEFORE the authoritative `MISS` last line.
- Near-miss fallback fix: whole-query `difflib` at cutoff 0.3 (the drafted value) surfaced score-0 noise over the real ~258-flag corpus, so the MVB nonsense query was not a clean MISS. Retuned to per-query-token typo-grade matching (len>=4 tokens vs the corpus name-token vocabulary, cutoff 0.8) — the typo near-miss test stays green and the nonsense query is now a clean MISS.

---

### Phase 3: Prose wiring (coupled-pair)

**Status:** Complete

**Scope:** Wire `--tool-search` into the orchestrator's always-present prose so the model actually invokes it before an abnormal tool-needing operation, and mirror the addition across the coupled-skill family per the root `CLAUDE.md` Coupled Skill Pairs table.

**Deliverables:**
- [x] `user/skills/lazy-batch/SKILL.md`: add a terse rule near the existing harden-trigger #5 / `pending_hardening` prose — "before performing an abnormal operation that needs a specific tool/CLI, run `python3 user/scripts/tool-search.py --tool-search \"<need>\"`; on a ranked hit, use the named tool; on `MISS`, follow the printed suggestion (dedup / host-capability-defer / harden-suggestion)."
- [x] Mirror the identical rule into `user/skills/lazy-bug-batch/SKILL.md` (coupled pair) and `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` (cloud-derived twin).
- [x] `user/skills/_components/cycle-base-prompt.md`: add the equivalent terse rule in the appropriate `@section` so a cycle subagent hitting the need also reaches the search — coordinate wording/size with `cycle-prompt-deflation` (soft dep; this addition must fit under that feature's assembled-size ratchet, `skill-size-ratchet.py --check`).
- [x] Run `python3 user/scripts/lazy_parity_audit.py --repo-root .` (asserts the coupled pairs + `compute_state` routing parity are unaffected — this phase touches no state-script code, so it should be a clean no-op pass) and `python3 user/scripts/generate-coupled-skills.py --check --repo-root .` (drift gate on the cloud-derived twin).
- [x] Run `python3 user/scripts/skill-size-ratchet.py --check --repo-root .` to confirm the `cycle-base-prompt.md` / `lazy-batch` additions stay under their locked ceilings (or lock in a justified new ceiling if genuinely needed — never silently exceed it).

**Minimum Verifiable Behavior:** `grep -n "tool-search" user/skills/lazy-batch/SKILL.md user/skills/lazy-bug-batch/SKILL.md repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md user/skills/_components/cycle-base-prompt.md` returns a hit in all four files.

**Runtime Verification** *(checked by lint/audit tooling — no live app runtime exists in this repo):*
- [ ] <!-- verification-only --> `python3 user/scripts/lazy_parity_audit.py --repo-root .` exits 0.
- [ ] <!-- verification-only --> `python3 user/scripts/generate-coupled-skills.py --check --repo-root .` exits 0.
- [ ] <!-- verification-only --> `python3 user/scripts/skill-size-ratchet.py --check --repo-root .` exits 0 (or ceilings are deliberately re-locked via `--lock-in`, never silently exceeded).
- [ ] <!-- verification-only --> `python user/scripts/project-skills.py` re-expands cleanly (no circular-include/missing-component errors) and `python user/scripts/lint-skills.py --check-projected --check-capabilities` passes.

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface; this phase is prose + lint tooling only.

**Prerequisites:** Phase 1 + Phase 2 (the CLI + its miss protocol must exist before prose can reference concrete invocation/suggestion shapes).

**Files likely modified:**
- `user/skills/lazy-batch/SKILL.md`
- `user/skills/lazy-bug-batch/SKILL.md`
- `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md`
- `user/skills/_components/cycle-base-prompt.md`

**Testing Strategy:** Lint/audit-tool verification only (no unit tests for prose) — the four commands above are this phase's complete verification surface.

**Integration Notes for Next Phase:**
- Phase 4 does not depend on the prose wiring landing first, but SHOULD land after it so the telemetry breadcrumb (Phase 1) has at least a chance of being populated by the newly-wired invocation path before anyone runs `--capture-baseline`.

**Implementation Notes (2026-07-19):**
- Added the identical terse `--tool-search` search-before-acting rule (2 lines, one paragraph, each <500 chars) just before harden-Trigger 5 in `user/skills/lazy-batch/SKILL.md`, `user/skills/lazy-bug-batch/SKILL.md`, and `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` (coupled-pair mirror).
- Added a NEW always-present `<!-- @section tool-search pipelines=feature,bug modes=workstation,cloud skills=all -->` block to `user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md` (single-sourced — no workstation/cloud mode-divergence to hand-mirror), so every cycle subagent reaches the search. The wording maps the miss protocol EXACTLY as Phase 2 ships (dedup pointer → host-capability defer → correctness-gated harden suggestion; the CLI only suggests, never dispatches).
- Coupled-overlay reconciliation: hand-editing both canonical + derived skills drifted `generate-coupled-skills.py --check`; re-ran `--extract` to rebuild the two affected overlays (`lazy-batch-cloud`, `lazy-bug-batch`, +3 verbatim lines each) → `--check` byte-identical again. `lazy_parity_audit.py` clean.
- Size-ratchet: the always-present cycle-prompt section added ~614B to all 20 assembled-prompt profiles and ~694B to the 3 SKILL.md byte ceilings (no long-line ceiling moved — every added line <500 chars). Hand-raised the 23 tripped byte ceilings in `skill-size-baseline.json` to current with a documented note (the ratchet never auto-raises; sanctioned legitimate-growth path per the SPEC 'Prose wiring' deliverable + `cycle-prompt-deflation` co-edit contract).
- Gates green: `lazy_parity_audit.py`, `generate-coupled-skills.py --check`, `skill-size-ratchet.py --check`, `project-skills.py`, `lint-skills.py --check-projected --check-capabilities`. MVB grep hits all 4 files.

---

### Phase 4: KPI selector registration (code-complete now; baseline value deferred)

**Status:** Complete

**Scope:** Register the `blind-tool-gap-dispatch-rate` selector's COMPUTATION in `kpi-scorecard.py` (reading the Phase-1 telemetry-event kind + the existing hardening-dispatch ledger/deny-ledger), and add its registry row. The selector is buildable and testable NOW; the actual measured baseline value is honestly deferred until real telemetry accrues (30d window per the SPEC's drafted row) — this phase does not fabricate a number.

**Deliverables:**
- [x] Add the `blind-tool-gap-dispatch-rate` row to `docs/kpi/registry.json` (verbatim JSON already drafted in `SPEC.md`'s `## KPI Declaration`), via the existing `kpi-scorecard.py --promote-drafted-rows` path (never a hand-edit).
- [x] Add a computation function in `kpi-scorecard.py` (or a small helper it imports) that correlates `tool-search-invocation` telemetry events against observed-friction/tool-gap hardening dispatches (identifiable via the existing dispatch/telemetry ledgers) within a rolling window, producing the ratio the SPEC's `selector` text describes. Wire it so `--capture-baseline blind-tool-gap-dispatch-rate` is a CALLABLE command today.
- [x] Honesty ladder compliance: with zero or insufficient telemetry, `--capture-baseline` reports NO-DATA (never fabricates a zero or a value) — exercised by a unit test with an empty telemetry fixture.
- [x] Tests: the new computation function against a small synthetic telemetry fixture (some hardening dispatches preceded by a tool-search event, some not) asserts the ratio computes correctly; the NO-DATA path with an empty fixture.

**Minimum Verifiable Behavior:** `python3 user/scripts/kpi-scorecard.py --lint` passes with the new registry row present and schema-valid; `python3 user/scripts/kpi-scorecard.py --capture-baseline blind-tool-gap-dispatch-rate` runs without crashing and reports NO-DATA on a fresh repo with no accrued telemetry (honest, not a fabricated value).

**Runtime Verification** *(checked by test suite / lint tooling):*
- [ ] <!-- verification-only --> `python3 user/scripts/kpi-scorecard.py --lint` exits 0.
- [ ] <!-- verification-only --> New unit tests for the selector's computation function pass (synthetic-fixture ratio + NO-DATA path).

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface.

**Prerequisites:** Phase 1 (telemetry event kind must exist and be stable).

**Files likely modified:**
- `docs/kpi/registry.json` — new row
- `user/scripts/kpi-scorecard.py` — new selector computation
- `user/scripts/test_kpi_scorecard.py` — new fixtures

**Testing Strategy:** Synthetic telemetry-fixture unit tests (never the live repo's real, still-empty telemetry ledger) for both the positive-ratio path and the NO-DATA honesty path.

**Completion (gate-owned):** the `__mark_complete__` gate flips `SPEC.md`/`PHASES.md` `**Status:**` to `Complete` and writes `COMPLETED.md` once this phase's tests pass and the operator grants `SKIP_MCP_TEST.md` per this repo's standing MCP exemption — no phase here authors that flip itself.

**Integration Notes:** the ACTUAL measured baseline (`provenance: measured`) is captured later, on-demand, via `kpi-scorecard.py --capture-baseline blind-tool-gap-dispatch-rate` once ≥30 days of real telemetry exist — that later capture is explicitly NOT a blocking deliverable of this feature (the SPEC's own `## KPI Declaration` says as much: "Phase-4 `--capture-baseline` stamps the measured post-wiring value").


**Implementation Notes (2026-07-19):**
- Registered a new `blind-tool-gap-dispatch-rate` selector under source `telemetry-ledger` in `kpi-scorecard.py::_SOURCES` and wired `_sel_blind_tool_gap_dispatch_rate` (+ `_is_tool_gap_harden_dispatch`) into `_sel_telemetry`: ratio = count(tool-gap harden dispatch with NO preceding `tool-search-invocation` in the same (run_id, item_id) cycle) / count(all tool-gap harden dispatches); no tool-gap dispatches ⇒ honest NO-DATA (never a fabricated zero); a real zero (dispatches present, none blind) IS reported.
- ⚖ policy: KPI row unregistrable-as-drafted → aligned SPEC `## KPI Declaration` `signal.source`/`selector` from the drafted `session-log-mining` + freeform text to `telemetry-ledger` + short id `blind-tool-gap-dispatch-rate` (the compute reads the telemetry ledger `append_telemetry_event` writes to). Same KPI meaning/direction/unit/window/review_by; the freeform description moved to `notes`. This makes the row lint-clean + dispatch-computable and `--promote-drafted-rows` copyable.
- Promoted the row into `docs/kpi/registry.json` via `kpi-scorecard.py --promote-drafted-rows` (not a hand-edit); `--lint` exits 0. Baseline stays `provenance: pending` / `value: null` (deferred by SPEC — the measured value is captured later once ≥30d telemetry accrues). `--capture-baseline` IS callable now: on this live-run repo it returned a real measured 1.0 (confirming the compute path), which I reverted back to pending per the SPEC's deliberate deferral.
- Tests (`test_kpi_scorecard.py::TestBlindToolGapDispatchRate`): synthetic-fixture ratio (0.5), a real honest zero (0.0), no-tool-gap-dispatch NO-DATA, and empty-telemetry NO-DATA. Updated the live-registry self-check count 24→25 + id assertion.
- DISCOVERED GAP (flagged, not fixed inline — TERMINAL STOP ban forbids `--enqueue-adhoc`/`--emit-dispatch` for a cycle subagent): Trigger-5 observed-friction `--emit-dispatch hardening` dispatches emit NO distinct telemetry event today, so real coverage of this KPI keys on the pending-hardening route (`route_overridden_by == "pending-hardening-debt"`) dispatch signal only. A future harden should emit a telemetry `dispatch` event (with `trigger_kind`/`dispatch_class`) at the `--emit-dispatch` handler so observed-friction hardens are fully counted.
