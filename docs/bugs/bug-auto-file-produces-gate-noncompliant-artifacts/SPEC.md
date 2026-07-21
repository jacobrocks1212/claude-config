# Auto-filed bug stubs violate the target repo's bugs-consistency gate

**Status:** Fixed
**Severity:** P2
**Discovered:** 2026-07-20
**Fixed:** 2026-07-20
**Fix commit:** a7a04ea6
**Related:** `docs/features/incident-auto-capture/SPEC.md`, `user/skills/_components/adhoc-enqueue.md`, `docs/specs/turn-routing-enforcement/`

## Trigger / reconstructed route

Manual `/harden-harness` invocation (trigger 5). Reported gap: every incident/ad-hoc bug
auto-file run leaves the AlgoBooth repo's `npm run qg:bugs-consistency` gate RED, and enqueues
queue entries the bug pipeline treats as inert.

The auto-file path is:

```
incident-scan.py::_enqueue
  → lazy-state.py --enqueue-adhoc --type bug   (enqueue_adhoc_bug)
    → bug-state.py --enqueue-adhoc             (enqueue_adhoc — writes queue.json entry)
  → seeds docs/bugs/<slug>/ADHOC_BRIEF.md
  → incident-scan seeds docs/bugs/<slug>/INCIDENT.md
```

Harden spin-offs (`/harden-harness` over-fit spin-off, `/spec-bug` route) and any manual
`adhoc-enqueue --type bug` use the SAME `enqueue_adhoc_bug` wrapper, so they share the defect.

## Verified symptom (two sub-gaps)

Both violate `scripts/check-bugs-consistency.ts` in the target repo (read-only inspection):

1. **`severity: null` (queue-schema rule).** `bug-state.py::enqueue_adhoc` unconditionally writes
   `"severity": severity` into the queue entry; the auto-file path never passes a severity, so the
   value is `null`. The gate's Rule 3 checks `if (e['severity'] !== undefined)` — a present-but-null
   value is `!== undefined`, so `QUEUE_SEVERITY_SET.has(null)` fails → `queue-schema` violation.
   (7 entries violating as of 2026-07-20.)

2. **No `SPEC.md` (queue-dangling-id rule).** The enqueued dir carries only `ADHOC_BRIEF.md` +
   `INCIDENT.md`, no `SPEC.md`. The gate counts a dir as an "open bug dir" only when it has a
   `SPEC.md` (`existsSync(join(entryPath, 'SPEC.md'))`), so every auto-filed queue id fails
   `queue-dangling-id` ("does not resolve to an open bug directory"). ≥5 entries violating.

## Root cause

`missing-contract` — the sanctioned ad-hoc/auto-file enqueue surface has no contract that its
produced artifacts be gate-ready. Two concrete defects:

- **Queue severity is written as a null OVERRIDE.** `merged_priority` (depdag.py) treats an explicit
  queue `severity` token as a **permanent override** of the SPEC's own `**Severity:**` (it only falls
  back to `spec_severity` past an expired *pin*). So neither writing `null` (gate-illegal) nor
  hard-coding `"Low"` (would pin the bug Low forever, suppressing `/spec-bug`'s later determination —
  exactly the divergence the gap flagged for `adhoc-dev-session-logs-no-app-rotation` /
  `adhoc-synth-track-analysis-returns-zero`, whose SPECs carry P1/P2) is correct. The queue key must
  be **omitted** when there is no explicit operator override, leaving the SPEC as the source of truth.

- **The enqueue seeds no SPEC.md.** The pipeline design (`adhoc-enqueue.md`) is stub-then-expand:
  `/spec-bug` authors the full SPEC. But bug-state routing already references `<dir>/SPEC.md` as the
  `STEP_INVESTIGATE` dispatch arg and the target repo's gate requires a SPEC.md for the dir to be a
  lifecycle bug. So a **gate-compliant stub SPEC.md** must exist at enqueue time (Status +
  Severity + Discovered), which `/spec-bug` then overwrites. Deferring the enqueue until a SPEC exists
  would contradict the stub-then-expand contract (the ADHOC_BRIEF.md → `/spec-bug` routing is the
  mechanism that produces the SPEC), so authoring the stub is the design-consistent choice.

## Fix scope

Harness-only (claude-config), at the shared enqueue choke points:

1. `bug-state.py::enqueue_adhoc` — OMIT the `severity` key when None/empty (write it only for an
   explicit token). Fixes `queue-schema` for every enqueue caller (incident, harden, materialize).
2. `lazy-state.py::enqueue_adhoc_bug` — seed a minimal gate-compliant stub `SPEC.md`
   (`**Status:** Investigating` / `**Severity:** <passed-or-Low>` / `**Discovered:**`) beside the
   ADHOC_BRIEF.md (idempotent). Fixes `queue-dangling-id` + status/severity-canonical for the
   incident + harden paths (the reported gap). Shared `_adhoc_stub_spec()` helper.
3. `lazy-state.py::materialize_wi` (near-neighbor, same class) — make its bug-route stub SPEC
   gate-compliant via the same helper (feature route unchanged; WI provenance line preserved).

The collector (incident-scan.py) stays severity-agnostic — its INCIDENT.md capsule already documents
"the collector never sets severity"; the stub default (Low) lives in the enqueue wrapper.

## Regression coverage

- `lazy-state.py --test` (`enqueue-bug` fixture): stub SPEC.md exists + gate-compliant header + queue
  entry omits the null severity key.
- `test_incident_scan.py::test_end_to_end_enqueue_stub_and_capsule`: assert the seeded dir carries a
  gate-compliant SPEC.md and the queue entry has no `severity` key.
- `bug-state.py --test` fixtures 12/13 pass explicit severities — unchanged (present tokens still written).
