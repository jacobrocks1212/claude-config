<!-- Shared reuse-class agent scaffold (cache/local-codebase access model + tree-sitter guidance + verdict taxonomy + output schema) for the cognito-pr-review plugin. Consumed by agents/cognito-consistency-checker.md and agents/cognito-intra-file-consistency.md. One source of truth — do not fork. -->

# PR Review Reuse-Agent Scaffold

This scaffold defines the cache/local-codebase access model, tree-sitter usage, verdict taxonomy, and output schema shared by reuse-class agents in the cognito-pr-review plugin.

## Cache-Based File Access

Files for this PR are pre-cached:

- **Changed files:** `{cacheDir}/files/{path}` — Full file content from PR branch
- **Diffs:** `{cacheDir}/diffs/{path}.diff` — What changed in this PR
- **Manifest:** `{cacheDir}/manifest.json` — File inventory with baseline mappings
- **Structural context:** `{cacheDir}/structural-context/{filename}.md` — Summarised context for large files

**Baseline reading strategy:**
1. Read `{cacheDir}/manifest.json` to find `baselines[]` for each file.
2. Only compare against baselines with `similarityScore >= 50`.
3. Read the highest-scoring baselines first (they are the strongest reuse signal).
4. Read the changed file and its baseline file in parallel for comparison.

---

## Codebase Exploration

You may read ANY file in the local repository for exploration purposes. However:

**The local codebase is on the `main` branch, NOT the PR branch.**

Use local codebase reads for:
- Finding existing patterns to compare against
- Checking how similar problems are solved elsewhere
- Validating that referenced APIs/methods exist and work as expected
- Understanding the broader context of the code being changed
- Assessing blast radius by checking who calls/uses the changed code

Do NOT use local files as the "current state" of PR files — use the cached versions for that.

Use Grep/Glob freely against the local codebase to trace callers, find similar implementations, and verify that alternatives you might suggest actually exist.

---

## Structural Codebase Queries (MCP Tools)

When tree-sitter MCP tools are available, prefer them over raw Read/Grep for structural queries against the local codebase:

- **`get_file_structure`** — Get a file's structural outline (classes, methods, properties with line numbers) before reading the full file.
- **`get_callers`** — Find all callers of a function/method to assess blast radius. Use this for every `refactor` verdict to enumerate callers before recommending a shape change.
- **`get_callees`** — Understand what a function calls before manually tracing through its body.
- **`find_symbol_usages`** — Find all references to a symbol (class, method, interface) across the codebase.
- **`get_dependencies`** — Get a file's imports and exports to understand its dependency relationships.

**When to use these vs. Read/Grep/Glob:**
- Use MCP tools for **structural** queries: "what does this file contain?", "who calls this?", "what does this function call?", "where is this symbol used?"
- Use Read for **content** inspection: reading actual code, understanding logic, checking specific implementations
- Use Grep for **text** searches: finding string literals, configuration values, patterns that aren't structural
- Use Glob for **file discovery**: finding files by name pattern

**Fallback:** If MCP tools are unavailable, return errors, or produce incomplete results, fall back to Read/Grep/Glob. MCP tools are an optimization, not a requirement.

**Same caveat as Codebase Exploration:** These tools query the local codebase on the `main` branch, not the PR branch. Use them for pattern comparison, caller tracing, and blast radius assessment — not for reading the current state of PR files.

---

## Verdict Taxonomy

Every finding must carry one of these verdicts:

| Verdict | Meaning |
|---|---|
| `reuse` | Existing code already does this; the PR should have called it directly |
| `extend` | An existing type/service is the right home — the PR should have added a member or case there, not created a new system |
| `refactor` | Existing code is the right home but must change shape; use `get_callers` to name the blast radius |
| `wrap` | Compose existing pieces behind a thin new seam instead of re-implementing from scratch |
| `acceptable-new` | Nothing suitable exists — proven by a recorded `negative_search_trail` |

Downstream post-processing maps verdicts to severity:
- `refactor` / `reuse` → `important`
- `extend` / `wrap` → `nit`
- `acceptable-new` → **dropped** (not surfaced in the final review)

Therefore: only emit `acceptable-new` findings as evidence that you searched thoroughly. They will not appear in the final review output but they are required by the R4 gate.

---

## Output Schema

Write exactly ONE file to `{cacheDir}/agent-output/{output-prefix}-{cluster}.json`, where `{output-prefix}` is defined by your specific agent prompt (the reuse-candidacy checker uses `reuse`) and `{cluster}` is the cluster name slugified (spaces → hyphens, lowercase).

The file MUST conform to this schema:

```json
{
  "group": "<cluster name>",
  "findings": [
    {
      "file": "<PR net-new file where the overlap lives>",
      "line": 0,
      "severity": "important",
      "title": "<short title>",
      "verdict": "reuse|extend|refactor|wrap|acceptable-new",
      "candidate": "<existing-system file:line / symbol / skill; empty string for acceptable-new>",
      "hypothesis": "<why this is a reuse/dup opportunity or why it is acceptable-new>",
      "evidence": {
        "snippet": "<relevant code excerpt>",
        "reference": "<file:line or skill name — local codebase or cache, note which>"
      },
      "confidence": "CONFIRMED" | "UNVERIFIED",
      "suggestion": "<reuse / extend / refactor / wrap X — or empty string for acceptable-new>",
      "blast_radius": "<get_callers summary listing callers that would be affected, for refactor verdicts; null for all others>",
      "negative_search_trail": "<comma-separated list of skills, docs, and symbols searched that came back empty — required and non-empty for acceptable-new; null for all other verdicts>",
      "escalation_candidate": false,
      "specialist_domain": null
    }
  ],
  "escalations": []
}
```

**Schema rules:**
- `findings` may be empty if the cluster is clean (no reuse opportunities and all new code is genuinely novel).
- `escalations` may be empty; only populate if a finding reveals a domain concern (security, performance, data-integrity, api-design, concurrency) that exceeds this agent's scope.
- Every `acceptable-new` finding MUST have a non-empty `negative_search_trail`. An empty trail fails the R4 gate — search again before writing the output.
- Every `refactor` finding MUST have a non-null `blast_radius` populated via `get_callers`.
- `severity` for this agent's findings is always `"important"` — downstream post-processing remaps by verdict (`refactor`/`reuse` → `important`, `extend`/`wrap` → `nit`, `acceptable-new` → dropped).
- `line` is the line in the PR file where the duplicate or reusable logic lives. Use 0 if the finding applies to the whole file.
- `candidate` is an empty string (not null) for `acceptable-new` verdicts.
- `confidence` is `"CONFIRMED"` when the agent has actively verified the finding (a concrete second occurrence found, a caller/blast-radius traced to ground truth); `"UNVERIFIED"` when hedged or unproven ("may", "could", "potentially", or unconfirmed against evidence).
