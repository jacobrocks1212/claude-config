# SKIP_MCP_TEST frontmatter with an unquoted colon breaks the strict sentinel parser at the completion gate — Investigation Spec

> A `SKIP_MCP_TEST.md` waiver whose YAML frontmatter carries an **unquoted colon-space inside a
> value** (e.g. `reason: blocked by X: no host device`, or a `skipped_by:` line naming a
> `key: value` pair) makes the strict PyYAML-backed sentinel reader (`parse_sentinel`) raise a
> `ScannerError`, which `_die()`s the whole state script (exit 2). Because the completion / Step-9
> leg reads the waiver through that strict parser, a colon a human naturally typed into a prose
> reason HARD-HALTS the pipeline at the finish line — a fully-waived feature cannot certify. The
> current mitigation is prose discipline ("quote colon-bearing values"), exactly the
> human-remembered invariant the harness mission says to replace with a mechanical guarantee.

**Status:** Concluded
**Severity:** P0
**Discovered:** 2026-07-04
**Placement:** docs/bugs/skip-mcp-test-frontmatter-unquoted-colon
**Related:** `user/scripts/lazy_core.py` (`parse_sentinel` line ~817 — the `yaml.safe_load` + `_die` on `YAMLError`; `skip_waiver_refusal`; `evaluate_completion_evidence`); `user/scripts/lazy-state.py` (Step-9 completion leg lines ~3336 & ~3361 — `skip_waiver_refusal(parse_sentinel(skip_mcp_file) …)`); `bug-state.py` (mirrored Step-9 read); `user/skills/_components/sentinel-frontmatter.md` (canonical sentinel schema — mirror AlgoBooth `check-docs-consistency.ts` / `check-bugs-consistency.ts` if the tolerance changes; those validators live in AlgoBooth, NOT this repo). Recurring-friction origin: the parallel-worktree-batch-execution + friction-kpi-registry lane HANDOFFs both carry the standing warning "SKIP_MCP_TEST.md (quote YAML values with colons!)".

<!-- Status lifecycle:
  - Investigating → root cause not yet proven; /spec-bug owns the root-cause investigation.
  - Concluded     → root cause proven, affected area + fix scope understood; ready for /plan-bug.
-->

---

## Problem

The sentinel frontmatter reader is strict YAML. YAML treats an unquoted `: ` (colon followed by a
space) inside a scalar as a mapping-value indicator, so a value like:

```yaml
---
kind: skip-mcp-test
skipped_by: pipeline
reason: untestable on this host: no real audio device
---
```

raises a `yaml.scanner.ScannerError: mapping values are not allowed here`. `parse_sentinel`
converts every `yaml.YAMLError` into a `_die()` (a hard exit-2 halt), so the completion-time read
of `SKIP_MCP_TEST.md` never returns and a fully-waived feature cannot reach `Status: Complete` /
`Fixed`. The current mitigation is prose discipline ("quote colon-bearing values"), the kind of
human-remembered invariant the harness mission says to replace mechanically.

---

## Verified Symptoms

1. **[VERIFIED]** A `SKIP_MCP_TEST.md` with an unquoted colon-space in a value hard-halts the state
   script (exit 2, `_die("invalid YAML frontmatter: …")`) at the completion gate — proven by
   direct read of `parse_sentinel` (`lazy_core.py:816-820`) plus an empirical PyYAML repro (see
   Evidence). It does NOT silently mis-parse in the single-line colon-space case — it raises.
2. **[VERIFIED]** The failure surfaces at the very end of the lifecycle (the Step-9 / completion
   leg reads the waiver via `skip_waiver_refusal(parse_sentinel(skip_mcp_file), …)` at
   `lazy-state.py:3336` and `:3361`), so a colon in a prose reason wastes a full cycle — the
   feature is otherwise done.
3. **[VERIFIED]** It recurs across lanes because the only defense is authoring prose (the two lane
   HANDOFF warnings), not a parser/writer contract — a mechanical footgun, not a one-off.

## Reproduction Steps

1. Author a `SKIP_MCP_TEST.md` waiver whose `reason:` (or any value) contains a colon followed by
   a space, e.g. `reason: untestable on this host: no real audio device`.
2. Let the pipeline reach the completion / Step-9 validation leg (feature implemented, no
   `VALIDATED.md`, skip present).
