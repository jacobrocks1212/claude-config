#!/usr/bin/env npx tsx
/**
 * post-process.ts - Deterministic post-processing for combined PR review findings
 *
 * Processes combined findings JSON from investigation + sweep agents:
 * 1. Recomputes effective_weight from the live weights state file (authoritative source;
 *    seeded from knowledge/weights.yaml shipped defaults — see weight-constants.ts)
 * 2. Drops SWEEP findings below minimum threshold (sweep lane only — Opus-lane sources
 *    are never threshold-dropped; a zeroed lane raises a lane_zeroed warning instead)
 * 3. Deduplicates by file:line — cross-lane co-located pairs collapse Opus-over-sweep;
 *    same-lane pairs collapse only on a normalized-title match (distinct findings at the
 *    same location both survive)
 * 4. Ranks by tier > severity > effective_weight
 * 5. Filters out-of-scope files via manifest (paths normalized on both sides)
 * 6. Annotates finding lifespans for re-reviews
 *
 * Every dropped finding is recorded in the payload's drops[] (step + reason).
 *
 * Input JSON shape (CombinedFindings):
 *   { investigation: [{ findings, escalations, group }], sweep: { findings, escalations }, manifest_path, previous_review_path? }
 *
 * Usage:
 *   npx tsx post-process.ts --input findings.json --manifest <cogDocsItemDir>/.pr-review/pr-cache/12345/manifest.json [--previous-review <cogDocsItemDir>/PR-12345.md] [--weights path/to/weights.yaml] [--summary]
 *
 * --summary emits a one-line count summary to stderr (stdout stays the pure
 * processed-findings JSON, safe to shell-redirect to processed-findings.json).
 */

import { readFileSync } from "fs";
import yaml from "js-yaml";
import {
	MIN_EFFECTIVE_WEIGHT,
	ensureWeightsState,
	normalizeSourceWeight,
	type SourceWeightEntry,
} from "./weight-constants.ts";

// ── Types ──────────────────────────────────────────────────────────────────────

interface InvestigationFinding {
	file: string;
	line: number;
	severity: "blocking" | "important" | "nit";
	title: string;
	hypothesis: string;
	evidence: {
		snippet: string;
		reference: string;
	};
	suggestion: string;
	escalation_candidate: boolean;
	specialist_domain: string | null;
	confidence?: "CONFIRMED" | "UNVERIFIED";
}

interface ReuseFinding {
	file: string;
	line: number;
	severity: "blocking" | "important" | "nit";
	title: string;
	verdict: string;
	candidate: string;
	hypothesis: string;
	evidence: {
		snippet: string;
		reference: string;
	};
	suggestion: string;
	blast_radius: string | null;
	negative_search_trail: string | null;
	escalation_candidate: boolean;
	specialist_domain: string | null;
	confidence?: "CONFIRMED" | "UNVERIFIED";
}

interface SweepFinding {
	file: string;
	line: number;
	severity: "blocking" | "important" | "nit";
	title: string;
	description: string;
	suggestion: string;
	rule_id: string;
	rule_category: string;
	effective_weight: number;
	tier: "critical" | "important" | "skim";
	escalation_candidate: boolean;
	specialist_domain: string | null;
	confidence?: "CONFIRMED" | "UNVERIFIED";
}

interface Escalation {
	file: string;
	line: number;
	domain: string;
	concern: string;
	severity_estimate: string;
}

interface CombinedFindings {
	investigation: Array<{
		findings: InvestigationFinding[];
		escalations: Escalation[];
		group: string;
	}>;
	sweep: {
		findings: SweepFinding[];
		escalations: Escalation[];
	};
	reuse?: Array<{
		findings: ReuseFinding[];
		escalations: Escalation[];
		group: string;
	}>;
	intrafile?: Array<{
		findings: ReuseFinding[];
		escalations: Escalation[];
		group: string;
	}>;
	manifest_path: string;
	previous_review_path?: string;
}

