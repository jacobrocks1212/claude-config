---
kind: implemented
feature_id: generalized-build-test-runner-skills
date: 2026-07-14
provenance: pipeline-gated
derivation: message-grep
commits: [abb6a6d, ebb0e76, 8a053ac, 3e43787, 16366c8]
decisions: [L1, L2, L3, L4, L5, L6, L7, L8]
---

# Implementation Ledger

**What shipped:** Generalize the Cognito build/test skill system's outcome contract — authoritative last-line banner + followable await + turn-end gate — to claude-config's 7-command gate battery and AlgoBooth's heavy `qg` quality gates, as ONE documented contract instantiated per repo. Additive only: the working Cognito system is byte-untouched.

**Decisions that drove it:**
- L1 — The generalization deliverable is ONE documented contract — `user/skills/_components/runner-outcome-contract.md` (banner grammar + followable await with 124/125 semantics + turn-end gate BY REFERENCE to `_components/turn-end-gate.md`, never copied) — instantiated per repo; the cross-repo seam is the documented grammar, not shared code.
- L2 — **PARK-PROVISIONAL (ratification pending):** light ops (claude-config battery, AlgoBooth `qg -- ts` / `qg -- docs`) get runner+banner+await WITHOUT machine-global queue admission; heavy AlgoBooth gates (`qg -- rust`, `qg -- sidecar`) join the existing queue as manifested ops. The queue manifest gains no "unserialized" lane value.
- L3 — **PARK-PROVISIONAL (ratification pending):** hook-deny only for heavy manifested ops (additive AlgoBooth `deny` rows on the existing manifest machinery); raw light invocations (`pytest user/scripts/`, `npm run qg -- ts` / `-- docs`) are NEVER hook-denied — advisory routing only. **D3-precision addendum (planning-time, 2026-07-13):** deny rows cover ONLY the exact heavy forms (`npm run qg -- rust\
- L4 — **PARK-PROVISIONAL (ratification pending):** the claude-config battery runner is stdlib-only cross-platform Python (`user/scripts/gate-battery.py`) conforming to the contract grammar independently of the PowerShell queue plane; it must run in cloud sessions (queue stays workstation-only per locked D7).
- L5 — Battery command SSOT is the committed per-repo `.claude/skill-config/gate-battery.json`; the runner refuses without one (manifest-less repo unaffected by construction); claude-config seeds it with the 7-command battery as commands (stable contract), not file paths.
- L6 — Cognito Forms is byte-untouched: no edits to its manifests, skills, `build-queue*.ps1` behavior, or the enforce hook's legacy fallback; all 5 Pester suites must stay green as a completion gate.
- L7 — Sequencing: implementation begins only after `lazy-core-package-decomposition` completes (hard dep, machine-enforced via `--sync-deps` at `/spec-phases` Step 1.6).
- L8 — Required MCP tooling: none — every Validation Criteria row is CLI/pytest/Pester-verifiable; claude-config has no MCP runtime (Step 9 exemption via operator-granted `SKIP_MCP_TEST.md` per `.claude/skill-config/quality-gates.md`), and no MCP tool must exist or be built for this feature's validation.

**Validated via: mcp. Receipt: COMPLETED.md (provenance: gated).**
