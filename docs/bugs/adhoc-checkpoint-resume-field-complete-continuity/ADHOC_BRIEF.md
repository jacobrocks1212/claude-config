---
kind: adhoc-brief
bug_id: adhoc-checkpoint-resume-field-complete-continuity
enqueued_by: lazy-adhoc
date: 2026-06-23
---

# Ad-hoc bug: Checkpoint resume continuity is field-by-field, not field-complete

Class: a sanctioned same-run checkpoint resume (non-operator-authorized) continues the SAME run, but write_run_marker unconditionally re-mints all run-scoped marker state on the resuming --run-start, so every continuity field must be carried back individually by restore_checkpoint_counters. This has now been patched reactively TWICE after a field was found un-restored: the 2026-06-14 operator-checkpoint-resume-counter-reset fix restored forward_cycles/meta_cycles/last_advance_consume_count, and hardening Round 35 (2026-06-23, commit 821628e) restored started_at (the run identity) after it false-tripped detect_cycle_bracket_friction signal (a) cycle-bracket-break (begin 03:15:38Z != end 05:41:28Z, jog-wheel-nudging). Each fix is whack-a-mole on one field. Durable fix: make checkpoint-resume continuity field-complete BY CONSTRUCTION - e.g. snapshot the full set of run-continuity fields into the checkpoint at write time and restore them as one unit in the carry-forward branch, with an explicit enumerated allow-list of which marker fields are run-scoped-fresh (reset) vs run-continuity (carried), so a newly added marker field cannot silently default to the reset side. Class boundary IN: any marker field that must be continuous across a non-operator-authorized same-run checkpoint resume (counters, watermark, started_at identity, and any future continuity field). OUT: the operator-authorized resume path (genuinely a NEW run wanting a fresh 0/0 budget and fresh identity - left intact), and the cross-pipeline clobber refusal (refuse_run_start_clobber, Round 19). Origin: hardening Round 35 + the 2026-06-14 counter-reset round; restore_checkpoint_counters / write_run_checkpoint in user/scripts/lazy_core.py.