3. `compute_state` calls `parse_sentinel(skip_mcp_file)` → `yaml.safe_load` raises `ScannerError`
   → `_die()`.

**Expected:** the waiver's prose reason is read tolerantly (an unquoted colon in a scalar treated
as a literal), the provenance gate evaluates, and the feature validates-from-skip.
**Actual:** the state script exits 2 with `invalid YAML frontmatter: mapping values are not
allowed here`, hard-halting the whole run (not a per-item halt — a malformed-input `_die`).
**Consistency:** always, for any value containing `: ` (colon-space) or a trailing colon. A colon
with NO following space (`reason: build:step`) is a valid plain scalar and does NOT trip it.

## Evidence Collected

### Source Code

- **`lazy_core.py:816-820` — the fault site.** `parse_sentinel` does
  `data = yaml.safe_load(yaml_body)` inside a `try`, and `except yaml.YAMLError as exc:` →
  `_die(f"invalid YAML frontmatter: {exc}", path)`. `_die` is a hard exit-2 halt (CLI contract:
  "exit 2 = malformed input"). There is NO tolerant pre-processing of scalar values.
- **`lazy-state.py:3336, :3361` — the completion-leg readers.** Both Step-9 branches call
  `skip_waiver_refusal(parse_sentinel(skip_mcp_file) or {}, repo_root)`. The `or {}` guards a
  `None` (absent file) return but CANNOT guard a `_die()` — `parse_sentinel` never returns on a
  `YAMLError`, it terminates the process. `bug-state.py` mirrors this read (coupled pair).
- **`lazy_core.py:3969-4000` — `__write_validated_from_skip__`** also `parse_sentinel(skip_path)`s
  the waiver, a second strict-parse chokepoint on the same file.
- **`evaluate_completion_evidence` (`lazy_core.py:2812-2816`)** only `.exists()`-checks
  `SKIP_MCP_TEST.md` via `_fail_closed_present()`, so the mis-parse is NOT in that function — the
  strict-parse halt is specifically in the Step-9 `skip_waiver_refusal` legs above.

### Runtime Evidence

Empirical PyYAML repro (this container, `python3`/PyYAML):

```
[colon-space in reason]        YAMLError -> ScannerError: mapping values are not allowed here
[skipped_by names a key:value] YAMLError -> ScannerError: mapping values are not allowed here
[quoted value (control)]       PARSED   -> {'kind':'skipped','skipped_by':'pipeline',
                                            'reason':'untestable on this host: no real audio device'}
```

The quoted control proves the fix target: quoting the value (or tolerant quote-on-read) makes the
identical content parse cleanly.

### Git History

Fresh bug directory (only `SPEC.md`, seeded this cycle). No prior fix attempts.

### Related Documentation

- `user/skills/_components/sentinel-frontmatter.md` §`SKIP_MCP_TEST.md` — the canonical schema
  (`reason: <one-line>`, `skipped_by`, `granted_by`, `spec_class`). Any read/write tolerance
  change must stay in lockstep with AlgoBooth's `check-docs-consistency.ts` /
  `check-bugs-consistency.ts` (`SENTINEL_SCHEMAS`) — those `.ts` validators are NOT in this repo.
- `user/scripts/CLAUDE.md` "Coupling Rule #4" — schemas kept in lockstep across
  `sentinel-frontmatter.md` ↔ the `.ts` validators ↔ `lazy_core.py`'s readers.
- The test-harness writer `_write_yaml_sentinel` (in both state scripts) is where a quote-on-write
  fix and its regression fixtures would land.

## Theories

### Theory 1: strict `yaml.safe_load` + `_die` on any scalar-embedded `: ` (colon-space)
- **Hypothesis:** `parse_sentinel`'s unconditional `yaml.safe_load` raises `ScannerError` on an
  unquoted colon-space value and `_die`s the run; the completion leg is the first place a
  human-authored prose `reason:` reaches it.
- **Supporting evidence:** direct read of `lazy_core.py:816-820`; empirical `ScannerError` repro;
  the two Step-9 call sites at `lazy-state.py:3336/3361`.
- **Contradicting evidence:** none.
- **Status:** **Confirmed.**