interface WeightsConfig {
	version: number;
	ema_alpha: number;
	category_multipliers: Record<string, number>;
	rule_weights: Record<string, { weight: number; data_points: number }>;
	// Nested { weight, data_points } schema; legacy bare-scalar entries still accepted.
	source_weights: Record<string, number | SourceWeightEntry>;
}

interface Manifest {
	version: number;
	pr?: {
		iterationId?: number;
		[key: string]: unknown;
	};
	files: Array<{
		path: string;
		[key: string]: unknown;
	}>;
	[key: string]: unknown;
}

interface Lifespan {
	raised_in: number;
	total_iterations: number;
}

interface ProcessedFinding {
	source: "investigation" | "reuse" | "intrafile" | "sweep";
	group: string | null;
	effective_weight: number;
	lifespan?: Lifespan;
	[key: string]: unknown;
}

interface PreviousFindingRef {
	file: string;
	line: number;
	title?: string;
	iteration: number;
}

interface DropRecord {
	step: 2 | 3 | 5;
	stage: "threshold" | "dedup" | "scope";
	reason: string;
	source: string;
	file: string;
	line: number;
	title?: string;
}

interface OutputPayload {
	processed_findings: ProcessedFinding[];
	dropped_count: number;
	dedup_count: number;
	scope_filtered_count: number;
	lane_zeroed: string[];
	lifespan_annotations: number;
	drops: DropRecord[];
}

// ── Category mapping ───────────────────────────────────────────────────────────
// Maps rule_category values from YAML rule files to weights.yaml category_multiplier keys

const CATEGORY_MAP: Record<string, string> = {
	"csharp-architecture": "architecture",
	"api-design": "api_design",
	"frontend-vue": "frontend",
	"code-consistency": "consistency",
	"testing": "testing",
	"security": "security",
	"performance": "performance",
	"template-binding": "template_binding",
};

// ── Constants ──────────────────────────────────────────────────────────────────
// MIN_EFFECTIVE_WEIGHT is shared with disposition-calibration via weight-constants.ts.

const LINE_PROXIMITY_RANGE = 20;

const TIER_ORDER: Record<string, number> = { critical: 0, important: 1, skim: 2 };
const SEVERITY_ORDER: Record<string, number> = { blocking: 0, important: 1, nit: 2 };

// ── Helpers ────────────────────────────────────────────────────────────────────

function loadWeights(weightsPathOverride: string | null): WeightsConfig {
	let weightsPath: string;
	try {
		// Live mutable copy under ~/.claude/state/cognito-pr-review/ (seeded from the
		// plugin's shipped defaults on first use); --weights overrides for tests/tools.
		weightsPath = weightsPathOverride ?? ensureWeightsState();
	} catch (err) {
		error(`Failed to resolve/seed weights state file: ${err}`);
		return process.exit(1);
	}
	try {
		const raw = readFileSync(weightsPath, "utf-8");
		return yaml.load(raw) as WeightsConfig;
	} catch (err) {
		error(`Failed to load weights at ${weightsPath}: ${err}`);
		return process.exit(1);
	}
}

function loadJSON<T>(filePath: string, label: string): T {
	try {
		const raw = readFileSync(filePath, "utf-8");
		return JSON.parse(raw) as T;
	} catch (err) {
		error(`Failed to load ${label} at ${filePath}: ${err}`);
		return process.exit(1);
	}
}

function error(msg: string): void {
	process.stderr.write(`[post-process] ${msg}\n`);
}

function locationKey(file: string, line: number): string {
	return `${file}:${line}`;
}

/** Resolve the category multiplier for a rule_category string. */
function getCategoryMultiplier(ruleCategory: string, weights: WeightsConfig): number {
	const mapped = CATEGORY_MAP[ruleCategory];
	if (mapped && weights.category_multipliers[mapped] !== undefined) {
		return weights.category_multipliers[mapped];
	}
	// Fallback: try the raw category name directly
	if (weights.category_multipliers[ruleCategory] !== undefined) {
		return weights.category_multipliers[ruleCategory];
	}
	return 1.0;
}

