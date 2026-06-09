#!/usr/bin/env npx tsx
/**
 * calibrate-weights.ts - Proximity-based calibration of review rule weights
 *
 * Matches historical plugin review artifacts against actual human ADO review comments
 * to compute TP/FP/FN rates per category, then applies EMA updates to weights.yaml.
 *
 * Usage:
 *   npx tsx calibrate-weights.ts [--dry-run] [--pr PR_ID] [--output-report path]
 */

import * as fs from "fs";
import * as path from "path";
import { execSync } from "child_process";
import yaml from "js-yaml";

// ── Constants ──────────────────────────────────────────────────────────────────

const REVIEWS_DIR = "C:\\Users\\JacobMadsen\\source\\repos\\Cognito Forms\\.claude.local\\reviews";
const WEIGHTS_PATH =
	"C:\\Users\\JacobMadsen\\.claude\\plugins\\local-tools\\plugins\\cognito-pr-review\\knowledge\\weights.yaml";
const DEFAULT_REPORT_PATH =
	"C:\\Users\\JacobMadsen\\.claude\\plugins\\local-tools\\plugins\\cognito-pr-review\\docs\\specs\\cognito-pr-review-v2\\calibration-report.md";
const REVIEWER_NAME = "Jacob Madsen";
const LINE_PROXIMITY = 20;

// ── Types ──────────────────────────────────────────────────────────────────────

interface CliArgs {
	dryRun: boolean;
	prId: string | null;
	outputReport: string;
}

interface ADoComment {
	author: string;
	content: string;
	publishedDate: string;
}

interface ADoThread {
	filePath: string;
	line: number;
	status: string;
	comments: ADoComment[];
}

interface ADoCommentPayload {
	prId: number;
	comments: ADoThread[];
}

interface HumanComment {
	filePath: string;
	line: number;
	content: string;
}

type Severity = "blocking" | "important" | "nit";

interface PluginFinding {
	file: string;
	line: number | null;
	severity: Severity;
	category: string;
	title: string;
	ruleId: null;
}

interface WeightsConfig {
	version: number;
	last_calibrated: string | null;
	calibration_prs: number[];
	ema_alpha: number;
	category_multipliers: Record<string, number>;
	rule_weights: Record<string, { weight: number; data_points: number }>;
}

interface CategoryStats {
	tp: number;
	fp: number;
	fn: number;
	oldMultiplier: number;
	newMultiplier: number;
}

interface MatchDetail {
	prId: number;
	findingFile: string;
	findingLine: number | null;
	commentFile: string;
	commentLine: number;
	matched: boolean;
}

