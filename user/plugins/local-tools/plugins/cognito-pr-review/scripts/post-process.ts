#!/usr/bin/env npx tsx
/**
 * post-process.ts - Deterministic post-processing for combined PR review findings
 *
 * Processes combined findings JSON from investigation + sweep agents:
 * 1. Recomputes effective_weight from weights.yaml (authoritative source)
 * 2. Drops sweep findings below minimum threshold
 * 3. Deduplicates by file:line (prefers investigation over sweep)
 * 4. Ranks by tier > severity > effective_weight
 * 5. Filters out-of-scope files via manifest
 * 6. Annotates finding lifespans for re-reviews
 *
 * Input JSON shape (CombinedFindings):
 *   { investigation: [{ findings, escalations, group }], sweep: { findings, escalations }, manifest_path, previous_review_path? }
 *
 * Usage:
 *   npx tsx post-process.ts --input findings.json --manifest <cogDocsItemDir>/.pr-review/pr-cache/12345/manifest.json [--previous-review <cogDocsItemDir>/PR-12345.md]
 */

import { readFileSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";
import yaml from "js-yaml";

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
}

interface Manifest {
	version: number;
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

interface OutputPayload {
	processed_findings: ProcessedFinding[];
	dropped_count: number;
	dedup_count: number;
	lifespan_annotations: number;
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

const MIN_EFFECTIVE_WEIGHT = 0.3;
const LINE_PROXIMITY_RANGE = 20;

const TIER_ORDER: Record<string, number> = { critical: 0, important: 1, skim: 2 };
const SEVERITY_ORDER: Record<string, number> = { blocking: 0, important: 1, nit: 2 };

// ── Helpers ────────────────────────────────────────────────────────────────────

function loadWeights(): WeightsConfig {
	const scriptDir = dirname(fileURLToPath(import.meta.url));
	const weightsPath = resolve(scriptDir, "..", "knowledge", "weights.yaml");
	try {
		const raw = readFileSync(weightsPath, "utf-8");
		return yaml.load(raw) as WeightsConfig;
	} catch (err) {
		error(`Failed to load weights.yaml at ${weightsPath}: ${err}`);
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

/** Compute effective_weight = rule_weight × category_multiplier. */
function computeEffectiveWeight(finding: SweepFinding, weights: WeightsConfig): number {
	const ruleEntry = weights.rule_weights[finding.rule_id];
	const ruleWeight = ruleEntry?.weight ?? 0.7; // default if rule not in weights
	const categoryMultiplier = getCategoryMultiplier(finding.rule_category, weights);
	return ruleWeight * categoryMultiplier;
}

// ── Previous review parsing ────────────────────────────────────────────────────

function parsePreviousReview(filePath: string): PreviousFindingRef[] {
	let content: string;
	try {
		content = readFileSync(filePath, "utf-8");
	} catch {
		error(`Could not read previous review at ${filePath}, skipping lifespan annotation`);
		return [];
	}

	const refs: PreviousFindingRef[] = [];

	// Extract iteration count from existing lifespan markers or section headers
	// Default to 1 if we can't determine
	let maxIteration = 1;
	const iterMatches = content.matchAll(/(?:Iteration|raised_in)\D*(\d+)/gi);
	for (const m of iterMatches) {
		const n = parseInt(m[1], 10);
		if (n > maxIteration) maxIteration = n;
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
				effective_weight: 1.0, // investigation findings get max weight for ranking
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
				effective_weight: 1.0,
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
				effective_weight: 1.0,
			});
		}
	}

	// Sweep findings get recomputed effective_weight
	for (const f of combined.sweep.findings) {
		const effectiveWeight = computeEffectiveWeight(f, weights);
		findings.push({
			...f,
			source: "sweep",
			group: null,
			effective_weight: effectiveWeight,
		});
	}

