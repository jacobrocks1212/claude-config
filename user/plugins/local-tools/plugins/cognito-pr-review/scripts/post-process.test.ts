import { execSync } from "node:child_process";
import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const scriptsDir = dirname(fileURLToPath(import.meta.url));
const fxPath = join(scriptsDir, "test-fixtures", "phase1-combined-findings.json");
const mfPath = join(scriptsDir, "test-fixtures", "phase1-manifest.json");

function runCli(): { processed_findings: ProcessedFinding[]; dropped_count: number; dedup_count: number } {
	const cmd = `npx tsx post-process.ts --input "${fxPath}" --manifest "${mfPath}"`;
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
