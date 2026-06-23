import { execSync } from "node:child_process";
import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import * as fs from "node:fs";
import * as os from "node:os";
import yaml from "js-yaml";

const scriptsDir = dirname(fileURLToPath(import.meta.url));
const fxDir = join(scriptsDir, "test-fixtures");

const sessionPath = join(fxDir, "disp-buddy-session.json");
const emptySessionPath = join(fxDir, "disp-buddy-session-empty.json");
const findingsPath = join(fxDir, "disp-processed-findings.json");
const weightsFixturePath = join(fxDir, "disp-weights.yaml");

interface RuleWeight {
	weight: number;
	data_points: number;
}

interface WeightsFile {
	version: number;
	ema_alpha: number;
	source_weights: Record<string, number>;
	rule_weights: Record<string, RuleWeight>;
	[key: string]: unknown;
}

function copyWeightsToTemp(label: string): string {
	const dest = join(os.tmpdir(), `disp-weights-${label}-${Date.now()}.yaml`);
	fs.copyFileSync(weightsFixturePath, dest);
	return dest;
}

function runCli(sessionFile: string, weightsFile: string): void {
	const cmd =
		`npx tsx disposition-calibration.ts` +
		` --session "${sessionFile}"` +
		` --findings "${findingsPath}"` +
		` --weights "${weightsFile}"`;
	execSync(cmd, { cwd: scriptsDir, encoding: "utf-8" });
}

function loadWeights(weightsFile: string): WeightsFile {
	const raw = fs.readFileSync(weightsFile, "utf-8");
	return yaml.load(raw) as WeightsFile;
}

describe("disposition-calibration EMA updates", () => {
	// Run CLI once and share the resulting weights file across tests 1–4 and 6.
	const sharedWeightsPath = copyWeightsToTemp("shared");

	// Expected failure: disposition-calibration.ts does not exist yet.
	// This call will throw, so wrap it to let node:test catch the failure per-test.
	let ranSuccessfully = false;
	let sharedWeights: WeightsFile | null = null;

	try {
		runCli(sessionPath, sharedWeightsPath);
		sharedWeights = loadWeights(sharedWeightsPath);
		ranSuccessfully = true;
	} catch {
		// CLI missing — all tests below will fail with meaningful messages.
	}

	test("sweep dismiss → rule weight updated to 0.525 and data_points incremented to 1", () => {
		assert.ok(
			ranSuccessfully,
			"CLI must run successfully (disposition-calibration.ts not found or errored)"
		);
		const w = sharedWeights!;
		assert.ok(
			w.rule_weights["appropriate-http-methods"] !== undefined,
			"rule_weights must contain appropriate-http-methods"
		);
		assert.strictEqual(
			w.rule_weights["appropriate-http-methods"].weight,
			0.525,
			`expected weight 0.525 (0.25*0 + 0.75*0.7) but got ${w.rule_weights["appropriate-http-methods"].weight}`
		);
		assert.strictEqual(
			w.rule_weights["appropriate-http-methods"].data_points,
			1,
			`expected data_points 1 but got ${w.rule_weights["appropriate-http-methods"].data_points}`
		);
	});

	test("kept investigation → source_weights.investigation updated to 0.925", () => {
		assert.ok(
			ranSuccessfully,
			"CLI must run successfully (disposition-calibration.ts not found or errored)"
		);
		const w = sharedWeights!;
		assert.strictEqual(
			w.source_weights["investigation"],
			0.925,
			`expected source_weights.investigation 0.925 (0.25*1 + 0.75*0.9) but got ${w.source_weights["investigation"]}`
		);
	});

	test("reuse dismiss → source_weights.reuse updated to 0.525 and no new rule key created", () => {
		assert.ok(
			ranSuccessfully,
			"CLI must run successfully (disposition-calibration.ts not found or errored)"
		);
		const w = sharedWeights!;
		assert.strictEqual(
			w.source_weights["reuse"],
			0.525,
			`expected source_weights.reuse 0.525 (0.25*0 + 0.75*0.7) but got ${w.source_weights["reuse"]}`
		);
		// The reuse finding should NOT have created a new rule entry — rule_weights must only
		// contain the original appropriate-http-methods key (modified) from the fixture.
		const ruleKeys = Object.keys(w.rule_weights);
		assert.deepEqual(
			ruleKeys,
			["appropriate-http-methods"],
			`rule_weights must contain exactly ["appropriate-http-methods"] but got [${ruleKeys.join(", ")}]`
		);
	});

	test("reviewer disposition skipped — no unexpected keys in weights", () => {
		assert.ok(
			ranSuccessfully,
			"CLI must run successfully (disposition-calibration.ts not found or errored)"
		);
		const w = sharedWeights!;
		// Only three things should have changed from the fixture:
		//   rule_weights.appropriate-http-methods (sweep dismiss)
		//   source_weights.investigation (kept)
		//   source_weights.reuse (dismiss)
		// source_weights.intrafile must be unchanged (no intrafile disposition in session).
		assert.strictEqual(
			w.source_weights["intrafile"],
			0.7,
			`source_weights.intrafile must be unchanged at 0.7 but got ${w.source_weights["intrafile"]}`
		);
		// No entry for qux.ts or reviewer should have spawned any rule key.
		assert.ok(
			!Object.keys(w.rule_weights).some((k) => k.includes("qux")),
			"no rule key related to qux.ts (reviewer finding) should exist"
		);
	});

	test("comments preserved — literal '# api-design rules' still present after write", () => {
		assert.ok(
			ranSuccessfully,
			"CLI must run successfully (disposition-calibration.ts not found or errored)"
		);
		const raw = fs.readFileSync(sharedWeightsPath, "utf-8");
		assert.ok(
			raw.includes("# api-design rules"),
			"written weights file must still contain the comment '# api-design rules' (no yaml.dump round-trip)"
		);
	});
});

describe("disposition-calibration zero-disposition no-op", () => {
	test("empty session leaves weights file byte-for-byte identical", () => {
		const tempWeightsPath = copyWeightsToTemp("empty-session");
		const before = fs.readFileSync(tempWeightsPath, "utf-8");

		let cliError: unknown = null;
		try {
			runCli(emptySessionPath, tempWeightsPath);
		} catch (err) {
			cliError = err;
		}

		assert.ok(
			cliError === null,
			`CLI must exit 0 for zero-disposition session but threw: ${cliError}`
		);

		const after = fs.readFileSync(tempWeightsPath, "utf-8");
		assert.strictEqual(
			after,
			before,
			"weights file must be byte-for-byte identical when no dispositions are present"
		);
	});
});
