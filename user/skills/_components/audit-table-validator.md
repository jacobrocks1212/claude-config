## Audit-Table Validator (post-generation pass)

**Why this component exists.** The audit walk surfaced two failure modes in per-feature decision tables (the per-feature listings inside `LAZY_BATCH_CLOUD_DECISION_LEDGER_*.md`, `LAZY_BATCH_REVIEW_*.md`, or any other generated audit artifact that enumerates per-feature decisions/findings as rows):

1. **Audit misattribution** — a row says a decision is a gap when it was actually resolved (4 of 199 decisions across 20 features: 2.H4, 4.H5, 6.H4, 13.H1). Root cause: the table was written against an early snapshot of the SPEC and never re-validated against the SPEC's current state.
2. **Cross-feature copy-paste error** — the same row text appears in two different feature tables (e.g. 17.L5 was a literal duplicate of 15.L4). Root cause: the generator template was filled in for one feature and never updated when iterated to the next.

This component is the post-generation validator pass. The consumer (any audit-artifact generator) runs it after the per-feature tables are written, and the validator annotates each table row with one of two warning tags as appropriate. Annotations are NON-DESTRUCTIVE — they append a marker to the row, never delete or rewrite the row content. The audit walker (whether human operator or downstream audit-walk skill) can then quickly spot rows that need re-classification before walking them as gaps.

The validator is read-only against everything but the artifact file(s) it just wrote. It runs no Tauri, no MCP server, and no shell beyond `grep` — it works identically in cloud and workstation.

### Inputs

- `artifact_paths` — list of generated audit-artifact paths to validate (e.g. one `LAZY_BATCH_REVIEW_<date>.md` per feature plus the optional `_index/<...>_overview.md`).
- `feature_resolver` — a callable / convention that maps each artifact's `feature_id` (parsed from frontmatter) to the feature's `spec_path` (i.e. `docs/features/<area>/<feature-id>/`). The standard convention: read frontmatter `feature_id`, then locate `docs/features/**/<feature-id>/SPEC.md` via `find`.

### Algorithm

1. **Parse each artifact's per-feature decision tables.** Each generator owns its own row schema. Consumers SHOULD pass the validator a list of `{artifact_path, feature_id, spec_md_path, table_section_title, row_anchor_column}` records identifying:
   - `table_section_title` — the H2/H3/H4 markdown heading that owns the table (e.g. `## Findings`, `## Compliance Matrix`, `### Per-feature decision listing`).
   - `row_anchor_column` — the column index whose value is the "anchor" the validator should search for in the SPEC and use for cross-feature deduplication (e.g. for a Findings table, the `Title` column; for a Decision Ledger, the `Decision ID` column or the `Decision text` column).

   For each row in each identified table, extract:
   - `row_text` — the full table-row markdown (used for cross-feature dedup).
   - `anchor_text` — the value of `row_anchor_column` for this row (used for SPEC keyword search).
   - `anchor_keywords` — the 2-4 most distinctive content words from `anchor_text` (drop articles, prepositions, generic verbs).

