# CLAUDE.md — docs/specs/

Design specs for harness improvements implemented **outside the autonomous lazy pipeline** — by
hand or in a normal session. Unlike `docs/features/`, this directory has **no `queue.json`** and
is not walked by `lazy-state.py`.

Use it for a harness change you're designing and implementing directly, where you want a durable
spec but don't want the lazy state machine to pick it up.

- One `<slug>/` per spec, kebab-case (e.g. `turn-routing-enforcement`, `lazy-hardening`).
- If a spec should instead run through the autonomous pipeline, put it under `docs/features/` and
  add it to that queue — see `docs/features/CLAUDE.md`.
