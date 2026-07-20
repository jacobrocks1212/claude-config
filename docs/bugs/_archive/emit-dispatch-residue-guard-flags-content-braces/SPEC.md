# Bug: emit_dispatch_prompt residue guard flags literal braces inside injected context VALUES

**Status:** Fixed
**Discovered:** 2026-07-17 — observed mid-run on a live `/lazy-batch` run (item in flight: `hydra-overlay`)
**Fixed:** 2026-07-18
**Fix commit:** ca8ca8b1
**Root-cause class:** script-defect
**Related:** `docs/specs/turn-routing-enforcement/` (hardening stage); hardening-log Round 31 (2026-07)

## Symptom (verified)

`lazy-state.py --emit-dispatch <class>` fail-closes with
`dispatch-<cls>.md: unbound token(s) after binding: <tok> — either add to @requires or
remove from the template` when an operator/orchestrator free-text `--context` value
legitimately contains a literal `{lower_snake}` curly-brace token — e.g. a recorded
`resolution_summary` / `failure_summary` carrying a code snippet, a JSON object, or a
curly-brace wire-type. Observed live on an `apply-resolution` emit whose recorded
`resolution_summary` contained a curly-brace wire-type; worked around by rephrasing the
summary brace-free. The dispatch could not be emitted until the DATA was mangled.

## Reconstructed route

`lazy_core.dispatch.emit_dispatch_prompt` (`user/scripts/lazy_core/dispatch.py`):

1. Assembles the selected template sections into `prompt` (line ~1117).
2. Builds `bindings` = standard pipeline tokens overlaid with the caller's `context`
   dict values (lines ~1123-1125).
3. Binds every token by `prompt.replace("{"+token+"}", value)` (lines ~1128-1129) — this
   INJECTS the free-text context VALUES into `prompt`.
4. **Residue guard runs AFTER injection** (line ~1132):
   `_PROMPT_RESIDUE_RE.findall(prompt)` where `_PROMPT_RESIDUE_RE = re.compile(r"\{[a-z0-9_]+\}")`.
   Any `{lower_snake}` surviving is treated as an unbound TEMPLATE token and the whole
   emission is refused.

The divergence: step 4 scans the FULLY-BOUND prompt, which now contains the injected
value text. A literal `{some_token}` that was DATA inside a context value is
indistinguishable from a genuine unbound template placeholder, so it fail-closes a
correct dispatch. The identical post-injection ordering exists in the sibling
`emit_cycle_prompt` (line ~855), which binds free-text state values
(`feature_name`, `sub_skill_args`, `untestability_reason`, …) the same way — a
near-neighbor with the same latent flaw.

## Root cause

script-defect: the residue guard cannot distinguish a TEMPLATE placeholder (the fixed
known set the emitter substitutes) from an arbitrary `{lower_snake}` brace appearing
INSIDE an already-substituted context VALUE. Residue detection must run against the
TEMPLATE (with all known placeholders stripped) BEFORE value injection; a brace inside an
injected value is opaque DATA and must never be counted as an unbound token.

## Fix scope

`user/scripts/lazy_core/dispatch.py`:

- Add a shared helper `_template_residue(template_text, bindings)` that strips every known
  `{token}` placeholder from the template, THEN scans the remainder for
  `_PROMPT_RESIDUE_RE` residue — i.e. detect unbound placeholders on the pre-injection
  template.
- `emit_dispatch_prompt`: run the residue guard via `_template_residue(prompt, bindings)`
  BEFORE the bind loop (refusal message + `_dedup_residue` shape unchanged).
- `emit_cycle_prompt` (near-neighbor, same class): same reordering, preserving the addenda
  attribution suffix (compute the addenda residue via `_template_residue(addenda_blob, bindings)`).
- Regression tests: a context value containing a literal `{lower_snake}` brace must emit
  `ok=True` (NOT refuse); a genuine unbound template token must still refuse naming it.

No gate weakened: genuine unbound TEMPLATE tokens are still caught (they are not in
`bindings`, so stripping leaves them for the residue scan). The change only stops
mis-flagging DATA.