/** Map a finding's confidence label to a numeric multiplier. Absent/unknown → 1.0 (back-compat). */
function resolveConfidence(finding: { confidence?: string }): number {
	switch (finding.confidence) {
		case "CONFIRMED": return 1.0;
		case "UNVERIFIED": return 0.5;
		default: return 1.0;
	}
}

/** Compute effective_weight = base × confidence_multiplier. */
function computeEffectiveWeight(
	finding: { source: string; rule_id?: string; rule_category?: string; confidence?: string },
	weights: WeightsConfig
): number {
	let base: number;
	if (finding.source === "sweep") {
		const ruleEntry = weights.rule_weights[finding.rule_id as string];
		const ruleWeight = ruleEntry?.weight ?? 0.7;
		const categoryMultiplier = getCategoryMultiplier(finding.rule_category as string, weights);
		base = ruleWeight * categoryMultiplier;
	} else {
		base = normalizeSourceWeight(weights.source_weights?.[finding.source])?.weight ?? 0.7;
	}
	return base * resolveConfidence(finding);
}

// ── Previous review parsing ────────────────────────────────────────────────────

function parsePreviousReview(filePath: string, totalIterations?: number): PreviousFindingRef[] {
	let content: string;
	try {
		content = readFileSync(filePath, "utf-8");
	} catch {
		error(`Could not read previous review at ${filePath}, skipping lifespan annotation`);
		return [];
	}

	const refs: PreviousFindingRef[] = [];

	// The iteration a carried-forward finding was first raised in. Derive it ONLY from
	// structural `### Iteration N` review-round headers — NOT from the review's own
	// emitted `raised_in:` / `total_iterations:` lifespan markers. Scraping those markers
	// was RC-1b: each run read back its prior `raised_in`, incrementing it every re-review
	// (777 → 778 → …). The old regex `/(?:Iteration|raised_in)\D*(\d+)/` also caught the
	// emitted `total_iterations:` value via the `Iteration` substring. Anchoring on the
	// `### Iteration N` header (the same durable signal detectReReview uses) closes both.
	// Default to 1 if no header is present; clamp to the real total when known.
	let maxIteration = 1;
	const iterMatches = content.matchAll(/^#{1,6}\s*Iteration\s+(\d+)/gim);
	for (const m of iterMatches) {
		const n = parseInt(m[1], 10);
		if (n > maxIteration) maxIteration = n;
	}
	if (totalIterations !== undefined && maxIteration > totalIterations) {
		maxIteration = totalIterations;
	}

	// Pattern 1: Critical/Investigation findings - "**File:** path/to/file.cs:42"
	const fileLinePattern = /\*\*File:\*\*\s*`?([^:`\n]+):(\d+)`?/g;
	let match: RegExpExecArray | null;
	while ((match = fileLinePattern.exec(content)) !== null) {
		refs.push({
			file: match[1].trim(),
			line: parseInt(match[2], 10),
			iteration: maxIteration,
		});
	}

	// Pattern 2: Rule-based findings - "description [path/to/file.cs:42] (weight: 0.84)"
	const bracketPattern = /\[([^\]]+?):(\d+)\]/g;
	while ((match = bracketPattern.exec(content)) !== null) {
		const file = match[1].trim();
		const line = parseInt(match[2], 10);
		// Avoid duplicates from the same line
		if (!refs.some(r => r.file === file && r.line === line)) {
			refs.push({ file, line, iteration: maxIteration });
		}
	}

	// Pattern 4: Standardized Issue Block (current synthesizer-v2 format) -
	// "**Location:** `path/to/file.cs:42`" under a "### {title}" heading
	const locationPattern = /\*\*Location:\*\*\s*`?([^:`\n]+):(\d+)`?/g;
	while ((match = locationPattern.exec(content)) !== null) {
		const file = match[1].trim();
		const line = parseInt(match[2], 10);
		if (!refs.some(r => r.file === file && r.line === line)) {
			refs.push({ file, line, iteration: maxIteration });
		}
	}

	// Extract titles for investigation findings (### Finding title above **File:**)
	const titleFilePattern = /###\s+(.+)\n(?:.*\n)*?\*\*File:\*\*\s*`?([^:`\n]+):(\d+)`?/g;
	while ((match = titleFilePattern.exec(content)) !== null) {
		const title = match[1].trim();
		const file = match[2].trim();
		const line = parseInt(match[3], 10);
		const existing = refs.find(r => r.file === file && r.line === line);
		if (existing) {
			existing.title = title;
		}
	}

	// Title association for Standardized Issue Blocks (### {title} above **Location:**)
	const titleLocationPattern = /###\s+(.+)\n(?:.*\n)*?\*\*Location:\*\*\s*`?([^:`\n]+):(\d+)`?/g;
	while ((match = titleLocationPattern.exec(content)) !== null) {
		const title = match[1].trim();
		const file = match[2].trim();
		const line = parseInt(match[3], 10);
		const existing = refs.find(r => r.file === file && r.line === line);
		if (existing && !existing.title) {
			existing.title = title;
		}
	}

	return refs;
}

function matchesPreviousFinding(
	finding: ProcessedFinding,
	previousRefs: PreviousFindingRef[]
): PreviousFindingRef | undefined {
	const file = finding.file as string;
	const line = finding.line as number;
	const title = finding.title as string | undefined;

	return previousRefs.find(ref => {
		if (ref.file !== file) return false;
		// Line must be within proximity range
		if (Math.abs(ref.line - line) > LINE_PROXIMITY_RANGE) return false;
		// For Opus-lane findings (investigation, reuse, intrafile), also compare title if available
		if ((finding.source === "investigation" || finding.source === "reuse" || finding.source === "intrafile") && ref.title && title) {
			return ref.title.toLowerCase() === title.toLowerCase();
		}
		return true;
	});
}

// ── Pipeline steps ─────────────────────────────────────────────────────────────

function step1_computeWeights(
	combined: CombinedFindings,
	weights: WeightsConfig
): { findings: ProcessedFinding[] } {
	const findings: ProcessedFinding[] = [];

	// Investigation findings pass through unchanged
	for (const group of combined.investigation) {
		for (const f of group.findings) {
			findings.push({
				...f,
				source: "investigation",
				group: group.group,
				effective_weight: computeEffectiveWeight({ ...f, source: "investigation" }, weights),
			});
		}
	}

	// Reuse findings: verdict→severity mapping; acceptable-new are dropped entirely
	for (const group of combined.reuse ?? []) {
		for (const f of group.findings) {
			// Drop findings the reuse agent marked as acceptable-new
			if (f.verdict === "acceptable-new") {
				continue;
			}

			// Map verdict to severity; unknown verdicts pass through with their existing severity
			let severity = f.severity;
			if (f.verdict === "refactor" || f.verdict === "reuse") {
				severity = "important";
			} else if (f.verdict === "extend" || f.verdict === "wrap") {
				severity = "nit";
			}

			findings.push({
				...f,
				severity,
				source: "reuse",
				group: group.group,
				effective_weight: computeEffectiveWeight({ ...f, source: "reuse" }, weights),
			});
		}
	}

	// Intrafile findings: verdict→severity mapping; acceptable/consistent verdicts are dropped
	for (const group of combined.intrafile ?? []) {
		for (const f of group.findings) {
			if (f.verdict === "acceptable-new" || f.verdict === "acceptable" || f.verdict === "consistent") {
				continue;
			}

			let severity = f.severity;
			if (f.verdict === "refactor" || f.verdict === "reuse") {
				severity = "important";
			} else if (f.verdict === "inconsistent") {
				severity = "nit";
			} else if (f.verdict === "extend" || f.verdict === "wrap") {
				severity = "nit";
			}

			findings.push({
				...f,
				severity,
				source: "intrafile",
				group: group.group,
				effective_weight: computeEffectiveWeight({ ...f, source: "intrafile" }, weights),
			});
		}
	}

	// Sweep findings get recomputed effective_weight
	for (const f of combined.sweep.findings) {
		const effectiveWeight = computeEffectiveWeight({ ...f, source: "sweep" }, weights);
		findings.push({
			...f,
			source: "sweep",
			group: null,
			effective_weight: effectiveWeight,
		});
	}

	return { findings };
}

function dropRecord(
	f: ProcessedFinding,
	step: 2 | 3 | 5,
	stage: "threshold" | "dedup" | "scope",
	reason: string
): DropRecord {
	return {
		step,
		stage,
		reason,
		source: f.source,
		file: f.file as string,
		line: f.line as number,
		title: f.title as string | undefined,
	};
}

function step2_dropBelowThreshold(
	findings: ProcessedFinding[],
	drops: DropRecord[]
): {
	findings: ProcessedFinding[];
	droppedCount: number;
} {
	let droppedCount = 0;
	const kept: ProcessedFinding[] = [];

	for (const f of findings) {
		// The minimum-weight drop applies to the SWEEP lane only. Opus-lane sources
		// (investigation, reuse, intrafile) are never threshold-dropped — calibration
		// drift zeroing those lanes silently was the source_weights-drift bug.
		if (f.source === "sweep" && f.effective_weight < MIN_EFFECTIVE_WEIGHT) {
			droppedCount++;
			drops.push(
				dropRecord(f, 2, "threshold", `sweep effective_weight ${f.effective_weight} < ${MIN_EFFECTIVE_WEIGHT}`)
			);
		} else {
			kept.push(f);
		}
	}

	return { findings: kept, droppedCount };
}

function step3_deduplicate(
	findings: ProcessedFinding[],
	drops: DropRecord[]
): {
	findings: ProcessedFinding[];
	dedupCount: number;
} {
	// file:line buckets may legitimately hold MULTIPLE distinct findings. Only two
	// collapse cases are treated as "same issue":
	//   1. Cross-lane co-located (Opus-class vs sweep): the sweep finding is assumed
	//      to be the same issue caught by the cheaper lane — Opus wins (historical intent).
	//   2. Same-lane with a matching normalized title: a true duplicate — highest
	//      effective_weight wins.
	// Distinct same-lane findings at the same location BOTH survive (the old code
	// silently discarded one of them purely by location collision).
	const seen = new Map<string, ProcessedFinding[]>();
	let dedupCount = 0;

	const isOpus = (f: ProcessedFinding): boolean => f.source !== "sweep";
	const normTitle = (f: ProcessedFinding): string =>
		((f.title as string) ?? "").trim().toLowerCase();

	for (const f of findings) {
		const key = locationKey(f.file as string, f.line as number);
		const bucket = seen.get(key);

		if (!bucket) {
			seen.set(key, [f]);
			continue;
		}

		let collapsed = false;
		for (let i = 0; i < bucket.length; i++) {
			const existing = bucket[i];
			const crossLane = isOpus(f) !== isOpus(existing);

			if (crossLane) {
				dedupCount++;
				if (isOpus(f)) {
					drops.push(
						dropRecord(existing, 3, "dedup", `co-located sweep finding superseded by ${f.source} at same location`)
					);
					bucket[i] = f;
				} else {
					drops.push(
						dropRecord(f, 3, "dedup", `co-located sweep finding superseded by ${existing.source} at same location`)
					);
				}
				collapsed = true;
				break;
			}

			if (normTitle(f) === normTitle(existing)) {
				dedupCount++;
				if (f.effective_weight > existing.effective_weight) {
					drops.push(dropRecord(existing, 3, "dedup", "lower-weight duplicate (same lane, same title)"));
					bucket[i] = f;
				} else {
					drops.push(dropRecord(f, 3, "dedup", "lower-weight duplicate (same lane, same title)"));
				}
				collapsed = true;
				break;
			}
		}

		if (!collapsed) {
			bucket.push(f);
		}
	}

	return { findings: Array.from(seen.values()).flat(), dedupCount };
}

function step4_rank(findings: ProcessedFinding[]): ProcessedFinding[] {
	return findings.sort((a, b) => {
		// Primary: tier (critical > important > skim)
		// All Opus-lane sources (investigation, reuse, intrafile) rank at the top tier
		const tierA = (a.source === "investigation" || a.source === "reuse" || a.source === "intrafile") ? "critical" : (a.tier as string) ?? "skim";
		const tierB = (b.source === "investigation" || b.source === "reuse" || b.source === "intrafile") ? "critical" : (b.tier as string) ?? "skim";
		const tierDiff = (TIER_ORDER[tierA] ?? 2) - (TIER_ORDER[tierB] ?? 2);
		if (tierDiff !== 0) return tierDiff;

		// Secondary: severity (blocking > important > nit)
		const sevA = (a.severity as string) ?? "nit";
		const sevB = (b.severity as string) ?? "nit";
		const sevDiff = (SEVERITY_ORDER[sevA] ?? 2) - (SEVERITY_ORDER[sevB] ?? 2);
		if (sevDiff !== 0) return sevDiff;

		// Tertiary: effective_weight descending
		return b.effective_weight - a.effective_weight;
	});
}

/** Normalize a path for scope comparison: forward slashes, no leading ./ or /, casefolded.
 * (Mirrors the normalizePath approach of the archived calibrate-weights.ts.) */
function normalizeScopePath(p: string): string {
	return p
		.replace(/\\/g, "/")
		.replace(/^\.\//, "")
		.replace(/^\//, "")
		.toLowerCase();
}

function step5_filterOutOfScope(
	findings: ProcessedFinding[],
	manifest: Manifest,
	drops: DropRecord[]
): { findings: ProcessedFinding[]; scopeFilteredCount: number } {
	// Both sides normalized — an agent emitting `.\Foo\Bar.cs` or a casing variant of a
	// manifest path must match, not be silently discarded.
	const manifestFiles = new Set(manifest.files.map(f => normalizeScopePath(f.path)));
	const kept: ProcessedFinding[] = [];
	let scopeFilteredCount = 0;

	for (const f of findings) {
		if (manifestFiles.has(normalizeScopePath(f.file as string))) {
			kept.push(f);
		} else {
			scopeFilteredCount++;
			drops.push(dropRecord(f, 5, "scope", "file not in manifest scope (after normalization)"));
		}
	}

	return { findings: kept, scopeFilteredCount };
}

function step6_annotateLifespan(
	findings: ProcessedFinding[],
	previousReviewPath: string,
	iterationId?: number
): { findings: ProcessedFinding[]; lifespanAnnotations: number } {
	const previousRefs = parsePreviousReview(previousReviewPath, iterationId);
	if (previousRefs.length === 0) {
		return { findings, lifespanAnnotations: 0 };
	}

	let lifespanAnnotations = 0;

	for (const f of findings) {
		const prevMatch = matchesPreviousFinding(f, previousRefs);
		if (prevMatch) {
			// total_iterations is the real PR iteration count (manifest.pr.iterationId).
			// When it is unavailable (legacy manifest) degrade to the prior +1 behavior —
			// now bounded, since prevMatch.iteration no longer amplifies via the scrape.
			const total = iterationId ?? prevMatch.iteration + 1;
			// raised_in is a real, bounded value: the iteration the finding was first
			// raised in, never exceeding the total.
			const raised = Math.min(prevMatch.iteration, total);
			f.lifespan = {
				raised_in: raised,
				total_iterations: total,
			};
			lifespanAnnotations++;
		}
	}

	return { findings, lifespanAnnotations };
}

// ── CLI ────────────────────────────────────────────────────────────────────────

interface CliArgs {
	inputPath: string;
	manifestPath: string;
	previousReviewPath: string | null;
	weightsPath: string | null;
	summary: boolean;
}

function parseArgs(argv: string[]): CliArgs {
	const args = argv.slice(2);
	let inputPath = "";
	let manifestPath = "";
	let previousReviewPath: string | null = null;
	let weightsPath: string | null = null;
	let summary = false;

	for (let i = 0; i < args.length; i++) {
		const arg = args[i];
		if (arg === "--input" && args[i + 1]) {
			inputPath = args[++i];
		} else if (arg === "--manifest" && args[i + 1]) {
			manifestPath = args[++i];
		} else if (arg === "--previous-review" && args[i + 1]) {
			previousReviewPath = args[++i];
		} else if (arg === "--weights" && args[i + 1]) {
			weightsPath = args[++i];
		} else if (arg === "--summary") {
			summary = true;
		}
	}

	if (!inputPath) {
		error("Missing required --input argument");
		process.exit(1);
	}
	if (!manifestPath) {
		error("Missing required --manifest argument");
		process.exit(1);
	}

	return { inputPath, manifestPath, previousReviewPath, weightsPath, summary };
}

// ── Main ───────────────────────────────────────────────────────────────────────

function main(): void {
	const { inputPath, manifestPath, previousReviewPath, weightsPath, summary } = parseArgs(process.argv);

	// Load inputs
	const combined = loadJSON<CombinedFindings>(inputPath, "input findings");
	const manifest = loadJSON<Manifest>(manifestPath, "manifest");
	const weights = loadWeights(weightsPath);

	// Pipeline
	const drops: DropRecord[] = [];
	const { findings: weighted } = step1_computeWeights(combined, weights);
	const { findings: thresholded, droppedCount } = step2_dropBelowThreshold(weighted, drops);
	const { findings: deduped, dedupCount } = step3_deduplicate(thresholded, drops);
	const ranked = step4_rank(deduped);
	const { findings: scoped, scopeFilteredCount } = step5_filterOutOfScope(ranked, manifest, drops);

	let final = scoped;
	let lifespanAnnotations = 0;

	if (previousReviewPath) {
		const result = step6_annotateLifespan(scoped, previousReviewPath, manifest.pr?.iterationId);
		final = result.findings;
		lifespanAnnotations = result.lifespanAnnotations;
	}

	// Lane-zeroed detection: any lane that entered the pipeline with findings but
	// ends with zero kept is loudly flagged — a silently-emptied lane (esp. the
	// Opus lanes) is how calibration drift went unnoticed.
	const inputLanes = new Set(weighted.map(f => f.source));
	const keptLanes = new Set(final.map(f => f.source));
	const laneZeroed = Array.from(inputLanes).filter(l => !keptLanes.has(l)).sort();
	if (laneZeroed.length > 0) {
		error(`WARNING: lane(s) zeroed by post-processing: ${laneZeroed.join(", ")} — every finding from these lanes was dropped`);
	}

	// Output
	const output: OutputPayload = {
		processed_findings: final,
		dropped_count: droppedCount,
		dedup_count: dedupCount,
		scope_filtered_count: scopeFilteredCount,
		lane_zeroed: laneZeroed,
		lifespan_annotations: lifespanAnnotations,
		drops,
	};

	process.stdout.write(JSON.stringify(output, null, 2) + "\n");

	// One-line count summary on stderr — the only output the orchestrator needs to
	// read when stdout is shell-redirected to processed-findings.json.
	// New keys are appended at the END (documented format — additive only).
	if (summary) {
		const severityCounts: Record<string, number> = { blocking: 0, important: 0, nit: 0 };
		for (const f of final) {
			const sev = (f.severity as string) ?? "nit";
			severityCounts[sev] = (severityCounts[sev] ?? 0) + 1;
		}
		error(
			`summary: total=${final.length} blocking=${severityCounts.blocking} ` +
			`important=${severityCounts.important} nit=${severityCounts.nit} ` +
			`dropped=${droppedCount} deduped=${dedupCount} lifespan=${lifespanAnnotations} ` +
			`scope_filtered=${scopeFilteredCount} lane_zeroed=${JSON.stringify(laneZeroed)}`
		);
	}
}

main();
