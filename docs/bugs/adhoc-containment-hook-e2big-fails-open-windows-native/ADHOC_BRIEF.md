---
kind: adhoc-brief
bug_id: adhoc-containment-hook-e2big-fails-open-windows-native
enqueued_by: lazy-adhoc
date: 2026-07-18
---

# Ad-hoc bug: lazy-cycle-containment.sh E2BIG fail-open on Windows-native Git Bash

Round 90 finding: on Windows-native Git Bash the containment hook passes its ~35KB python body via python3 -c "$_LCC_PY", exceeding the ~32KB Windows command-line limit, so the exec fails E2BIG and the hook fails OPEN - the lazy cycle containment plane is silently DISARMED on Windows-native hosts (22 pre-existing test_hooks E2BIG failures reproduce it). Fix shape per the finding: deliver the python body via stdin or a temp file instead of -c, keeping fail-open semantics for genuine errors; add a regression test asserting the hook arms on a Windows-size command line.
