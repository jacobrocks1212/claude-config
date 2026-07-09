#!/usr/bin/env npx tsx
/**
 * disposition-calibration.ts - EMA weight calibration from buddy-session dispositions
 *
 * Statistical design (bug: pr-review-ema-calibration-statistical-design-drives-lane-death):
 *   - PER-PR AGGREGATION: one EMA step per (rule | source) key per run — the signal is the
 *     kept/total ratio of that run's dispositions for the key, never N sequential steps
 *     (which let a single review multiplicatively crater a weight, e.g. 0.7 × 0.75^8 ≈ 0.075).
 *   - CLAMP: calibrated weights land in [WEIGHT_FLOOR, WEIGHT_CEIL] (weight-constants.ts),
 *     with WEIGHT_FLOOR > MIN_EFFECTIVE_WEIGHT so calibration alone can never push a lane
 *     under post-process's drop threshold.
 *   - ANNEALED ALPHA: alpha = min(ema_alpha, max(0.05, 1/(n+1))) where n = the key's
 *     data_points before this run.
 *
 * Weights are read from / written to the live state file (~/.claude/state/cognito-pr-review/
 * weights.yaml, seeded from the plugin's shipped defaults) unless --weights overrides.
 * source_weights entries use the nested { weight, data_points } schema; legacy bare-scalar
 * entries are still read (and surgically rewritten in place, weight only).
 */
import { readFileSync, writeFileSync, existsSync } from "fs";
import { basename } from "path";
import yaml from "js-yaml";
import {
	annealedAlpha,
	clampWeight,
	ensureWeightsState,
	normalizeSourceWeight,
	type SourceWeightEntry,
} from "./weight-constants.ts";

// ── Types ──────────────────────────────────────────────────────────────────────

interface Disposition {
	finding_ref: string;
	source: string;
	severity: string;
	note?: string;
}

interface BuddyChunk {
	index: number;
	status?: string;
	dispositions: Disposition[];
	[key: string]: unknown;
}

interface BuddySession {
	pr_id?: number;
	cache_dir?: string;
	chunks: BuddyChunk[];
	[key: string]: unknown;
}

interface ProcessedFinding {
	source: string;
	file: string;
	line: number;
	rule_id?: string;
	[key: string]: unknown;
}

interface ProcessedFindingsFile {
	processed_findings?: ProcessedFinding[];
}

interface RuleWeight {
	weight: number;
	data_points: number;
}

interface WeightsConfig {
	version?: number;
	ema_alpha?: number;
	// Nested { weight, data_points } schema; legacy bare-scalar entries still accepted.
	source_weights: Record<string, number | SourceWeightEntry>;
	rule_weights: Record<string, RuleWeight>;
	[key: string]: unknown;
}

interface Delta {
	key: string;
	kind: "rule" | "source";
	oldVal: number;
	newVal: number;
	newDataPoints: number;
	signal: number;
	alpha: number;
	samples: number;
	legacyScalar: boolean;
}

// ── CLI ────────────────────────────────────────────────────────────────────────

interface CliArgs {
	sessionPath: string;
	findingsPath: string;
	weightsPath: string;
	dryRun: boolean;
}

