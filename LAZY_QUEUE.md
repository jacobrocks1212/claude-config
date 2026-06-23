# Lazy Queue — claude-config   (run active 🔒)

## Features (0)


## Bugs (3)

| # | item | state | sev |
|---|------|-------|------|
| 1 | [bug-pipeline-cycle-dispatch-omits-cycle-prompt-ref](docs/bugs/bug-pipeline-cycle-dispatch-omits-cycle-prompt-ref/SPEC.md) | Validate | P2 |
| | status: Validate · phase 2/2 · next: run mcp-test · `bug-state.py --emit-prompt` registers the cycle prompt in the by-reference registry but never surfaces the `@@lazy-ref` token, so `/lazy-bug` and `/lazy-bug-batch` dispatch every real-skill cycle by value — re-inlining 9.5–12K-char prompts the feature pipeline passes as a 49-char reference. | | |
| 2 | [adhoc-checkpoint-resume-field-complete-continuity](docs/bugs/adhoc-checkpoint-resume-field-complete-continuity/SPEC.md) | Spec | — |
| | status: Spec · next: spec | | |
| 3 | [adhoc-ensure-runtime-test-injects-signal-under-test](docs/bugs/adhoc-ensure-runtime-test-injects-signal-under-test/SPEC.md) | Spec | P1 |
| | status: Spec · next: spec | | |
