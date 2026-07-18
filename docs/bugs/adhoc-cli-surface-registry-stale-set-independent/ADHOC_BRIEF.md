---
kind: adhoc-brief
bug_id: adhoc-cli-surface-registry-stale-set-independent
enqueued_by: lazy-adhoc
date: 2026-07-18
---

# Ad-hoc bug: cli-surface.json stale: --set-independent shipped without registry regen

cli_surface_gen.py --check fails (2 tests): the committed docs/cli/cli-surface.json was not regenerated when the --set-independent flag landed on the state scripts (harden round 9d46a357). Fix: run cli_surface_gen.py to regenerate + commit, and check whether the harden-harness gate list should include cli_surface_gen.py --check so a CLI-flag add cannot ship without its registry regen.
