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

describe("disposition-calibration per-PR aggregation + clamp + annealing", () => {
	const eightDismissPath = join(fxDir, "disp-buddy-session-8dismiss.json");
	const nestedFixturePath = join(fxDir, "disp-weights-nested.yaml");

	function copyNestedToTemp(label: string): string {
		const dest = join(os.tmpdir(), `disp-weights-nested-${label}-${Date.now()}.yaml`);
		fs.copyFileSync(nestedFixturePath, dest);
		return dest;
	}

	interface NestedWeightsFile {
		ema_alpha: number;
		source_weights: Record<string, number | { weight: number; data_points: number }>;
		rule_weights: Record<string, RuleWeight>;
	}

	test("8 dismissals in one run = ONE bounded EMA step on a legacy scalar (0.9 → 0.675, not 0.9·0.75^8)", () => {
		const weightsFile = copyWeightsToTemp("8dismiss");
		runCli(eightDismissPath, weightsFile);
		const w = loadWeights(weightsFile);
		assert.strictEqual(
			w.source_weights["investigation"],
			0.675,
			`expected ONE aggregated step 0.25*0 + 0.75*0.9 = 0.675 but got ${w.source_weights["investigation"]} (sequential-step bug would give ≈0.09)`
		);
	});

	test("nested schema: 8 dismissals clamp at WEIGHT_FLOOR 0.35 and increment data_points", () => {
		const weightsFile = copyNestedToTemp("clamp");
		runCli(eightDismissPath, weightsFile);
		const raw = fs.readFileSync(weightsFile, "utf-8");
		const w = yaml.load(raw) as NestedWeightsFile;
		const inv = w.source_weights["investigation"] as { weight: number; data_points: number };
		// 0.25*0 + 0.75*0.38 = 0.285 → clamped to 0.35
		assert.strictEqual(inv.weight, 0.35, `expected clamp at 0.35 but got ${inv.weight}`);
		assert.strictEqual(inv.data_points, 4, `expected data_points 3+1=4 but got ${inv.data_points}`);
		assert.ok(raw.includes("# nested-schema comment preservation check"), "comments must survive the surgical write");
	});

	test("annealed alpha: rule with data_points 9 moves at alpha 0.1, not ema_alpha 0.25", () => {
		const weightsFile = copyNestedToTemp("anneal");
		runCli(sessionPath, weightsFile);
		const w = yaml.load(fs.readFileSync(weightsFile, "utf-8")) as NestedWeightsFile;
		// sweep dismiss on appropriate-http-methods (data_points 9): alpha = min(0.25, max(0.05, 1/10)) = 0.1
		// 0.1*0 + 0.9*0.7 = 0.63
		assert.strictEqual(w.rule_weights["appropriate-http-methods"].weight, 0.63);
		assert.strictEqual(w.rule_weights["appropriate-http-methods"].data_points, 10);
		// nested investigation entry (data_points 3): kept → alpha 0.25 → 0.25*1 + 0.75*0.38 = 0.535
		const inv = w.source_weights["investigation"] as { weight: number; data_points: number };
		assert.strictEqual(inv.weight, 0.535);
		assert.strictEqual(inv.data_points, 4);
		// mixed schema: legacy scalar reuse entry still updates in place
		assert.strictEqual(w.source_weights["reuse"], 0.525);
	});
});

describe("disposition-calibration guarded session read (bug 4 helper half)", () => {
	test("missing session file → clean diagnostic exit, not an ENOENT stack", () => {
		const weightsFile = copyWeightsToTemp("missing-session");
		const before = fs.readFileSync(weightsFile, "utf-8");
		const missingSession = join(os.tmpdir(), `no-such-session-${Date.now()}.json`);

		let out = "";
		let cliError: unknown = null;
		try {
			out = execSync(
				`npx tsx disposition-calibration.ts --session "${missingSession}" --findings "${findingsPath}" --weights "${weightsFile}"`,
				{ cwd: scriptsDir, encoding: "utf-8" }
			);
		} catch (err) {
			cliError = err;
		}

		assert.ok(cliError === null, `CLI must exit 0 on a missing session file but threw: ${cliError}`);
		assert.ok(
			out.includes("no session file — nothing to calibrate"),
			`stdout must carry the diagnostic, got: ${out}`
		);
		const after = fs.readFileSync(weightsFile, "utf-8");
		assert.strictEqual(after, before, "weights must be untouched when there is no session");
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
