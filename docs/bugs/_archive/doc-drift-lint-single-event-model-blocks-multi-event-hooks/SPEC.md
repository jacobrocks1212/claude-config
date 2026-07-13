# Bug: doc-drift-lint `check_hooks` single-event model blocks multi-event hooks

**Status:** Fixed
**Severity:** Low
**Discovered:** 2026-07-12
**Component:** `user/scripts/doc-drift-lint.py::check_hooks`
**Origin:** harden-harness (manual, trigger 5) — friction hit during the
`live-settings-split-brain-disarms-enforcement-plane` bug fix.

## Reconstructed route (Step 1)

`check_hooks` parses each root-`CLAUDE.md` `## Hooks` Trigger cell with `_TRIGGER_RE`
(`.search` — a SINGLE `Event (Matcher)` clause) and then asserts:

```python
reg_events = registered[name]
if set(reg_events) != {doc_event}:
    findings.append(... "documented under event %s but registered under %s" ...)
```

`registered[name]` is the FULL `{event: matcher_set}` map read from `user/settings.json`.
When a hook is registered under **multiple events**, `set(reg_events)` is a multi-element
set that can never equal the single-element `{doc_event}`, so the row is drift by
construction — there is no Trigger-cell spelling that validates it.

## Verified symptom

`lazy-route-inject.sh` is legitimately registered under THREE events in
`user/settings.json`:

- `UserPromptSubmit` (no matcher → matches-all)
- `SessionStart` matcher `compact`
- `PostCompact` (no matcher → matches-all)

To land the `live-settings-split-brain-disarms-enforcement-plane` fix drift-clean, its
`## Hooks` row had to carry the `doc-drift:deliberate-divergence` marker documenting only
`UserPromptSubmit (*)` in the machine-parsed cell and the other two events in prose — an
honest but unsatisfying escape hatch masking a real linter limitation, not a genuine
doc/reality divergence.

## Root cause (Step 2)

**script-defect** — `check_hooks` models each documented hook as registered under exactly
one event (`_TRIGGER_RE.search` + `set(reg_events) != {doc_event}`). The check has no
representation for a multi-event hook even though `_fmt_events` already emits the
semicolon-separated multi-clause form (`"UserPromptSubmit (*); SessionStart (compact);
PostCompact (*)"`) on the registered side. Evidence: `doc-drift-lint.py:255` (`.search`),
`:262` (`doc_event, doc_matchers = m.group(1), ...`), `:270` (`set(reg_events) != {doc_event}`).

## Proposed fix scope (Concluded)

Extend `check_hooks` to parse ALL `Event (Matcher)` clauses in a Trigger cell (via
`_TRIGGER_RE.findall`, semicolon-separated, matching `_fmt_events` output) and compare the
full documented `event -> matcher` map against `registered[name]`. Constraints:

- Single-event path stays **byte-identical** (branch on clause count; existing rows and
  their exact finding messages unchanged).
- `NOT registered` path unchanged.
- `*`-matcher (empty registered matcher set = matches-all) semantics preserved — an empty
  registered matcher set skips the per-event matcher comparison.
- Multi-event drift (a documented event not registered, or a registered event not
  documented) is a set-inequality finding; a per-event matcher mismatch is its own finding.

Then retire the `doc-drift:deliberate-divergence` marker on the `lazy-route-inject.sh`
row and document all three events in its Trigger cell, contingent on
`doc-drift-lint.py --repo-root .` staying exit 0 (incl. `test_this_repo_is_clean`).

## Gates

- `python3 -m pytest user/scripts/test_doc_drift_lint.py -q`
- `python3 user/scripts/doc-drift-lint.py --repo-root .` (exit 0)
- `python3 user/scripts/lint-skills.py`
