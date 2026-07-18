# SubagentStop Wedge-Backstop Hook — Phases

**Status:** Ready

Single-phase feature — a contained hook + its registration + hermetic tests. The design is fully
specified in SPEC.md (operator-authorized decision #14, claude-code-guide-confirmed mechanism), so
this routes straight to `/write-plan` → `/execute-plan`.

**MCP runtime:** not-required — a harness hook validated by hermetic `test_hooks.py` fixtures
(synthetic hook-input JSON + temp repo/marker/plan), no Tauri/MCP app surface (standalone — no app
integration, per the untestable class in `docs/features/mcp-testing/SPEC.md`).

---

### Phase 1: SubagentStop wedge-backstop hook + loop-guard + registration + tests
**Status:** Not started
**Phase kind:** design

Implement the authorized option: a fail-open `SubagentStop` hook that blocks a genuinely-wedged
dispatched subagent at most once (breadcrumb keyed on the documented `agent_id`), forcing it to
commit + complete or write `BLOCKED.md` instead of returning dead.

- [ ] `user/hooks/subagent-wedge-backstop.sh` — `SubagentStop` hook reading the input JSON
  (`agent_id`, `cwd`, `session_id`); resolves the repo from `cwd`.
- [ ] **Predicate:** block only when (run marker present for the repo) AND (active plan status
  != `Complete`) AND (git working tree dirty OR plan has unchecked WU checkboxes). Otherwise
  exit 0 (allow).
- [ ] **Loop-guard:** self-managed breadcrumb at an absolute path outside any repo
  (`<claude-state>/subagent-stops/<agent_id>.json`); block at most ONCE per `agent_id` (present
  breadcrumb ⇒ allow the stop). NO dependency on the undocumented `stop_hook_active`.
- [ ] **Block action:** exit 2 with an actionable `reason` ("stopping with pending plan work;
  commit + complete or write BLOCKED.md, then stop"); write the breadcrumb before blocking.
- [ ] **Fail-open:** any error / missing field / unresolvable repo / breadcrumb I/O failure ⇒
  exit 0 (allow). The hook can never wedge the pipeline.
- [ ] Register in `user/settings.json` under a `SubagentStop` key (matcher `*`); keep the
  settings schema valid.
- [ ] **Breadcrumb lifecycle:** GC on genuine completion (a `SessionEnd` cleanup path and/or a
  staleness sweep); GC failure is non-fatal.
- [ ] **Tests** in `test_hooks.py`: predicate-true→block-once; second-attempt(same `agent_id`)→
  allow; fail-open on malformed input / missing `agent_id`; clean-tree-or-Complete-plan→allow;
  no-marker→allow; two distinct `agent_id`s→independent breadcrumbs. Cite the claude-code-guide
  confirmation (agent_id documented/stable; stop_hook_active NOT used) in an implementation note.

**Gates:** `test_hooks.py` (new cases green), `lint-skills.py` OK (if any skill prose references the
hook), `lazy-state.py`/`bug-state.py --test` OK, and validate `user/settings.json` parses with the
new `SubagentStop` registration.
