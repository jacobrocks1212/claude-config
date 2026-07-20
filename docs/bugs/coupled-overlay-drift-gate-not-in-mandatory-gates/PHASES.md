# Implementation Phases — Wire the coupled-overlay drift gate into the mandatory gate battery

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — claude-config has no Tauri/MCP server; validation is the repo's own Python test+lint suite plus the gate battery itself (see `.claude/skill-config/quality-gates.md` §MCP exemption). This is a config-manifest + docs + test change with no MCP-reachable surface.

## Cross-feature Integration Notes

No hard deps on Complete upstreams — the SPEC's `**Related:**` list is prior-art references, not a `**Depends on:**` block. The consumed gate `generate-coupled-skills.py --check` already exists and is exit-coded (0 ok / 1 drift / 2 malformed); this feature only registers it, it does not modify it.

## Validated Assumptions

- **The battery runs precisely the manifest's gates.** Verified by reading `user/scripts/gate-battery.py` (`_load_manifest` reads `<toplevel>/.claude/skill-config/gate-battery.json`; `main()` loops `for gate in gates`). A gate absent from the manifest never runs; adding a manifest row is sufficient to make the battery run it. (Code-provable — static config read; confirmed by the SPEC's serving-path trace and by direct read of the manifest + runner.)
- **`generate-coupled-skills.py --check --repo-root .` currently exits 0 on the committed tree** — confirmed by direct run: `coupled-pair generation: all pairs byte-identical (fresh)  EXIT=0`. So adding it to the mandatory battery does NOT break the green baseline; it only starts catching FUTURE drift. (Runtime-observed — ran the command.)

---

### Phase 1: Register the coupled-overlay drift gate in the mandatory battery (+ prose + count + recurrence guard)

**Scope:** Add `generate-coupled-skills.py --check` as a mandatory gate in the battery manifest, name it in the coupled-pair prose gate list so a human/agent following the prose also runs it, correct the now-stale "7-command invariant battery" doc claims, and add a recurrence-guard test so the gate cannot be silently removed again. This is the durable prevention the archived sibling bug (`coupled-overlays-drift-from-committed-skills`) spun this bug off to deliver.

**Deliverables:**
- [ ] Add an 8th gate row to `.claude/skill-config/gate-battery.json` invoking the drift gate, e.g. `{ "id": "coupled-overlay-drift", "cmd": "python3 user/scripts/generate-coupled-skills.py --check --repo-root ." }`. Keep it a peer of the existing `parity-audit` row (both are coupled-surface drift gates), placed after it.
- [ ] Name the drift gate in the coupled-pair prose gate list in `.claude/skill-config/quality-gates.md` — in the "Lazy skill-family changes" section (currently names only `lazy_parity_audit.py --report`) and the "Mixed / feature completion" FULL-set line, so `generate-coupled-skills.py --check` is listed alongside `lazy_parity_audit.py` as the coupled-overlay drift check.
- [ ] Correct the stale battery-count prose (bump `7`→`8`, OR reword to drop the hardcoded count for future-proofing) at `CLAUDE.md:259`, `user/scripts/CLAUDE.md:56`, and `user/scripts/CLAUDE.md:158`. If `docs/features/.../generalized-build-test-runner-skills` SPEC L5 hardcodes the same count AND the CLAUDE.md rows cite it as authority ("SPEC L5"), keep the citation internally consistent (either reword the CLAUDE.md to not cite a specific number, or note the count moved).
- [ ] Add a recurrence-guard test to `user/scripts/tests/test_gate_battery.py` asserting the committed claude-config `.claude/skill-config/gate-battery.json` manifest contains a gate whose `cmd` invokes `generate-coupled-skills.py --check` (a config-invariant test that reads the real repo manifest, distinct from the runner's hermetic-tmp tests). This is the mechanical guard against a future silent removal of the row — the exact failure class this bug fixes.
- [ ] Tests: the recurrence-guard test above (RED before the manifest edit, GREEN after) plus the full battery re-run confirming 8 gates all pass on the clean tree.

**Minimum Verifiable Behavior:** `python3 user/scripts/gate-battery.py` (run from the repo root, or the 8 gates individually) reports `cmds=8` in its outcome banner with `RESULT=PASS`, and `python3 user/scripts/generate-coupled-skills.py --check --repo-root .` is one of the gates that ran.

**Runtime Verification** *(checked by running the battery — NOT by the implementation agent):*
- [ ] <!-- verification-only --> After adding the gate row, running the full battery reports `cmds=8` and `RESULT=PASS` on the clean committed tree (baseline stays green — the gate catches future drift, not the current tree).
- [ ] <!-- verification-only --> Drift is now caught by the mandatory battery: deliberately mutate a canonical coupled SKILL.md WITHOUT re-extracting its overlay (or otherwise induce overlay drift), run the battery, and confirm it now FAILS naming the `coupled-overlay-drift` gate — then revert the deliberate mutation. This is the SPEC's reproduction step 3-5, now expected to fail-fast instead of passing green.

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface in this repo (config manifest + docs + Python test).

**Prerequisites:** None (single-phase fix).

**Files likely modified:**
- `.claude/skill-config/gate-battery.json` — add the drift-gate row (the primary fix site; the exact artifact `gate-battery.py::_load_manifest` reads).
- `.claude/skill-config/quality-gates.md` — name the drift gate in the coupled-pair prose gate list.
- `CLAUDE.md` — correct the stale "7-command invariant battery" claim (line ~259).
- `user/scripts/CLAUDE.md` — correct the stale battery-count claims (lines ~56, ~158).
- `user/scripts/tests/test_gate_battery.py` — add the recurrence-guard test.

**Testing Strategy:**
1. Recurrence-guard unit test (TDD): assert the committed manifest contains the drift gate — RED before the JSON edit, GREEN after.
2. Full-battery re-run: `python3 user/scripts/gate-battery.py` from the repo root → `cmds=8`, `RESULT=PASS`.
3. Drift-catch spot check (Runtime Verification row): induce overlay drift, confirm the battery fails naming the new gate, revert.
4. Consistency re-check: `python3 user/scripts/doc-drift-lint.py --repo-root .` and `python3 user/scripts/cli-surface-lint.py --repo-root .` stay clean after the manifest + doc edits (per the SPEC Affected Area note).

**Completion (gate-owned):** the `__mark_fixed__` gate flips SPEC.md `**Status:**` to Fixed and writes `FIXED.md` once this phase's verification passes and the validation tail runs — this plan never flips top-level status itself.

**Integration Notes for Next Phase:** None — single-phase fix.