interface FalseNegative {
	prId: number;
	file: string;
	line: number;
	excerpt: string;
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function warn(msg: string): void {
	process.stderr.write(`[calibrate-weights] WARN: ${msg}\n`);
}

function info(msg: string): void {
	process.stderr.write(`[calibrate-weights] ${msg}\n`);
}

/** Strip UTF-8 BOM if present. */
function stripBom(s: string): string {
	return s.charCodeAt(0) === 0xfeff ? s.slice(1) : s;
}

/** Normalize a file path: strip leading slash, convert backslashes, lowercase. */
function normalizePath(filePath: string): string {
	return filePath
		.replace(/^\//, "")
		.replace(/\\/g, "/")
		.toLowerCase();
}

// ── Step 1: Enumerate Review Artifacts ────────────────────────────────────────

function enumerateReviewArtifacts(filterPrId: string | null): { prId: number; filePath: string }[] {
	let files: string[];
	try {
		files = fs.readdirSync(REVIEWS_DIR);
	} catch (err) {
		process.stderr.write(`[calibrate-weights] ERROR: Cannot read reviews directory: ${err}\n`);
		process.exit(1);
	}

	const results: { prId: number; filePath: string }[] = [];

	for (const file of files) {
		// Match PR-{id}.md but skip PR-{id}-journey.md
		const match = /^PR-(\d+)\.md$/.exec(file);
		if (!match) continue;

		const prId = parseInt(match[1], 10);
		if (filterPrId !== null && match[1] !== filterPrId) continue;

		results.push({ prId, filePath: path.join(REVIEWS_DIR, file) });
	}

	return results;
}

// ── Step 2: Fetch ADO Comments ─────────────────────────────────────────────────

function fetchAdoComments(prId: number): HumanComment[] {
	const cmd =
		`powershell.exe -Command "cd 'C:\\Users\\JacobMadsen\\source\\repos\\Cognito Forms'; ` +
		`.\\get-pr-comments.ps1 ${prId} -Format JSON"`;

	let raw: string;
	try {
		raw = execSync(cmd, { encoding: "utf-8", timeout: 30000 }) as string;
	} catch (err) {
		warn(`get-pr-comments.ps1 failed for PR ${prId}: ${err}`);
		return [];
	}

	raw = stripBom(raw).trim();
	if (!raw) {
		warn(`Empty output from get-pr-comments.ps1 for PR ${prId}`);
		return [];
	}

	let payload: ADoCommentPayload;
	try {
		payload = JSON.parse(raw) as ADoCommentPayload;
	} catch (err) {
		warn(`Failed to parse JSON from get-pr-comments.ps1 for PR ${prId}: ${err}`);
		return [];
	}

	const humanComments: HumanComment[] = [];

	for (const thread of payload.comments ?? []) {
		for (const comment of thread.comments ?? []) {
			if (comment.author !== REVIEWER_NAME) continue;
			humanComments.push({
				filePath: normalizePath(thread.filePath ?? ""),
				line: thread.line ?? 0,
				content: comment.content ?? "",
			});
		}
	}

	return humanComments;
}

// ── Step 3: Parse Review Artifacts ────────────────────────────────────────────

/** Determine severity from the section header text. */
function headerToSeverity(header: string): Severity {
	const lower = header.toLowerCase();
	if (lower.includes("critical")) return "blocking";
	if (lower.includes("important") || lower.includes("consistency")) return "important";
	return "nit";
}

function parseReviewArtifact(filePath: string): PluginFinding[] {
	let content: string;
	try {
		content = stripBom(fs.readFileSync(filePath, "utf-8"));
	} catch (err) {
		warn(`Failed to read review artifact ${filePath}: ${err}`);
		return [];
	}

	const findings: PluginFinding[] = [];
	const lines = content.split(/\r?\n/);

	let currentSeverity: Severity = "nit";

	// We scan line-by-line, tracking section headers and parsing finding blocks.
	// Finding block:
	//   ### {number}. [{category}] {title}      (or ###  {number}. [{category}] {title})
	//   **File:** `{path}` or `{path}:{line}`
	//   **Confidence:** {number}%
	//
	// Some reviews use a looser format (numbered list items with inline brackets).

	for (let i = 0; i < lines.length; i++) {
		const line = lines[i];

		// Track section severity via ## headings
		const sectionMatch = /^##\s+(.+)/.exec(line);
		if (sectionMatch) {
			currentSeverity = headerToSeverity(sectionMatch[1]);
			continue;
		}

		// Pattern A: ### {num}. [{category}] {title}
		const findingHeaderA = /^###\s+\d+\.\s+\[([^\]]+)\]\s+(.+)/.exec(line);
		if (findingHeaderA) {
			const category = findingHeaderA[1].toLowerCase().trim();
			const title = findingHeaderA[2].trim();

			// Look ahead for **File:** within next 5 lines
			let file: string | null = null;
			let lineNum: number | null = null;

			for (let j = i + 1; j < Math.min(i + 6, lines.length); j++) {
				const fileLine = lines[j];
				// **File:** `path:line`
				const fileLineMatch = /\*\*File:\*\*\s*`?([^`\n]+)`?/.exec(fileLine);
				if (fileLineMatch) {
					const raw = fileLineMatch[1].trim();
					const colonMatch = /^(.+):(\d+)(?:-\d+)?$/.exec(raw);
					if (colonMatch) {
						file = normalizePath(colonMatch[1]);
						lineNum = parseInt(colonMatch[2], 10);
					} else {
						file = normalizePath(raw);
						lineNum = null;
					}
					break;
				}
			}

			if (file !== null) {
				findings.push({
					file,
					line: lineNum,
					severity: currentSeverity,
					category,
					title,
					ruleId: null,
				});
			}
			continue;
		}

		// Pattern B: numbered list item with inline bracket category (newer format):
		// {num}. **[{category}] Rule: {title}** - `{path}:{line}`
		// e.g.:  1. **[cognito-frontend] Rule: Nullable Type Accuracy** - `billing-field-settings.ts:7`
		const findingHeaderB =
			/^\d+\.\s+\*{0,2}\[([^\]]+)\][^\*]*\*{0,2}\s*[-–]\s*`?([^`\n:]+):(\d+)`?/.exec(line);
		if (findingHeaderB) {
			const category = findingHeaderB[1].toLowerCase().trim();
			const file = normalizePath(findingHeaderB[2].trim());
			const lineNum = parseInt(findingHeaderB[3], 10);

			// Extract title: everything between ** markers or plain text
			const titleMatch = /\*{1,2}([^\*]+)\*{1,2}/.exec(line);
			const title = titleMatch ? titleMatch[1].trim() : line.trim();

			findings.push({
				file,
				line: lineNum,
				severity: currentSeverity,
				category,
				title,
				ruleId: null,
			});
			continue;
		}

		// Pattern C: inline finding with file path in parentheses or brackets (Cognito-Specific Findings)
		// e.g.: - **Orphaned legacy keys** (`Form.MoveBillingFieldSettings.cs:23`): ...
		const findingHeaderC = /^[-*]\s+\*{1,2}([^\*]+)\*{1,2}\s+\(`?([^`)]+):(\d+)`?\)/.exec(line);
		if (findingHeaderC) {
			const title = findingHeaderC[1].trim();
			const file = normalizePath(findingHeaderC[2].trim());
			const lineNum = parseInt(findingHeaderC[3], 10);

			findings.push({
				file,
				line: lineNum,
				severity: currentSeverity,
				category: "consistency",
				title,
				ruleId: null,
			});
			continue;
		}
	}

	return findings;
}

// ── Step 4 & 5: Proximity Matching and Classification ─────────────────────────

interface MatchResult {
	matched: boolean;
	finding: PluginFinding;
	humanComment: HumanComment | null;
}

function runProximityMatching(
	prId: number,
	findings: PluginFinding[],
	humanComments: HumanComment[]
): {
	tpFindings: PluginFinding[];
	fpFindings: PluginFinding[];
	fnComments: HumanComment[];
	details: MatchDetail[];
} {
	const matchedCommentIndices = new Set<number>();
	const tpFindings: PluginFinding[] = [];
	const fpFindings: PluginFinding[] = [];
	const details: MatchDetail[] = [];

	for (const finding of findings) {
		if (finding.line === null) {
			// Can't proximity-match without a line number
			fpFindings.push(finding);
			continue;
		}

		let matched = false;
		let matchedComment: HumanComment | null = null;

		for (let ci = 0; ci < humanComments.length; ci++) {
			const comment = humanComments[ci];
			if (comment.line === 0) continue; // skip comments with no line info

			// Normalize and compare file paths
			if (normalizePath(finding.file) !== normalizePath(comment.filePath)) continue;

			// Check proximity
			if (Math.abs(finding.line - comment.line) <= LINE_PROXIMITY) {
				matched = true;
				matchedComment = comment;
				matchedCommentIndices.add(ci);
				break;
			}
		}

		details.push({
			prId,
			findingFile: finding.file,
			findingLine: finding.line,
			commentFile: matchedComment?.filePath ?? "",
			commentLine: matchedComment?.line ?? 0,
			matched,
		});

		if (matched) {
			tpFindings.push(finding);
		} else {
			fpFindings.push(finding);
		}
	}

	// FN: human comments not matched by any finding
	const fnComments: HumanComment[] = humanComments.filter(
		(_, ci) => !matchedCommentIndices.has(ci) && humanComments[ci].line !== 0
	);

	return { tpFindings, fpFindings, fnComments, details };
}

// ── Step 6: EMA Weight Update ──────────────────────────────────────────────────

function loadWeights(): WeightsConfig {
	const raw = stripBom(fs.readFileSync(WEIGHTS_PATH, "utf-8"));
	return yaml.load(raw) as WeightsConfig;
}

function computeEmaUpdates(
	categoryStats: Map<string, { tp: number; fp: number; fn: number }>,
	weights: WeightsConfig
): Map<string, { oldMultiplier: number; newMultiplier: number }> {
	const alpha = weights.ema_alpha ?? 0.25;
	const updates = new Map<string, { oldMultiplier: number; newMultiplier: number }>();

	for (const [category, stats] of categoryStats) {
		const total = stats.tp + stats.fp;
		if (total === 0) continue;

		const signal = stats.tp / total;
		const oldMultiplier = weights.category_multipliers[category] ?? 1.0;
		const newMultiplier = parseFloat((alpha * signal + (1 - alpha) * oldMultiplier).toFixed(4));

		updates.set(category, { oldMultiplier, newMultiplier });
	}

	return updates;
}

function writeWeights(
	weights: WeightsConfig,
	updates: Map<string, { oldMultiplier: number; newMultiplier: number }>,
	calibratedPrIds: number[]
): void {
	for (const [category, { newMultiplier }] of updates) {
		weights.category_multipliers[category] = newMultiplier;
	}

	weights.last_calibrated = new Date().toISOString().split("T")[0];

	const existingPrs = new Set(weights.calibration_prs ?? []);
	for (const prId of calibratedPrIds) {
		existingPrs.add(prId);
	}
	weights.calibration_prs = Array.from(existingPrs).sort((a, b) => a - b);

	const dumped = yaml.dump(weights, { lineWidth: 120, quotingType: '"' });
	fs.writeFileSync(WEIGHTS_PATH, dumped, "utf-8");
}

// ── Step 7: Output Report ──────────────────────────────────────────────────────

function buildReport(opts: {
	dryRun: boolean;
	prId: string | null;
	analyzedPrIds: number[];
	totalFindings: number;
	totalHumanComments: number;
	categoryStats: Map<string, { tp: number; fp: number; fn: number }>;
	emaUpdates: Map<string, { oldMultiplier: number; newMultiplier: number }>;
	allDetails: MatchDetail[];
	allFalseNegatives: FalseNegative[];
	weights: WeightsConfig;
}): string {
	const {
		dryRun,
		prId,
		analyzedPrIds,
		totalFindings,
		totalHumanComments,
		categoryStats,
		emaUpdates,
		allDetails,
		allFalseNegatives,
		weights,
	} = opts;

	const today = new Date().toISOString().split("T")[0];

	let mode: string;
	if (dryRun && prId) {
		mode = `Dry run — Single PR (PR-${prId})`;
	} else if (dryRun) {
		mode = "Dry run — Full bulk";
	} else if (prId) {
		mode = `Single PR (PR-${prId})`;
	} else {
		mode = "Full bulk";
	}

	const lines: string[] = [
		"# Calibration Report",
		"",
		`**Date:** ${today}`,
		`**Mode:** ${mode}`,
		`**PRs analyzed:** ${analyzedPrIds.length} (${analyzedPrIds.join(", ")})`,
		`**Total plugin findings analyzed:** ${totalFindings}`,
		`**Total human comments analyzed:** ${totalHumanComments}`,
		"",
		"## Per-Category Results",
		"",
		"| Category | TP | FP | FN | Old Multiplier | New Multiplier |",
		"|----------|----|----|-----|----------------|----------------|",
	];

	// Collect all categories (from stats and from weights)
	const allCategories = new Set([
		...categoryStats.keys(),
		...Object.keys(weights.category_multipliers),
	]);

	for (const category of Array.from(allCategories).sort()) {
		const stats = categoryStats.get(category) ?? { tp: 0, fp: 0, fn: 0 };
		const update = emaUpdates.get(category);
		const oldMul = update?.oldMultiplier ?? weights.category_multipliers[category] ?? 1.0;
		const newMul = update?.newMultiplier ?? oldMul;
		lines.push(
			`| ${category} | ${stats.tp} | ${stats.fp} | ${stats.fn} | ${oldMul.toFixed(4)} | ${newMul.toFixed(4)} |`
		);
	}

	lines.push("");
	lines.push("## Proximity Match Details");
	lines.push("");
	lines.push("| PR | Finding File:Line | Comment File:Line | Match |");
	lines.push("|----|-------------------|-------------------|-------|");

	for (const detail of allDetails) {
		const findingLoc = `${detail.findingFile}:${detail.findingLine ?? "?"}`;
		const commentLoc =
			detail.matched ? `${detail.commentFile}:${detail.commentLine}` : "—";
		const matchStr = detail.matched ? "✓" : "✗";
		lines.push(`| ${detail.prId} | ${findingLoc} | ${commentLoc} | ${matchStr} |`);
	}

	lines.push("");
	lines.push("## False Negative Patterns");
	lines.push("");
	lines.push("Human reviewer comments that the plugin missed:");
	lines.push("");

	if (allFalseNegatives.length === 0) {
		lines.push("_(None — all human comments were matched by plugin findings)_");
	} else {
		for (const fn of allFalseNegatives) {
			const excerpt = fn.excerpt.slice(0, 100).replace(/\n/g, " ");
			lines.push(`- **PR #${fn.prId} | ${fn.file}:${fn.line}** — "${excerpt}"`);
		}
	}

	if (dryRun) {
		lines.push("");
		lines.push("## Dry Run Notice");
		lines.push("");
		lines.push(
			"This was a dry run. No changes were written to `weights.yaml`. " +
				"Re-run without `--dry-run` to apply EMA updates."
		);
	}

	lines.push("");

	return lines.join("\n");
}

function writeReport(reportPath: string, content: string): void {
	const dir = path.dirname(reportPath);
	fs.mkdirSync(dir, { recursive: true });
	fs.writeFileSync(reportPath, content, "utf-8");
}

// ── CLI Parsing ────────────────────────────────────────────────────────────────

function parseArgs(argv: string[]): CliArgs {
	const args = argv.slice(2);
	let dryRun = false;
	let prId: string | null = null;
	let outputReport = DEFAULT_REPORT_PATH;

	for (let i = 0; i < args.length; i++) {
		const arg = args[i];
		if (arg === "--dry-run") {
			dryRun = true;
		} else if (arg === "--pr" && args[i + 1]) {
			prId = args[++i];
		} else if (arg === "--output-report" && args[i + 1]) {
			outputReport = args[++i];
		}
	}

	return { dryRun, prId, outputReport };
}

// ── Main ───────────────────────────────────────────────────────────────────────

function main(): void {
	const { dryRun, prId, outputReport } = parseArgs(process.argv);

	info(`Starting calibration (dry-run=${dryRun}, pr=${prId ?? "all"})`);

	// Step 1: Enumerate artifacts
	const artifacts = enumerateReviewArtifacts(prId);
	if (artifacts.length === 0) {
		process.stderr.write(
			`[calibrate-weights] ERROR: No review artifacts found in ${REVIEWS_DIR}\n`
		);
		process.exit(1);
	}
	info(`Found ${artifacts.length} review artifact(s)`);

	// Load weights once up front
	const weights = loadWeights();

	// Accumulate results across PRs
	const categoryStats = new Map<string, { tp: number; fp: number; fn: number }>();
	const allDetails: MatchDetail[] = [];
	const allFalseNegatives: FalseNegative[] = [];
	const analyzedPrIds: number[] = [];
	let totalFindings = 0;
	let totalHumanComments = 0;

	for (const artifact of artifacts) {
		info(`Processing PR ${artifact.prId}...`);

		// Step 2: Fetch ADO comments
		const humanComments = fetchAdoComments(artifact.prId);
		info(`  → ${humanComments.length} human comment(s) from ADO`);

		// Step 3: Parse review artifact
		const findings = parseReviewArtifact(artifact.filePath);
		info(`  → ${findings.length} plugin finding(s) parsed`);

		if (findings.length === 0 && humanComments.length === 0) {
			info(`  → Skipping PR ${artifact.prId} (no data on either side)`);
			continue;
		}

		analyzedPrIds.push(artifact.prId);
		totalFindings += findings.length;
		totalHumanComments += humanComments.length;

		// Step 4 & 5: Proximity matching
		const { tpFindings, fpFindings, fnComments, details } = runProximityMatching(
			artifact.prId,
			findings,
			humanComments
		);

		info(
			`  → TP=${tpFindings.length}, FP=${fpFindings.length}, FN=${fnComments.length}`
		);

		allDetails.push(...details);

		// Accumulate false negatives
		for (const comment of fnComments) {
			allFalseNegatives.push({
				prId: artifact.prId,
				file: comment.filePath,
				line: comment.line,
				excerpt: comment.content,
			});
		}

		// Accumulate category stats
		for (const finding of tpFindings) {
			const cat = finding.category;
			if (!categoryStats.has(cat)) categoryStats.set(cat, { tp: 0, fp: 0, fn: 0 });
			categoryStats.get(cat)!.tp++;
		}
		for (const finding of fpFindings) {
			const cat = finding.category;
			if (!categoryStats.has(cat)) categoryStats.set(cat, { tp: 0, fp: 0, fn: 0 });
			categoryStats.get(cat)!.fp++;
		}
		// FN are attributed to a synthetic category "unmatched-human"
		if (fnComments.length > 0) {
			if (!categoryStats.has("unmatched-human"))
				categoryStats.set("unmatched-human", { tp: 0, fp: 0, fn: 0 });
			categoryStats.get("unmatched-human")!.fn += fnComments.length;
		}
	}

	if (analyzedPrIds.length === 0) {
		process.stderr.write(
			`[calibrate-weights] ERROR: No PRs could be analyzed (all skipped due to errors or empty data)\n`
		);
		process.exit(1);
	}

	// Step 6: EMA updates
	const emaUpdates = computeEmaUpdates(categoryStats, weights);

	if (!dryRun) {
		writeWeights(weights, emaUpdates, analyzedPrIds);
		info(`Wrote updated weights.yaml`);
	} else {
		info(`Dry run — weights.yaml NOT updated`);
	}

	// Step 7: Build and write report
	const report = buildReport({
		dryRun,
		prId,
		analyzedPrIds,
		totalFindings,
		totalHumanComments,
		categoryStats,
		emaUpdates,
		allDetails,
		allFalseNegatives,
		weights,
	});

	writeReport(outputReport, report);
	info(`Calibration report written to ${outputReport}`);

	// Step 8: Summary to stderr
	process.stderr.write("\n── Calibration Summary ────────────────────────────────────\n");
	process.stderr.write(`PRs analyzed:            ${analyzedPrIds.length}\n`);
	process.stderr.write(`Total plugin findings:   ${totalFindings}\n`);
	process.stderr.write(`Total human comments:    ${totalHumanComments}\n`);
	process.stderr.write(`False negatives:         ${allFalseNegatives.length}\n`);
	process.stderr.write(`Category multiplier changes:\n`);
	for (const [cat, { oldMultiplier, newMultiplier }] of emaUpdates) {
		const delta = newMultiplier - oldMultiplier;
		const sign = delta >= 0 ? "+" : "";
		process.stderr.write(
			`  ${cat.padEnd(20)} ${oldMultiplier.toFixed(4)} → ${newMultiplier.toFixed(4)} (${sign}${delta.toFixed(4)})\n`
		);
	}
	if (dryRun) {
		process.stderr.write("(DRY RUN — no changes written)\n");
	}
	process.stderr.write("───────────────────────────────────────────────────────────\n");
}

main();