2. **SPEC keyword search (NOT-FOUND-IN-SPEC detection).** For each row in each feature's table:
   - Read `{spec_md_path}` (the feature's SPEC.md).
   - Grep the SPEC body (case-insensitive substring) for the row's `anchor_text` literal. If found, the row anchors cleanly.
   - If the literal isn't found, fall back to a keyword search: a row is considered "anchored" iff at least 2 of `anchor_keywords` appear (case-insensitive substring) anywhere in the SPEC body.
   - If neither match holds, the row is `NOT-FOUND-IN-SPEC`. Annotate it (see step 4).

3. **Cross-feature duplicate detection (CROSS-FEATURE-DUP).** Across ALL parsed tables in this validator invocation (across every artifact in `artifact_paths`):
   - Normalize each row's `row_text` (strip trailing whitespace and the leading/trailing `|` table delimiters, collapse internal whitespace runs to single spaces). This avoids false positives on cosmetic differences.
   - Group rows by normalized `row_text`. Any group with ≥ 2 entries flagged as `CROSS-FEATURE-DUP` — but ONLY when the entries come from DIFFERENT artifacts (`feature_id` differs). Two rows in the same feature's artifact are not flagged (intra-feature duplicates are a separate concern handled by the generator itself).
   - For each flagged group, annotate every member (see step 4).

4. **Annotate rows in place.** For each row that triggered a warning:
   - Open the owning artifact file.
   - Locate the table row by its full original text (use the unnormalized row_text from parsing — it's the literal markdown).
   - Append one or both warning markers to the last cell of the row, just inside the trailing `|`:
     - `⚠ NOT-FOUND-IN-SPEC` — append when SPEC keyword search found nothing.
     - `⚠ CROSS-FEATURE-DUP(<other-feature-id>[, <other-feature-id>...])` — append when the row is a literal cross-feature duplicate. List the other feature ids that share the row.
   - Both markers MAY appear on the same row (separated by a single space).
   - If the row already ends with a trailing markdown table delimiter, insert the marker(s) before that delimiter. If the row's last cell is empty, the marker(s) fill the empty cell.

5. **Summary block.** After all annotations land, append a `## Audit-Table Validator Report` section at the END of each annotated artifact file with:

   ```markdown
   ## Audit-Table Validator Report

   *Generated <ISO 8601 UTC> by `_components/audit-table-validator.md`.*

   - **Rows scanned:** <total across all tables in this artifact>
   - **NOT-FOUND-IN-SPEC:** <count> — see annotated rows above.
   - **CROSS-FEATURE-DUP:** <count> — duplicate row text shared with: <comma-separated list of other artifact basenames>.

   Annotations are non-destructive — they mark rows for the audit walker
   to re-classify, but do not remove the original row content. Resolve
   each by either (a) updating the row's anchor text to match the SPEC's
   current wording, (b) regenerating the audit table against the current
   SPEC, or (c) confirming the misattribution and removing the row.
   ```

6. **Return status:**
   - `clean` — no annotations applied. The validator section IS still written so the audit trail shows the validator ran. Counts in the summary are zero.
   - `annotated:N_not_found+M_dup` — N rows tagged NOT-FOUND-IN-SPEC, M tagged CROSS-FEATURE-DUP (some rows may have both tags; counts overlap). Consumer SHOULD include this in its own end-of-skill output so the operator notices.

### Skip conditions

- The artifact's frontmatter has no `feature_id` field (cross-cutting overview-only artifacts where the rows don't anchor to a single SPEC) — skip per-feature SPEC validation for that artifact, but include its rows in the cross-feature dup scan.
- The resolved `spec_md_path` does not exist (the feature dir was deleted or moved since the artifact was generated) — skip the SPEC search for that feature's rows; include the artifact's rows in the cross-feature dup scan; note the missing SPEC in the summary block (`⚠ SPEC.md not found for <feature_id>; SPEC validation skipped`).
- The artifact has no parseable tables at the named section titles — skip silently. The validator is a passive enhancement; absent tables are not an error.

### Integration with `lazy-batch-retro`

`/lazy-batch-retro` is the closest existing audit-artifact generator that benefits from this validator. After Step 6b writes per-feature artifacts and the optional cross-cutting overview, the orchestrator calls this validator with each per-feature artifact's path, the artifact's `feature_id` (from frontmatter), the resolved `docs/features/**/<feature_id>/SPEC.md` path, and `{table_section_title: "## Findings", row_anchor_column: 1 /* the Title column */}` plus `{table_section_title: "## Compliance Matrix", row_anchor_column: 0 /* the Rule ID column */}`. The Commit step (Step 7) follows; the validator annotations are part of the same commit as the artifacts themselves.

### Integration with other generators

Any future generator that produces per-feature decision tables (e.g. an ad-hoc `LAZY_BATCH_CLOUD_DECISION_LEDGER_<date>.md` writer) should `!cat` inject this component as its final step before commit, then call the algorithm with the relevant `{table_section_title, row_anchor_column}` records. The generator owns the row schema; this component owns the post-write validation.
