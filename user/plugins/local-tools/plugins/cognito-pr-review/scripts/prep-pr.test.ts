import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import * as fs from "node:fs";
import * as os from "node:os";

import { pathToFileURL } from "node:url";
import { detectReReview, readReviewedSha, computeIterationDiff, isMainModuleInvocation } from "./prep-pr.ts";

const scriptsDir = dirname(fileURLToPath(import.meta.url));
const fxDir = join(scriptsDir, "test-fixtures");
const withShaDir = join(fxDir, "rereview-with-sha");
const legacyDir = join(fxDir, "rereview-legacy");

describe("prep-pr re-review anchor via persisted reviewed SHA (RC-2a)", () => {
	test("REVIEWED.md carrying reviewed_sha resolves the previous anchor to that SHA (not a journey round number)", () => {
		const info = detectReReview(101, withShaDir);
		assert.strictEqual(info.isReReview, true, "journey present → re-review");
		assert.strictEqual(
			info.reviewedSha,
			"abc1234def5678abc1234def5678abc1234def56",
			`reviewedSha must be the persisted SHA, got ${info.reviewedSha}`
		);
	});

	test("readReviewedSha parses the frontmatter reviewed_sha directly", () => {
		assert.strictEqual(readReviewedSha(withShaDir), "abc1234def5678abc1234def5678abc1234def56");
	});

	test("legacy REVIEWED.md without reviewed_sha → reviewedSha null, journey ### Iteration N scrape preserved (regression guard)", () => {
		const info = detectReReview(102, legacyDir);
		assert.strictEqual(info.isReReview, true, "journey present → re-review");
		assert.strictEqual(info.reviewedSha, null, "legacy REVIEWED.md has no reviewed_sha → null anchor");
		assert.strictEqual(info.previousIterationId, 3, `journey fallback must yield max ### Iteration N (3), got ${info.previousIterationId}`);
	});

	test("no REVIEWED.md at all → readReviewedSha null (does not throw)", () => {
		assert.strictEqual(readReviewedSha(fxDir), null);
	});

	test("initial review (no journey) still returns a reviewedSha field", () => {
		// scriptsDir has no PR-999-journey.md → not a re-review; reviewedSha resolves from
		// any REVIEWED.md in that dir (none here) → null. Field must exist (shape guard).
		const info = detectReReview(999, scriptsDir);
		assert.strictEqual(info.isReReview, false);
		assert.strictEqual(info.reviewedSha, null);
	});
});

describe("prep-pr merge-safe base-relative iteration diff (RC-2b)", () => {
	const iterations = [
		{ id: 1, createdDate: "", sourceRefCommit: { commitId: "PREV" }, targetRefCommit: { commitId: "" } },
		{ id: 2, createdDate: "", sourceRefCommit: { commitId: "CUR" }, targetRefCommit: { commitId: "" } },
	];

	// Injectable compare stub keyed on (base, head). Models the merge-commit-head scenario:
	//  - base-relative endpoints surface the branch-only changes and CANCEL merged-in main churn;
	//  - the legacy three-dot PREV...CUR would instead surface main churn and drop branch files.
	function compareStub(base: string, head: string) {
		if (base === "BASE" && head === "CUR") {
			return Promise.resolve([
				{ filename: "Cognito/Rewrite.cs", status: "modified", sha: "cur-rewrite" },
				{ filename: "Cognito/New.cs", status: "added", sha: "new-1" },
			]);
		}
		if (base === "BASE" && head === "PREV") {
			// Rewrite.cs was already branch-changed as of previous (different blob); New.cs not yet.
			return Promise.resolve([
				{ filename: "Cognito/Rewrite.cs", status: "modified", sha: "prev-rewrite" },
			]);
		}
		if (base === "PREV" && head === "CUR") {
			// The buggy three-dot path: dominated by merged-in main churn, branch files dropped.
			return Promise.resolve([
				{ filename: "Billing/TestClock.cs", status: "modified", sha: "m1" },
				{ filename: "Ai/FormGen.cs", status: "modified", sha: "m2" },
				{ filename: "Marketing/Template.cs", status: "modified", sha: "m3" },
			]);
		}
		return Promise.resolve([]);
	}

	function tmpCacheDir(): string {
		return fs.mkdtempSync(join(os.tmpdir(), "prep-diff-"));
	}

	test("merge-commit head: delta INCLUDES branch-only files and EXCLUDES merged-in main churn", async () => {
		const cacheDir = tmpCacheDir();
		const diff = await computeIterationDiff(42, 2, 1, "tok", cacheDir, iterations, undefined, {
			baseRef: "BASE",
			fetchCompare: compareStub,
		});
		const all = [...diff.filesAdded, ...diff.filesModified, ...diff.filesRemoved];
		assert.ok(all.includes("Cognito/Rewrite.cs"), "re-modified branch file must appear (blob sha changed since previous)");
		assert.ok(diff.filesAdded.includes("Cognito/New.cs"), "newly-added branch file must appear as added");
		for (const churn of ["Billing/TestClock.cs", "Ai/FormGen.cs", "Marketing/Template.cs"]) {
			assert.ok(!all.includes(churn), `merged-in main churn (${churn}) must be excluded`);
		}
	});

	test("non-merge head: delta equals the straightforward branch changes (no regression)", async () => {
		const cacheDir = tmpCacheDir();
		// previous had no branch changes; current has one modified + one added → both surface.
		const simpleStub = (base: string, head: string) => {
			if (base === "BASE" && head === "CUR") {
				return Promise.resolve([
					{ filename: "Cognito/Foo.cs", status: "modified", sha: "f1" },
					{ filename: "Cognito/Bar.cs", status: "added", sha: "b1" },
				]);
			}
			return Promise.resolve([]);
		};
		const diff = await computeIterationDiff(42, 2, 1, "tok", cacheDir, iterations, undefined, {
			baseRef: "BASE",
			fetchCompare: simpleStub,
		});
		assert.deepEqual(diff.filesModified.sort(), ["Cognito/Foo.cs"]);
		assert.deepEqual(diff.filesAdded.sort(), ["Cognito/Bar.cs"]);
	});

	test("empty-diff guard: unresolved endpoint SHA returns an empty IterationDiffData", async () => {
		const cacheDir = tmpCacheDir();
		const emptyIters = [{ id: 1, createdDate: "", sourceRefCommit: { commitId: "PREV" }, targetRefCommit: { commitId: "" } }];
		// currentIterationId = 2 has no entry → currentSha unresolved.
		const diff = await computeIterationDiff(42, 2, 1, "tok", cacheDir, emptyIters, undefined, {
			baseRef: "BASE",
			fetchCompare: compareStub,
		});
		assert.deepEqual(diff.filesAdded, []);
		assert.deepEqual(diff.filesModified, []);
		assert.deepEqual(diff.filesRemoved, []);
	});
});

