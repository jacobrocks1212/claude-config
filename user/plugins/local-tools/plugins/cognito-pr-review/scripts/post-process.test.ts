import { execSync } from "node:child_process";
import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import * as fs from "node:fs";
import * as os from "node:os";

const scriptsDir = dirname(fileURLToPath(import.meta.url));
const fxPath = join(scriptsDir, "test-fixtures", "phase1-combined-findings.json");
const mfPath = join(scriptsDir, "test-fixtures", "phase1-manifest.json");
const wtPath = join(scriptsDir, "test-fixtures", "phase1-weights.yaml");

interface CliPayload {
	processed_findings: ProcessedFinding[];
	dropped_count: number;
	dedup_count: number;
	scope_filtered_count: number;
	lane_zeroed: string[];
	drops: Array<{ step: number; stage: string; reason: string; source: string; file: string; line: number }>;
}

function runCli(): CliPayload {
	// --weights pins the test to a fixture weights file (the live state file drifts by design)
	const cmd = `npx tsx post-process.ts --input "${fxPath}" --manifest "${mfPath}" --weights "${wtPath}"`;
	const out = execSync(cmd, { cwd: scriptsDir, encoding: "utf-8" });
	return JSON.parse(out);
}

interface ProcessedFinding {
	source: string;
	file: string;
	line: number;
	effective_weight: number;
	[key: string]: unknown;
}

function findByFile(findings: ProcessedFinding[], file: string): ProcessedFinding | undefined {
	return findings.find(f => f.file === file);
}

function findAllByFile(findings: ProcessedFinding[], file: string): ProcessedFinding[] {
	return findings.filter(f => f.file === file);
}

function approx(a: number, b: number): boolean {
	return Math.abs(a - b) < 1e-9;
}

describe("post-process weight generalization", () => {
	let result: ReturnType<typeof runCli>;

	test("CLI produces parseable output with processed_findings array", () => {
		result = runCli();
		assert.ok(Array.isArray(result.processed_findings), "processed_findings must be an array");
		assert.ok(typeof result.dropped_count === "number", "dropped_count must be a number");
	});

	test("investigation finding without confidence is weighted at source_weights.investigation (0.9)", () => {
		if (!result) result = runCli();
		const f = findByFile(result.processed_findings, "A.cs");
		assert.ok(f !== undefined, "investigation finding on A.cs must be present");
		assert.strictEqual(f.effective_weight, 0.9);
	});

	test("reuse finding without confidence is weighted at source_weights.reuse (0.7)", () => {
		if (!result) result = runCli();
		const f = findByFile(result.processed_findings, "B.cs");
		assert.ok(f !== undefined, "reuse finding on B.cs must be present");
		assert.strictEqual(f.effective_weight, 0.7);
	});

	test("intrafile finding without confidence is weighted at source_weights.intrafile (0.7)", () => {
		if (!result) result = runCli();
		const f = findByFile(result.processed_findings, "C.cs");
		assert.ok(f !== undefined, "intrafile finding on C.cs must be present");
		assert.strictEqual(f.effective_weight, 0.7);
	});

	test("sweep finding effective_weight is rule_weight * category_multiplier (0.7 * 0.8 = 0.56)", () => {
		if (!result) result = runCli();
		const f = findByFile(result.processed_findings, "D.cs");
		assert.ok(f !== undefined, "sweep finding on D.cs must be present");
		assert.ok(
			approx(f.effective_weight, 0.7 * 0.8),
			`expected D.cs effective_weight ≈ ${0.7 * 0.8} but got ${f.effective_weight}`
		);
	});

	test("investigation finding with UNVERIFIED confidence is weighted at 0.9 * 0.5 = 0.45", () => {
		if (!result) result = runCli();
		const f = findByFile(result.processed_findings, "E.cs");
		assert.ok(f !== undefined, "UNVERIFIED investigation finding on E.cs must be present");
		assert.strictEqual(f.effective_weight, 0.45);
	});

	test("intrafile finding with UNVERIFIED confidence survives floor at 0.7 * 0.5 = 0.35", () => {
		if (!result) result = runCli();
		const f = findByFile(result.processed_findings, "F.cs");
		assert.ok(f !== undefined, "UNVERIFIED intrafile finding on F.cs must be present (0.35 >= 0.3 floor)");
		assert.strictEqual(f.effective_weight, 0.35);
	});

	test("sweep finding below floor after confidence multiplier is dropped (0.525 * 0.8 * 0.5 = 0.21 < 0.3)", () => {
		if (!result) result = runCli();
		const g = findByFile(result.processed_findings, "G.cs");
		assert.strictEqual(g, undefined, "G.cs finding with effective_weight 0.21 must be absent from processed_findings");
		assert.ok(result.dropped_count >= 1, `dropped_count should be >= 1 but was ${result.dropped_count}`);
	});

	test("investigation finding beats sweep finding when both target the same file and line (Opus-over-sweep precedence)", () => {
		if (!result) result = runCli();
		const hFindings = findAllByFile(result.processed_findings, "H.cs");
		assert.strictEqual(hFindings.length, 1, "exactly one finding should survive dedup for H.cs:10");
		assert.strictEqual(hFindings[0].source, "investigation", `surviving H.cs finding must come from investigation, got ${hFindings[0].source}`);
	});
});