### Theory 2 (ruled out as the dominant mode): silent mis-parse into a nested mapping
- **Hypothesis:** the value mis-parses into `{reason: {…}}` and the gate reads the wrong shape.
- **Supporting evidence:** the original SPEC hypothesized this as an alternative.
- **Contradicting evidence:** for a single-line `reason: a: b`, PyYAML RAISES (`ScannerError`), it
  does not produce a nested mapping — proven empirically. A silent nested-mapping mis-parse needs
  a genuinely block-structured value (indented continuation), which the one-line prose reason is
  not. The real-world failure is the hard halt, not a silent mis-shape.
- **Status:** **Ruled Out** (as the observed failure mode; the hard `_die` is the actual symptom).

## Proven Findings

1. The fault is a single chokepoint: `parse_sentinel`'s `yaml.safe_load` + `_die`-on-`YAMLError`
   (`lazy_core.py:816-820`). Any sentinel — not just `SKIP_MCP_TEST.md` — with an unquoted
   colon-space value hard-halts every consumer; the waiver is simply the file a human hand-edits
   most often at the finish line.
2. The completion-leg blast radius is the two Step-9 `skip_waiver_refusal(parse_sentinel(...))`
   reads (`lazy-state.py:3336/3361`, mirrored in `bug-state.py`) plus
   `__write_validated_from_skip__`.
3. The `or {}` fallbacks at the call sites are inert against this bug — `_die` terminates before
   any `or {}` runs.

## Recommended Fix Direction (for /plan-bug)

⚖ policy: fix direction (read-tolerant vs quote-on-write vs both) → recommend **both
(defense-in-depth)**.

Rationale (completeness-first, D7 — this is scope/robustness, not a divergent user-visible
product decision, so it is recommended in-cycle rather than parked to NEEDS_INPUT; /plan-bug owns
the final call and may narrow):

- **Tolerant read (primary):** make `parse_sentinel` pre-process frontmatter so an unquoted
  colon-space in a *scalar value* is treated as a literal (quote-on-read), keeping strict schema
  semantics for keys/kinds. This fixes BOTH existing on-disk files and every future one, at the
  one chokepoint, and is the only direction that repairs a human-hand-authored waiver.
- **Quote-on-write (secondary):** the pseudo-skill / `_write_yaml_sentinel` writers emit
  colon-bearing values pre-quoted, so pipeline-authored artifacts are always valid YAML. Alone it
  does NOT cover human-authored files, which is why it is defense-in-depth rather than the primary.
- **Lockstep constraint:** whichever lands must keep `_components/sentinel-frontmatter.md` and the
  AlgoBooth `check-*-consistency.ts` validators in sync (Coupling Rule #4), and add a regression
  fixture to the in-file `--test` harness proving an unquoted-colon waiver parses AND the
  completion gate accepts it (both `lazy-state.py --test` and `bug-state.py --test`, since the
  read is a coupled pair).

Alternatives remain enumerated for /plan-bug to weigh; the three above are the full option set.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Sentinel parser (the fault) | `user/scripts/lazy_core.py` (`parse_sentinel` ~816-820) | Root cause — `yaml.safe_load` + `_die` on any colon-space value. Tolerant-read fix lands here. |
| Completion / Step-9 read legs | `user/scripts/lazy-state.py` (~3336, ~3361); `user/scripts/bug-state.py` (mirrored) | Where a human-authored waiver first reaches the strict parse → hard halt. Coupled pair. |
| Skip→validated pseudo-skill | `user/scripts/lazy_core.py` (`__write_validated_from_skip__` ~3969) | Second strict-parse chokepoint on the same file. |
| Quote-on-write surface | `_write_yaml_sentinel` in both state scripts | Where a defense-in-depth quote-on-write + its RED fixtures land. |
| Schema lockstep | `user/skills/_components/sentinel-frontmatter.md`; AlgoBooth `check-docs-consistency.ts` / `check-bugs-consistency.ts` | Must mirror any tolerance change (Coupling Rule #4). The `.ts` validators are in AlgoBooth, not this repo. |

## Open Questions

- None blocking `/plan-bug`. The lone design choice — read-tolerant vs quote-on-write vs both — is
  answered above (recommend both, defense-in-depth) and is scope-class, not a
  product-behavior fork; `/plan-bug` may narrow it during phase authoring.
