# SubagentStop Wedge-Backstop Hook — Phases

**Status:** Complete

Single-phase feature — a contained hook + its registration + hermetic tests. The design is fully
specified in SPEC.md (operator-authorized decision #14, claude-code-guide-confirmed mechanism), so
this routes straight to `/write-plan` → `/execute-plan`.

**MCP runtime:** not-required — a harness hook validated by hermetic `test_hooks.py` fixtures
(synthetic hook-input JSON + temp repo/marker/plan), no Tauri/MCP app surface (standalone — no app
integration, per the untestable class in `docs/features/mcp-testing/SPEC.md`).

---

### Phase 1: SubagentStop wedge-backstop hook + loop-guard + registration + tests
**Status:** Complete
**Phase kind:** design

Implement the authorized option: a fail-open `SubagentStop` hook that blocks a genuinely-wedged
dispatched subagent at most once (breadcrumb keyed on the documented `agent_id`), forcing it to
commit + complete or write `BLOCKED.md` instead of returning dead.

- [x] `user/hooks/subagent-wedge-backstop.sh` — `SubagentStop` hook reading the input JSON
  (`agent_id`, `cwd`, `session_id`); resolves the repo from `cwd`.
- [x] **Predicate:** block only when (run marker present for the repo) AND (active plan status
  != `Complete`) AND (git working tree dirty OR plan has unchecked WU checkboxes). Otherwise
  exit 0 (allow).
- [x] **Loop-guard:** self-managed breadcrumb at an absolute path outside any repo
  (`<claude-state>/subagent-stops/<agent_id>.json`); block at most ONCE per `agent_id` (present
  breadcrumb ⇒ allow the stop). NO dependency on the undocumented `stop_hook_active`.
- [x] **Block action:** exit 2 with an actionable `reason` ("stopping with pending plan work;
  commit + complete or write BLOCKED.md, then stop"); write the breadcrumb before blocking.
- [x] **Fail-open:** any error / missing field / unresolvable repo / breadcrumb I/O failure ⇒
  exit 0 (allow). The hook can never wedge the pipeline.
- [x] Register in `user/settings.json` under a `SubagentStop` key (matcher `*`); keep the
  settings schema valid.
- [x] **Breadcrumb lifecycle:** GC on genuine completion (a `SessionEnd` cleanup path and/or a
  staleness sweep); GC failure is non-fatal.
- [x] **Tests** in `test_hooks.py`: predicate-true→block-once; second-attempt(same `agent_id`)→
  allow; fail-open on malformed input / missing `agent_id`; clean-tree-or-Complete-plan→allow;
  no-marker→allow; two distinct `agent_id`s→independent breadcrumbs. Cite the claude-code-guide
  confirmation (agent_id documented/stable; stop_hook_active NOT used) in an implementation note.

**Gates:** `test_hooks.py` (new cases green), `lint-skills.py` OK (if any skill prose references the
hook), `lazy-state.py`/`bug-state.py --test` OK, and validate `user/settings.json` parses with the
new `SubagentStop` registration.

#### Implementation Notes (2026-07-18)

**Work completed.** Shipped `user/hooks/subagent-wedge-backstop.sh` (fail-open SubagentStop hook,
embedded-Python-via-`-c` on the `lazy-cycle-containment.sh` pattern) + 12 hermetic `test_wedge_*`
cases in `user/scripts/test_hooks.py`; registered under `SubagentStop (*)` + `SessionEnd (*)` in
`user/settings.json`; added the `subagent-wedge-backstop.sh` root-`CLAUDE.md` Hooks-table row and
bumped the `user/hooks/CLAUDE.md` "python-bearing hooks" count 7→8 (this is the 8th).

**Key decisions / integration.**
- **Block = exit 2, NOT deny-JSON.** SubagentStop's documented block mechanism is exit code 2 +
  a stderr `reason` (confirmed by claude-code-guide, 2026-07-17). Unlike the PreToolUse command
  guards in this dir (where a non-zero exit is a hard error and deny is JSON), the bash wrapper
  here `exit $?`-PROPAGATES python's exit code. Tests assert the SUBPROCESS EXIT CODE (2/0).
- **Loop-guard keys on `agent_id`, never `stop_hook_active`.** `stop_hook_active` is undocumented
  for SubagentStop (absent from its input schema); the hook header comment cites the confirmation.
  Breadcrumb at `<claude-state>/subagent-stops/<agent_id>.json` (OUTSIDE any repo, so it never
  dirties the tree the predicate inspects); a present breadcrumb ⇒ allow (block at most once). A
  breadcrumb WRITE failure ⇒ allow (never block without a persisted guard, else infinite loop).
- **Active-plan resolution.** `docs/{features,bugs}/*/plans/*.md` globbed; a Complete/Superseded/
  Draft plan is excluded from "active", so a non-empty active set ⇒ predicate condition 2 (status
  != Complete). Fail-open bias: no active plan resolves / no marker / no lazy_core import / git
  error ⇒ allow (false-negative preferred over false-positive per the operator steer).
- **Breadcrumb lifecycle.** Entry staleness sweep (24h) + a SessionEnd-mode branch (agent_id
  absent, session_id present ⇒ GC that session's breadcrumbs); GC failure non-fatal.

**Pitfalls / gotchas.**
- **Embedded `-c` body must stay SMALL.** On this Windows Git-Bash box, `python -c "<huge body>"`
  hits `Argument list too long` (~32KB CreateProcess limit) — this is exactly why the 22
  pre-existing `test_containment_*` deny tests fail on this machine (`lazy-cycle-containment.sh`'s
  ~680-line body blows the limit and the hook fail-opens). This hook's body is 8.4KB, well under
  the limit, so it runs. **The containment arg-length fragility is a PRE-EXISTING harness defect,
  unrelated to this feature** — flagged for a separate `/harden-harness` pass (candidate fix:
  factor the containment python into a sibling `.py` file like `lazy_guard.py`).

**Files modified.** `user/hooks/subagent-wedge-backstop.sh` (new), `user/scripts/test_hooks.py`
(+12 `test_wedge_*` cases, `_WEDGE_SH` added to the python-bearing no-python sweep),
`user/settings.json` (SubagentStop + SessionEnd registration), `CLAUDE.md` (Hooks-table row),
`user/hooks/CLAUDE.md` (7→8 python-bearing-hook count + enumerated list).

**Validation:** MCP not-required (no runtime rows). Gates green: `test_hooks.py` 12/12 new +
no-python sweep; `doc-drift-lint.py` exit 0; `lazy-state.py`/`bug-state.py --test`; `lint-skills.py`;
`settings.json` parses.
