"""pipeline_visualizer — a local web control-plane for the lazy feature/bug pipelines.

A thin stdlib-only renderer over the existing lazy-state.py / bug-state.py JSON
contract. State is NEVER re-inferred here — the backend shells the existing state
scripts and parses their output, attaching a display-only `curated_stage`.

See docs/features/lazy-pipeline-visualizer/SPEC.md for the design.
"""