describe("prep-pr main-module detection is symlink-agnostic (documented ~/.claude/plugins path)", () => {
	function tmpDir(): string {
		return fs.mkdtempSync(join(os.tmpdir(), "prep-mainmod-"));
	}

	test("a module reached through a symlink is still detected as the CLI entry point", () => {
		const dir = tmpDir();
		const realTarget = join(dir, "real-prep.ts");
		const linkPath = join(dir, "linked-prep.ts");
		fs.writeFileSync(realTarget, "// entry point\n");
		try {
			fs.symlinkSync(realTarget, linkPath, "file");
		} catch (err: any) {
			// Windows without symlink privilege / dev mode — the invariant is untestable here.
			if (err && (err.code === "EPERM" || err.code === "ENOSYS" || err.code === "UnknownSystemError")) return;
			throw err;
		}
		// Module loaded from the REAL path (import.meta.url), process launched via the SYMLINK
		// path (argv[1]) — the exact divergence that made the CLI silently no-op.
		const moduleUrl = pathToFileURL(realTarget).href;
		assert.strictEqual(
			isMainModuleInvocation(moduleUrl, linkPath),
			true,
			"realpath of module URL and of the symlinked argv[1] resolve to the same file → entry point"
		);
	});

	test("a direct (non-symlink) invocation is still detected as the CLI entry point", () => {
		const dir = tmpDir();
		const realTarget = join(dir, "real-prep.ts");
		fs.writeFileSync(realTarget, "// entry point\n");
		assert.strictEqual(isMainModuleInvocation(pathToFileURL(realTarget).href, realTarget), true);
	});

	test("importing the module (argv[1] is a different file) is NOT detected as the entry point", () => {
		const dir = tmpDir();
		const modulePath = join(dir, "prep.ts");
		const importerPath = join(dir, "test-runner.ts");
		fs.writeFileSync(modulePath, "// module\n");
		fs.writeFileSync(importerPath, "// importer\n");
		assert.strictEqual(
			isMainModuleInvocation(pathToFileURL(modulePath).href, importerPath),
			false,
			"module imported by a different entry file must not run the CLI dispatch"
		);
	});

	test("missing argv[1] is NOT detected as the entry point", () => {
		const dir = tmpDir();
		const modulePath = join(dir, "prep.ts");
		fs.writeFileSync(modulePath, "// module\n");
		assert.strictEqual(isMainModuleInvocation(pathToFileURL(modulePath).href, undefined), false);
	});
});
