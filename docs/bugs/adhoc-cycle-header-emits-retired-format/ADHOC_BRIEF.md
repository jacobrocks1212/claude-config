---
kind: adhoc-brief
bug_id: adhoc-cycle-header-emits-retired-format
enqueued_by: lazy-adhoc
date: 2026-07-12
---

# Ad-hoc bug: State scripts emit the retired '### Cycle fwd N/M' cycle_header format

The lazy/bug state scripts emit a cycle_header field in the retired '### Cycle fwd N/M meta K id skill' format, but orchestrator-voice.md retired that heading ('must not reappear') for the T2 format '### Step — summary [n/max]'. The script-emitted cycle_header contradicts the binding output contract; orchestrators echoing it verbatim per the probe-presence guard would violate orchestrator-voice.md. Reconcile emit_cycle_header to the T2 shape or bless the field in the contract. Observed during /lazy-bug-batch run 2026-07-12.