	return { findings };
}

function step2_dropBelowThreshold(findings: ProcessedFinding[]): {
	findings: ProcessedFinding[];
	droppedCount: number;
} {
	let droppedCount = 0;
	const kept: ProcessedFinding[] = [];

	for (const f of findings) {
		if (f.source === "sweep" && f.effective_weight < MIN_EFFECTIVE_WEIGHT) {
			droppedCount++;
		} else {
			kept.push(f);
		}
	}

	return { findings: kept, droppedCount };
}

function step3_deduplicate(findings: ProcessedFinding[]): {
	findings: ProcessedFinding[];
	dedupCount: number;
} {
	const seen = new Map<string, ProcessedFinding>();
	let dedupCount = 0;

	for (const f of findings) {
		const key = locationKey(f.file as string, f.line as number);
		const existing = seen.get(key);

		if (!existing) {
			seen.set(key, f);
			continue;
		}

		dedupCount++;

		// Opus-lane sources (investigation, reuse, intrafile) beat sweep; within Opus-lane keep highest weight
		const incomingIsOpus = f.source === "investigation" || f.source === "reuse" || f.source === "intrafile";
		const existingIsOpus = existing.source === "investigation" || existing.source === "reuse" || existing.source === "intrafile";

		if (incomingIsOpus && !existingIsOpus) {
			// Incoming Opus-lane displaces existing sweep
			seen.set(key, f);
		} else if (existingIsOpus && !incomingIsOpus) {
			// Keep existing Opus-lane finding; discard sweep challenger
		} else {
			// Both same tier (Opus vs Opus, or sweep vs sweep) — keep highest effective_weight
			if (f.effective_weight > existing.effective_weight) {
				seen.set(key, f);
			}
		}
	}

	return { findings: Array.from(seen.values()), dedupCount };
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

function step5_filterOutOfScope(
	findings: ProcessedFinding[],
	manifest: Manifest
): ProcessedFinding[] {
	const manifestFiles = new Set(manifest.files.map(f => f.path));
	return findings.filter(f => manifestFiles.has(f.file as string));
}

function step6_annotateLifespan(
	findings: ProcessedFinding[],
	previousReviewPath: string
): { findings: ProcessedFinding[]; lifespanAnnotations: number } {
	const previousRefs = parsePreviousReview(previousReviewPath);
	if (previousRefs.length === 0) {
		return { findings, lifespanAnnotations: 0 };
	}

	let lifespanAnnotations = 0;

	for (const f of findings) {
		const prevMatch = matchesPreviousFinding(f, previousRefs);
		if (prevMatch) {
			f.lifespan = {
				raised_in: prevMatch.iteration,
				total_iterations: prevMatch.iteration + 1,
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
}

function parseArgs(argv: string[]): CliArgs {
	const args = argv.slice(2);
	let inputPath = "";
	let manifestPath = "";
	let previousReviewPath: string | null = null;

	for (let i = 0; i < args.length; i++) {
		const arg = args[i];
		if (arg === "--input" && args[i + 1]) {
			inputPath = args[++i];
		} else if (arg === "--manifest" && args[i + 1]) {
			manifestPath = args[++i];
		} else if (arg === "--previous-review" && args[i + 1]) {
			previousReviewPath = args[++i];
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

	return { inputPath, manifestPath, previousReviewPath };
}

// ── Main ───────────────────────────────────────────────────────────────────────

function main(): void {
	const { inputPath, manifestPath, previousReviewPath } = parseArgs(process.argv);

	// Load inputs
	const combined = loadJSON<CombinedFindings>(inputPath, "input findings");
	const manifest = loadJSON<Manifest>(manifestPath, "manifest");
	const weights = loadWeights();

	// Pipeline
	const { findings: weighted } = step1_computeWeights(combined, weights);
	const { findings: thresholded, droppedCount } = step2_dropBelowThreshold(weighted);
	const { findings: deduped, dedupCount } = step3_deduplicate(thresholded);
	const ranked = step4_rank(deduped);
	const scoped = step5_filterOutOfScope(ranked, manifest);

	let final = scoped;
	let lifespanAnnotations = 0;

	if (previousReviewPath) {
		const result = step6_annotateLifespan(scoped, previousReviewPath);
		final = result.findings;
		lifespanAnnotations = result.lifespanAnnotations;
	}

	// Output
	const output: OutputPayload = {
		processed_findings: final,
		dropped_count: droppedCount,
		dedup_count: dedupCount,
		lifespan_annotations: lifespanAnnotations,
	};

	process.stdout.write(JSON.stringify(output, null, 2) + "\n");
}

main();
