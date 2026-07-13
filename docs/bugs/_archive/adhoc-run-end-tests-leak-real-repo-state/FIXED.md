---
kind: fixed
feature_id: adhoc-run-end-tests-leak-real-repo-state
date: 2026-07-13
provenance: operator-directed-interactive
validated_via: pytest (test_lazy_core.py 1125/1125 bare; 8/8 targeted under marker-polluted LAZY_STATE_DIR; real-state-dir zero-diff snapshot); NOT pipeline-gated (__mark_fixed__)
auto_ticked_rows: 0
---

# Completion Receipt

`adhoc-run-end-tests-leak-real-repo-state` marked fixed on 2026-07-13, fix commit `5e7c8793`.

Root cause (traced in SPEC.md): the `test_p7_run_end_*` (7) +
`test_marker_present_cli_absent_then_present_and_readonly` (1) hermetic subprocess tests in
`user/scripts/test_lazy_core.py` isolated only `LAZY_STATE_DIR`, never `--repo-root` — so every
`lazy-state.py` subprocess bound to `os.getcwd()`, the REAL claude-config checkout. The shared
`_seed_efficacy_breadcrumb` helper's `interventions_covered` flag passed only via a REAL read of
the real repo's `docs/interventions/*.md`; and 2 of the 8 tests never seeded the breadcrumb, so
they silently validated the earlier-positioned efficacy gate (whose refusal text literally
instructs running `efficacy-eval.py`/`incident-scan.py` against the real repo) instead of the
checkpoint/terminal-reason stop-authorization gates their names and docstrings claim.

## What shipped (one commit, `5e7c8793` — test-only; production code unchanged)

1. All 8 tests now mkdir a hermetic temp `repo_dir` and pass `--repo-root <repo_dir>` on every
   subprocess leg (never the argparse `os.getcwd()` default).
2. `_seed_efficacy_breadcrumb` seeds its OWN disposable interventions-bearing fixture dir (a
   sibling of the test's state dir, carrying a throwaway `docs/interventions/adhoc-test-fixture.md`)
   and passes it explicitly as `covered_repo_root=` — the crumb's coverage flag no longer depends
   on the marker's `repo_root` or the real repo. Signature unchanged; all pre-existing call sites
   unaffected.
3. The 2 masked tests seed the breadcrumb before their asserting `--run-end` and pin their
   assertions to the specific gate (`"Stop-authorization gate"` substring + `attended: true` echo /
   the named non-sanctioned reason), so a future re-masking fails loudly.

## Symptom reproduction — evidence the defect is gone

**Original symptom:** pre-fix, the exact subprocess sequence of
`test_p7_run_end_checkpoint_attended_no_auth_refuses` refused via the EFFICACY gate
(`"No efficacy-flush breadcrumb COVERING THE INTERVENTIONS-BEARING SCOPE …"` — naming real-repo
commands), not the checkpoint gate; and the breadcrumb helper read the real
`docs/interventions/`.

**Post-fix, same surface:** the same sequence now refuses via
`"Stop-authorization gate: this is an ATTENDED run …"` with `"attended": true` — the gate the
test exists to pin — with `--repo-root` bound to a temp fixture and the breadcrumb derived from a
disposable fixture dir. Serving-path regression coverage: the strengthened assertions in both
previously-masked tests fail on any refusal other than their own gate's.

**Verification (PHASES.md Runtime Verification, all green):**
- Targeted: `-k "test_p7_run_end or test_marker_present"` → 8 passed.
- Full bare suite → 1125 passed.
- 8/8 green under a marker-polluted process-level `LAZY_STATE_DIR` (synthetic live run +
  cycle markers). The full suite's 75 failures under that non-contractual polluted override were
  PROVEN pre-existing (git-stash pre-fix repro of 2 of them, same refusal text) — out of scope.
- Real `~/.claude/state/` sha256+mtime snapshot byte-identical before-first-run vs after-last-run.
- `lazy_parity_audit.py --repo-root .` exit 0; `doc-drift-lint.py --repo-root .` exit 0.
