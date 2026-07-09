/**
 * weight-constants.ts - Shared weight constants + mutable-weights state resolution
 *
 * Single source of truth for the weight-threshold constants consumed by BOTH
 * post-process.ts and disposition-calibration.ts (bug: pr-review-ema-calibration-
 * statistical-design-drives-lane-death), and for the mutable-weights state file
 * (bug: pr-review-plugin-cache-split-brain-freezes-weights).
 *
 * Weights split:
 *   - `knowledge/weights.yaml` (plugin) = SHIPPED DEFAULTS seed, versioned with the plugin.
 *   - `~/.claude/state/cognito-pr-review/weights.yaml` = LIVE mutable copy. Seeded from the
 *     shipped defaults on first use; all calibration writes land here, so learned weights
 *     survive plugin version bumps and are never served stale from the plugin cache.
 *
 * Set COGNITO_PR_REVIEW_STATE_DIR to relocate the state dir (used by tests to sandbox).
 */

import { readFileSync, writeFileSync, mkdirSync, existsSync } from "fs";
import { dirname, join, resolve } from "path";
import { fileURLToPath } from "url";
import { homedir } from "os";

// ── Constants ──────────────────────────────────────────────────────────────────

/** Findings from the sweep lane below this effective weight are dropped by post-process. */
export const MIN_EFFECTIVE_WEIGHT = 0.3;

/** Calibration may never drive a weight below this floor... */
export const WEIGHT_FLOOR = 0.35;

/** ...or above this ceiling. Floor > MIN_EFFECTIVE_WEIGHT so calibration alone can never
 * push a lane's CONFIRMED findings under the drop threshold. */
export const WEIGHT_CEIL = 1.0;

// ── Types ──────────────────────────────────────────────────────────────────────

/** Nested source_weights entry. Legacy files carry a bare scalar instead. */
export interface SourceWeightEntry {
	weight: number;
	data_points: number;
}

// ── Helpers ────────────────────────────────────────────────────────────────────

/** Clamp a calibrated weight into [WEIGHT_FLOOR, WEIGHT_CEIL]. */
export function clampWeight(w: number): number {
	return Math.min(WEIGHT_CEIL, Math.max(WEIGHT_FLOOR, w));
}

/**
 * Annealed EMA alpha: fast to move while a key has little data, settling as data
 * accumulates — alpha = max(0.05, 1/(n+1)), capped at the configured ema_alpha.
 */
export function annealedAlpha(emaAlpha: number, dataPoints: number): number {
	return Math.min(emaAlpha, Math.max(0.05, 1 / (dataPoints + 1)));
}

/** Normalize a source_weights entry: legacy scalar → { weight, data_points: 0 }. */
export function normalizeSourceWeight(
	v: number | SourceWeightEntry | undefined
): SourceWeightEntry | undefined {
	if (v === undefined || v === null) return undefined;
	if (typeof v === "number") return { weight: v, data_points: 0 };
	return { weight: v.weight, data_points: v.data_points ?? 0 };
}

/** Path of the shipped-defaults seed (the plugin's knowledge/weights.yaml). */
export function seedWeightsPath(): string {
	const scriptDir = dirname(fileURLToPath(import.meta.url));
	return resolve(scriptDir, "..", "knowledge", "weights.yaml");
}

/** Path of the live mutable weights state file. */
export function weightsStatePath(): string {
	const overrideDir = process.env.COGNITO_PR_REVIEW_STATE_DIR;
	const stateDir =
		overrideDir && overrideDir.length > 0
			? overrideDir
			: join(
					process.env.USERPROFILE || process.env.HOME || homedir(),
					".claude",
					"state",
					"cognito-pr-review"
				);
	return join(stateDir, "weights.yaml");
}

/**
 * Ensure the mutable weights state file exists, seeding it from the shipped
 * defaults when absent. Returns the state file path.
 */
export function ensureWeightsState(): string {
	const statePath = weightsStatePath();
	if (!existsSync(statePath)) {
		const seed = readFileSync(seedWeightsPath(), "utf-8");
		mkdirSync(dirname(statePath), { recursive: true });
		writeFileSync(statePath, seed, "utf-8");
	}
	return statePath;
}