function parseArgs(argv: string[]): CliArgs {
	const args = argv.slice(2);
	let sessionPath = "";
	let findingsPath = "";
	let weightsPath = "";
	let dryRun = false;

	for (let i = 0; i < args.length; i++) {
		const arg = args[i];
		if (arg === "--session" && args[i + 1]) {
			sessionPath = args[++i];
		} else if (arg === "--findings" && args[i + 1]) {
			findingsPath = args[++i];
		} else if (arg === "--weights" && args[i + 1]) {
			weightsPath = args[++i];
		} else if (arg === "--dry-run") {
			dryRun = true;
		}
	}

	if (!sessionPath) {
		process.stderr.write("[disposition-calibration] Missing required --session argument\n");
		process.exit(1);
	}
	if (!findingsPath) {
		process.stderr.write("[disposition-calibration] Missing required --findings argument\n");
		process.exit(1);
	}
	if (!weightsPath) {
		// Default to the live mutable state file (seeded from shipped defaults on first
		// use) — calibration must never write into the plugin's versioned cache copy.
		weightsPath = ensureWeightsState();
	}

	return { sessionPath, findingsPath, weightsPath, dryRun };
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function normalizeSep(p: string): string {
	return p.replace(/\\/g, "/");
}

function normalizeBasename(p: string): string {
	return basename(normalizeSep(p)).toLowerCase();
}

function parseFindingRef(ref: string): { file: string; line: number } | null {
	const m = /^(.*?):(\d+)/.exec(ref);
	if (!m) return null;
	const file = m[1].trim();
	const line = parseInt(m[2], 10);
	return { file, line };
}

function joinDispositionToFinding(
	disp: Disposition,
	findings: ProcessedFinding[]
): ProcessedFinding | null {
	const parsed = parseFindingRef(disp.finding_ref);
	if (!parsed) return null;

	const refBase = normalizeBasename(parsed.file);
	const refLine = parsed.line;

	for (const f of findings) {
		if (f.source !== disp.source) continue;
		if (f.line !== refLine) continue;
		const fBase = normalizeBasename(f.file);
		if (fBase === refBase || normalizeSep(f.file).toLowerCase().endsWith("/" + refBase)) {
			return f;
		}
	}
	return null;
}

function toSignal(severity: string): number {
	return severity === "dismiss" ? 0.0 : 1.0;
}

function applyEma(alpha: number, signal: number, old: number): number {
	return parseFloat((alpha * signal + (1 - alpha) * old).toFixed(4));
}

// ── Surgical text replacement ──────────────────────────────────────────────────

/**
 * Surgically update a source_weights entry inside the source_weights: section only.
 * Handles the nested { weight, data_points } schema; falls back to the legacy
 * bare-scalar form (weight replaced in place; data_points has nowhere to live).
 */
function replaceSourceEntry(text: string, source: string, newWeight: number, newDp: number): string {
	const lines = text.split("\n");

	// Locate the top-level source_weights: section
	let i = 0;
	while (i < lines.length && lines[i].replace(/\r$/, "") !== "source_weights:") i++;
	if (i >= lines.length) return text;
	i++;

	const nestedHeader = `  ${source}:`;
	const scalarRe = new RegExp(`^(  ${source}:[ \\t]+)[\\d.]+`);

	while (i < lines.length) {
		const stripped = lines[i].replace(/\r$/, "");

		// Left the section: a non-empty line that is neither indented nor a comment
		if (stripped.length > 0 && !stripped.startsWith(" ") && !stripped.startsWith("#")) break;

		if (stripped === nestedHeader) {
			// Nested form: scan the entry's indented fields
			i++;
			let weightReplaced = false;
			let dpReplaced = false;
			while (i < lines.length) {
				const fieldStripped = lines[i].replace(/\r$/, "");
				if (fieldStripped.length > 0 && !fieldStripped.startsWith("    ") && !fieldStripped.startsWith("\t")) break;
				if (!weightReplaced && /^    weight:/.test(fieldStripped)) {
					lines[i] = lines[i].replace(/(^\s*weight:\s*)[\d.]+/, `$1${newWeight}`);
					weightReplaced = true;
				} else if (!dpReplaced && /^    data_points:/.test(fieldStripped)) {
					lines[i] = lines[i].replace(/(^\s*data_points:\s*)[\d]+/, `$1${newDp}`);
					dpReplaced = true;
				}
				if (weightReplaced && dpReplaced) break;
				i++;
			}
			return lines.join("\n");
		}

		if (scalarRe.test(stripped)) {
			// Legacy scalar form — replace the weight in place
			lines[i] = lines[i].replace(scalarRe, `$1${newWeight}`);
			return lines.join("\n");
		}

		i++;
	}

	return text;
}

function replaceRuleWeight(text: string, ruleId: string, newWeight: number, newDp: number): string {
	const lines = text.split("\n");
	const ruleHeader = `  ${ruleId}:`;
	let i = 0;
	while (i < lines.length && lines[i].replace(/\r$/, "") !== ruleHeader) i++;
	if (i >= lines.length) return text;

	i++;
	let weightReplaced = false;
	let dpReplaced = false;

	while (i < lines.length) {
		const line = lines[i];
		const stripped = line.replace(/\r$/, "");
		if (stripped.length > 0 && !stripped.startsWith("    ") && !stripped.startsWith("\t")) break;
		if (!weightReplaced && /^    weight:/.test(stripped)) {
			lines[i] = line.replace(/(^\s*weight:\s*)[\d.]+/, `$1${newWeight}`);
			weightReplaced = true;
		} else if (!dpReplaced && /^    data_points:/.test(stripped)) {
			lines[i] = line.replace(/(^\s*data_points:\s*)[\d]+/, `$1${newDp}`);
			dpReplaced = true;
		}
		if (weightReplaced && dpReplaced) break;
		i++;
	}

	return lines.join("\n");
}

// ── Main ───────────────────────────────────────────────────────────────────────

function main(): void {
	const { sessionPath, findingsPath, weightsPath, dryRun } = parseArgs(process.argv);

	// Guarded session read: a cache without a buddy session is a normal condition
	// (non-buddy review), not a crash.
	if (!existsSync(sessionPath)) {
		process.stdout.write(
			"[disposition-calibration] no session file — nothing to calibrate (non-buddy cache?)\n"
		);
		return;
	}

	const sessionRaw = readFileSync(sessionPath, "utf-8");
	const session = JSON.parse(sessionRaw) as BuddySession;

	const findingsRaw = readFileSync(findingsPath, "utf-8");
	const findingsFile = JSON.parse(findingsRaw) as ProcessedFindingsFile | ProcessedFinding[];
	const findings: ProcessedFinding[] = Array.isArray(findingsFile)
		? findingsFile
		: (findingsFile.processed_findings ?? []);

	const weightsRawText = readFileSync(weightsPath, "utf-8");
	const weights = yaml.load(weightsRawText) as WeightsConfig;

	const alpha = weights.ema_alpha ?? 0.25;

	const allDispositions: Disposition[] = (session.chunks ?? []).flatMap(
		(c) => c.dispositions ?? []
	);

	if (allDispositions.length === 0) {
		process.stdout.write("no dispositions to calibrate — weights unchanged\n");
		return;
	}

	const SKIP_SOURCES = new Set(["reviewer"]);
	const SWEEP_SOURCE = "sweep";

	// ── Per-PR aggregation: bucket this run's dispositions per (rule | source) key ──
	// One EMA step per key per run; signal = kept/total for the key.
	interface Aggregate {
		kind: "rule" | "source";
		key: string;
		kept: number;
		total: number;
	}
	const aggregates = new Map<string, Aggregate>();

	for (const disp of allDispositions) {
		if (SKIP_SOURCES.has(disp.source)) continue;

		const matched = joinDispositionToFinding(disp, findings);
		if (!matched) {
			process.stderr.write(
				`[disposition-calibration] unmatched disposition: ${disp.finding_ref} (source=${disp.source})\n`
			);
			continue;
		}

		let kind: "rule" | "source";
		let key: string;
		if (matched.source === SWEEP_SOURCE && matched.rule_id && weights.rule_weights[matched.rule_id]) {
			kind = "rule";
			key = matched.rule_id;
		} else if (disp.source !== SWEEP_SOURCE && weights.source_weights[disp.source] !== undefined) {
			kind = "source";
			key = disp.source;
		} else {
			continue;
		}

		const aggKey = `${kind}|${key}`;
		let agg = aggregates.get(aggKey);
		if (!agg) {
			agg = { kind, key, kept: 0, total: 0 };
			aggregates.set(aggKey, agg);
		}
		agg.total++;
		agg.kept += toSignal(disp.severity);
	}

	const deltas: Delta[] = [];

	for (const agg of aggregates.values()) {
		const signal = parseFloat((agg.kept / agg.total).toFixed(4));

		if (agg.kind === "rule") {
			const entry = weights.rule_weights[agg.key];
			const effectiveAlpha = annealedAlpha(alpha, entry.data_points ?? 0);
			const newWeight = parseFloat(clampWeight(applyEma(effectiveAlpha, signal, entry.weight)).toFixed(4));
			deltas.push({
				key: agg.key,
				kind: "rule",
				oldVal: entry.weight,
				newVal: newWeight,
				newDataPoints: (entry.data_points ?? 0) + 1,
				signal,
				alpha: effectiveAlpha,
				samples: agg.total,
				legacyScalar: false,
			});
		} else {
			const rawEntry = weights.source_weights[agg.key];
			const entry = normalizeSourceWeight(rawEntry)!;
			const effectiveAlpha = annealedAlpha(alpha, entry.data_points);
			const newWeight = parseFloat(clampWeight(applyEma(effectiveAlpha, signal, entry.weight)).toFixed(4));
			deltas.push({
				key: agg.key,
				kind: "source",
				oldVal: entry.weight,
				newVal: newWeight,
				newDataPoints: entry.data_points + 1,
				signal,
				alpha: effectiveAlpha,
				samples: agg.total,
				legacyScalar: typeof rawEntry === "number",
			});
		}
	}

	if (deltas.length === 0) {
		process.stdout.write("no dispositions to calibrate — weights unchanged\n");
		return;
	}

	if (!dryRun) {
		let text = weightsRawText;

		for (const d of deltas) {
			if (d.kind === "source") {
				text = replaceSourceEntry(text, d.key, d.newVal, d.newDataPoints);
			} else {
				text = replaceRuleWeight(text, d.key, d.newVal, d.newDataPoints);
			}
		}

		writeFileSync(weightsPath, text, "utf-8");
	}

	process.stdout.write("Calibration delta summary:\n");
	for (const d of deltas) {
		process.stdout.write(
			`  ${d.key}: ${d.oldVal} → ${d.newVal} (signal ${d.signal} over ${d.samples} disposition(s), α ${d.alpha})\n`
		);
	}
	if (dryRun) {
		process.stdout.write("(dry run — weights file not written)\n");
	}
}

main();
