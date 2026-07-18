import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { detectReReview, readReviewedSha } from "./prep-pr.ts";

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
