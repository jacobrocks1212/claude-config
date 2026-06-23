#!/usr/bin/env npx tsx
import { readFileSync, writeFileSync } from "fs";
import { resolve, dirname, basename } from "path";
import { fileURLToPath } from "url";
import yaml from "js-yaml";

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
	source_weights: Record<string, number>;
	rule_weights: Record<string, RuleWeight>;
	[key: string]: unknown;
}

interface Delta {
	key: string;
	kind: "rule" | "source";
	oldVal: number;
	newVal: number;
	signal: number;
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

	const scriptDir = dirname(fileURLToPath(import.meta.url));

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
		weightsPath = resolve(scriptDir, "..", "knowledge", "weights.yaml");
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

function replaceSourceScalar(text: string, source: string, newVal: number): string {
	const re = new RegExp(`(^  ${source}:[ \\t]+)[\\d.]+`, "m");
	return text.replace(re, `$1${newVal}`);
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

	const deltas: Delta[] = [];

	const mutableWeights: WeightsConfig = {
		...weights,
		source_weights: { ...weights.source_weights },
		rule_weights: Object.fromEntries(
			Object.entries(weights.rule_weights).map(([k, v]) => [k, { ...v }])
		),
	};

	for (const disp of allDispositions) {
		if (SKIP_SOURCES.has(disp.source)) continue;

		const matched = joinDispositionToFinding(disp, findings);
		if (!matched) {
			process.stderr.write(
				`[disposition-calibration] unmatched disposition: ${disp.finding_ref} (source=${disp.source})\n`
			);
			continue;
		}

		const signal = toSignal(disp.severity);

		if (matched.source === SWEEP_SOURCE && matched.rule_id && mutableWeights.rule_weights[matched.rule_id]) {
			const entry = mutableWeights.rule_weights[matched.rule_id];
			const oldWeight = entry.weight;
			const newWeight = applyEma(alpha, signal, oldWeight);
			deltas.push({ key: matched.rule_id, kind: "rule", oldVal: oldWeight, newVal: newWeight, signal });
			entry.weight = newWeight;
			entry.data_points = entry.data_points + 1;
		} else if (disp.source !== SWEEP_SOURCE && mutableWeights.source_weights[disp.source] !== undefined) {
			const oldVal = mutableWeights.source_weights[disp.source];
			const newVal = applyEma(alpha, signal, oldVal);
			deltas.push({ key: disp.source, kind: "source", oldVal, newVal, signal });
			mutableWeights.source_weights[disp.source] = newVal;
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
				text = replaceSourceScalar(text, d.key, d.newVal);
			} else {
				const entry = mutableWeights.rule_weights[d.key];
				text = replaceRuleWeight(text, d.key, d.newVal, entry.data_points);
			}
		}

		writeFileSync(weightsPath, text, "utf-8");
	}

	process.stdout.write("Calibration delta summary:\n");
	for (const d of deltas) {
		process.stdout.write(
			`  ${d.key}: ${d.oldVal} → ${d.newVal} (signal ${d.signal})\n`
		);
	}
	if (dryRun) {
		process.stdout.write("(dry run — weights file not written)\n");
	}
}

main();