describe("post-process dedup + scope-filter silent-drop fixes", () => {
	let result: CliPayload;

	test("two DISTINCT same-line investigation findings both survive (no location-only collapse)", () => {
		result = runCli();
		const iFindings = findAllByFile(result.processed_findings, "I.cs");
		assert.strictEqual(iFindings.length, 2, `both distinct I.cs:5 findings must survive, got ${iFindings.length}`);
	});

	test("true same-lane duplicate (same normalized title) still collapses to one", () => {
		if (!result) result = runCli();
		const jFindings = findAllByFile(result.processed_findings, "J.cs");
		assert.strictEqual(jFindings.length, 1, `same-title J.cs:3 duplicates must collapse, got ${jFindings.length}`);
		// Higher effective_weight (the CONFIRMED-by-default one at 0.9) must win over the UNVERIFIED 0.45
		assert.strictEqual(jFindings[0].effective_weight, 0.9);
	});

	test("path-variant './K.cs' matches manifest entry 'K.cs' after normalization", () => {
		if (!result) result = runCli();
		const kFindings = result.processed_findings.filter(f => f.file === "./K.cs");
		assert.strictEqual(kFindings.length, 1, "./K.cs sweep finding must survive the scope filter");
	});

	test("out-of-scope Z.cs is filtered WITH a drop record and counted", () => {
		if (!result) result = runCli();
		const zFindings = result.processed_findings.filter(f => f.file === "Z.cs");
		assert.strictEqual(zFindings.length, 0, "Z.cs must be scope-filtered");
		assert.ok(result.scope_filtered_count >= 1, `scope_filtered_count must be >= 1, got ${result.scope_filtered_count}`);
		const zDrop = result.drops.find(d => d.file === "Z.cs" && d.stage === "scope");
		assert.ok(zDrop !== undefined, "drops[] must contain a scope-stage record for Z.cs");
	});

	test("threshold drop is sweep-scoped and recorded in drops[]", () => {
		if (!result) result = runCli();
		const gDrop = result.drops.find(d => d.file === "G.cs" && d.stage === "threshold");
		assert.ok(gDrop !== undefined, "drops[] must contain a threshold-stage record for G.cs");
		assert.strictEqual(gDrop!.source, "sweep", "only sweep findings may be threshold-dropped");
	});

	test("no lane is zeroed in this fixture (all four lanes keep findings)", () => {
		if (!result) result = runCli();
		assert.deepEqual(result.lane_zeroed, [], `lane_zeroed must be empty, got ${JSON.stringify(result.lane_zeroed)}`);
	});
});

describe("post-process Opus lane immune to threshold (source-weights-drift bug)", () => {
	test("investigation finding survives even when its source weight is below MIN_EFFECTIVE_WEIGHT, and the zeroed sweep lane is flagged", () => {
		// Weights fixture with investigation driven to 0.29 (below the 0.3 threshold):
		// the CONFIRMED investigation finding must survive; sweep sub-threshold must drop.
		const tmpDir = fs.mkdtempSync(join(os.tmpdir(), "pp-lane-"));
		const lowWeights = join(tmpDir, "weights.yaml");
		fs.writeFileSync(
			lowWeights,
			[
				"version: 1",
				"ema_alpha: 0.25",
				"category_multipliers:",
				"  consistency: 0.8",
				"source_weights:",
				"  investigation: 0.29",
				"  intrafile: 0.29",
				"  reuse: 0.29",
				"rule_weights:",
				"  defensive-null-checks:",
				"    weight: 0.2",
				"    data_points: 0",
				"  invalid-hardcoded-entity-id:",
				"    weight: 0.2",
				"    data_points: 0",
				"",
			].join("\n"),
			"utf-8"
		);
		const cmd = `npx tsx post-process.ts --input "${fxPath}" --manifest "${mfPath}" --weights "${lowWeights}"`;
		const result: CliPayload = JSON.parse(execSync(cmd, { cwd: scriptsDir, encoding: "utf-8" }));

		const aFindings = result.processed_findings.filter(f => f.file === "A.cs");
		assert.strictEqual(aFindings.length, 1, "investigation finding at weight 0.29 must NOT be threshold-dropped");
		assert.strictEqual(aFindings[0].effective_weight, 0.29);

		// All sweep rules land at 0.2 * 0.8 = 0.16 < 0.3 → entire sweep lane drops → flagged
		assert.ok(result.lane_zeroed.includes("sweep"), `sweep lane must be flagged as zeroed, got ${JSON.stringify(result.lane_zeroed)}`);
	});
});
