#!/usr/bin/env npx tsx
/**
 * emit-chunk-index.ts - Deterministic chunk index + findings shards + Phase-0 envelope
 *
 * Derives the buddy-mode lazy-loading sidecars from artifacts already on disk:
 * 1. Parses the journey file's `## Manual Review Guide` into `### Step N` chunks
 * 2. Joins processed-findings.json against each chunk's `**Files:**` list
 *    (a finding belongs to a chunk if its `file` appears in that list — the same
 *    rule review-pr-buddy.md applies; membership = exact path match or a
 *    basename/suffix match for journey entries written as bare file names)
 * 3. Writes {cacheDir}/chunk-index.json, {cacheDir}/findings-by-chunk/chunk-{k}.json,
 *    and {cacheDir}/phase0-result.json (the Phase-0 result envelope)
 *
 * Assignment invariants:
 * - Every processed finding lands in EXACTLY ONE shard. Chunks are scanned in
 *   journey order and the first matching chunk wins (mirrors a linear walk).
 * - Findings whose file matches no chunk go to a final CATCH-ALL chunk
 *   (group "Unassigned findings") appended after the journey chunks — never
 *   silently dropped.
 *
 * Journey-less (downshifted-route) support: when no journey file exists
 * (review-pr.md Step 1.7 downshifted path produces none), a single synthetic
 * chunk 0 is emitted covering ALL manifest files with ALL findings
 * (complexity "trivial", journey_lines null) so buddy walks downshifted PRs
 * through the same per-chunk loop.
 *
 * Usage:
 *   npx tsx emit-chunk-index.ts --cache-dir <cacheDir> [--journey <path>]
 *
 * --journey overrides journey discovery (default: manifest.journeyFile, then
 * <cogDocsItemDir>/PR-{pr}-journey.md; neither present → journey-less mode).
 */

import { existsSync, mkdirSync, readFileSync, writeFileSync } from "fs";
import { join, basename, resolve } from "path";

// ── Types ──────────────────────────────────────────────────────────────────────

interface ManifestFile {
	path: string;
	cachedDiff?: string;
	[key: string]: unknown;
}

interface Manifest {
	pr?: number;
	cacheDir?: string;
	journeyFile?: string;
	files: ManifestFile[];
	[key: string]: unknown;
}

interface PrContext {
	prId?: number;
	cogDocsItemDir?: string | null;
	[key: string]: unknown;
}

interface ProcessedFinding {
	file: string;
	line?: number;
	title?: string;
	source: string;
	[key: string]: unknown;
}

interface ProcessedFindings {
	processed_findings: ProcessedFinding[];
	[key: string]: unknown;
}

interface FindingRef {
	finding_ref: string;
	source: string;
	offset_in_processed: number;
}

interface Chunk {
	index: number;
	group: string;
	complexity: "trivial" | "non-trivial";
	files: string[];
	journey_lines: [number, number] | null;
	diff_paths: string[];
	finding_refs: FindingRef[];
}

interface ChunkIndex {
	chunks: Chunk[];
}

interface Phase0Result {
	pr_id: number | string;
	cacheDir: string;
	cogDocsItemDir: string | null;
	journey_path: string | null;
	chunk_count: number;
	finding_counts: Record<string, number>;
	chunk_index_path: string;
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function error(msg: string): void {
	process.stderr.write(`[emit-chunk-index] ${msg}\n`);
}

function loadJSON<T>(filePath: string, label: string): T {
	try {
		const raw = readFileSync(filePath, "utf-8");
		return JSON.parse(raw) as T;
	} catch (err) {
		error(`Failed to load ${label} at ${filePath}: ${err}`);
		return process.exit(1);
	}
}

function loadOptionalJSON<T>(filePath: string): T | null {
	if (!existsSync(filePath)) return null;
	try {
		return JSON.parse(readFileSync(filePath, "utf-8")) as T;
	} catch {
		return null;
	}
}

/** Canonical finding ref per buddy's Finding ID Convention: `<basename>:<line>`,
 *  or `<basename>#<slug>` for line-less findings. */
function findingRefId(f: ProcessedFinding): string {
	const base = basename(f.file);
	if (typeof f.line === "number" && f.line > 0) {
		return `${base}:${f.line}`;
	}
	const slug = String(f.title ?? "finding")
		.toLowerCase()
		.replace(/[^a-z0-9]+/g, "-")
		.replace(/^-+|-+$/g, "")
		.slice(0, 40) || "finding";
	return `${base}#${slug}`;
}

/** Normalize a path for matching: forward slashes, no leading ./ */
function normPath(p: string): string {
	return p.replace(/\\/g, "/").replace(/^\.\//, "");
}

/** Does a finding's file match one of a chunk's Files entries?
 *  Exact path match, or suffix match for entries written as bare basenames /
 *  partial paths (journey Files lists sometimes name `FooTests.cs` without a dir). */
function fileMatchesEntry(findingFile: string, entry: string): boolean {
	const f = normPath(findingFile);
	const e = normPath(entry);
	if (f === e) return true;
	if (f.endsWith("/" + e)) return true;
	if (e.endsWith("/" + f)) return true;
	return false;
}

// ── Journey parsing ────────────────────────────────────────────────────────────

interface JourneyChunk {
	group: string;
	complexity: "trivial" | "non-trivial";
	files: string[];
	journey_lines: [number, number];
}

/** Parse `### Step N: {Group}` chunks out of the journey's Manual Review Guide.
 *  journey_lines are 1-based inclusive [heading line, last line before the next
 *  heading or section]. Files are the backtick-quoted tokens in the chunk's
 *  `**Files:**` bullet(s). Complexity defaults to non-trivial when absent/ambiguous
 *  (the conservative direction buddy already takes). */
function parseJourneyChunks(journeyText: string): JourneyChunk[] {
	const lines = journeyText.split(/\r?\n/);
	const guideStart = lines.findIndex(l => /^##\s+Manual Review Guide\b/.test(l));
	if (guideStart === -1) return [];

	// Guide ends at the next `## ` heading (or EOF)
	let guideEnd = lines.length;
	for (let i = guideStart + 1; i < lines.length; i++) {
		if (/^##\s+/.test(lines[i]) && !/^###/.test(lines[i])) {
			guideEnd = i;
			break;
		}
	}

	const stepHeadings: Array<{ line: number; group: string }> = [];
	for (let i = guideStart; i < guideEnd; i++) {
		const m = lines[i].match(/^###\s+Step\s+\d+:\s*(.+)$/);
		if (m) stepHeadings.push({ line: i, group: m[1].trim() });
	}

	const chunks: JourneyChunk[] = [];
	for (let s = 0; s < stepHeadings.length; s++) {
		const start = stepHeadings[s].line;
		const end = s + 1 < stepHeadings.length ? stepHeadings[s + 1].line - 1 : guideEnd - 1;
		const body = lines.slice(start, end + 1).join("\n");

		// Files: every backtick-quoted token inside the **Files:** bullet (which may wrap lines
		// until the next **Key:** bullet)
		const filesMatch = body.match(/\*\*Files:\*\*([\s\S]*?)(?=\n\s*-\s+\*\*|\n###|$)/);
		const files: string[] = [];
		if (filesMatch) {
			for (const m of filesMatch[1].matchAll(/`([^`]+)`/g)) {
				const token = m[1].trim();
				// Keep only path-shaped tokens (contain a dot-extension); skip symbol names
				// like `GetWalletPaymentMethods` mentioned in parentheticals.
				if (/\.[A-Za-z0-9]+$/.test(token) && !files.includes(token)) {
					files.push(token);
				}
			}
		}

		const complexityMatch = body.match(/\*\*Complexity:\*\*\s*(\S+)/);
		const complexity: "trivial" | "non-trivial" =
			complexityMatch && complexityMatch[1].toLowerCase().startsWith("trivial")
				? "trivial"
				: "non-trivial";

		chunks.push({
			group: stepHeadings[s].group,
			complexity,
			files,
			journey_lines: [start + 1, end + 1], // 1-based inclusive
		});
	}
	return chunks;
}

// ── CLI ────────────────────────────────────────────────────────────────────────

interface CliArgs {
	cacheDir: string;
	journeyPath: string | null;
}

function parseArgs(argv: string[]): CliArgs {
	const args = argv.slice(2);
	let cacheDir = "";
	let journeyPath: string | null = null;

	for (let i = 0; i < args.length; i++) {
		const arg = args[i];
		if (arg === "--cache-dir" && args[i + 1]) {
			cacheDir = args[++i];
		} else if (arg === "--journey" && args[i + 1]) {
			journeyPath = args[++i];
		}
	}

	if (!cacheDir) {
		error("Missing required --cache-dir argument");
		process.exit(1);
	}

	return { cacheDir: resolve(cacheDir), journeyPath };
}

// ── Main ───────────────────────────────────────────────────────────────────────

function main(): void {
	const { cacheDir, journeyPath: journeyOverride } = parseArgs(process.argv);

	const manifest = loadJSON<Manifest>(join(cacheDir, "manifest.json"), "manifest");
	const processed = loadJSON<ProcessedFindings>(
		join(cacheDir, "processed-findings.json"),
		"processed findings"
	);
	const prContext = loadOptionalJSON<PrContext>(join(cacheDir, "pr-context.json"));

	const cogDocsItemDir = prContext?.cogDocsItemDir ?? null;
	const prId: number | string = prContext?.prId ?? manifest.pr ?? "local";

	// Journey discovery: --journey → manifest.journeyFile → <cogDocsItemDir>/PR-{pr}-journey.md
	let journeyPath: string | null = null;
	const candidates = [
		journeyOverride,
		manifest.journeyFile,
		cogDocsItemDir && typeof prId === "number"
			? join(cogDocsItemDir, `PR-${prId}-journey.md`)
			: null,
	];
	for (const c of candidates) {
		if (c && existsSync(c)) {
			journeyPath = resolve(c);
			break;
		}
	}

	const findings = processed.processed_findings ?? [];

	// Per-source finding counts for the envelope (all sources present in the data)
	const findingCounts: Record<string, number> = {
		investigation: 0,
		sweep: 0,
		reuse: 0,
		intrafile: 0,
	};
	for (const f of findings) {
		findingCounts[f.source] = (findingCounts[f.source] ?? 0) + 1;
	}

	// Build chunks
	const chunks: Chunk[] = [];
	const assigned = new Set<number>(); // offsets already sharded (first match wins)

	if (journeyPath) {
		const journeyChunks = parseJourneyChunks(readFileSync(journeyPath, "utf-8"));
		if (journeyChunks.length === 0) {
			error(`Journey at ${journeyPath} has no '### Step N' chunks under '## Manual Review Guide'`);
			process.exit(1);
		}

		for (let k = 0; k < journeyChunks.length; k++) {
			const jc = journeyChunks[k];
			const refs: FindingRef[] = [];
			for (let i = 0; i < findings.length; i++) {
				if (assigned.has(i)) continue;
				if (jc.files.some(entry => fileMatchesEntry(findings[i].file, entry))) {
					assigned.add(i);
					refs.push({
						finding_ref: findingRefId(findings[i]),
						source: findings[i].source,
						offset_in_processed: i,
					});
				}
			}
			// diff_paths: manifest cachedDiff for every manifest file matching this chunk
			const diffPaths: string[] = [];
			for (const mf of manifest.files) {
				if (jc.files.some(entry => fileMatchesEntry(mf.path, entry)) && mf.cachedDiff) {
					if (!diffPaths.includes(mf.cachedDiff)) diffPaths.push(mf.cachedDiff);
				}
			}
			chunks.push({
				index: k,
				group: jc.group,
				complexity: jc.complexity,
				files: jc.files,
				journey_lines: jc.journey_lines,
				diff_paths: diffPaths,
				finding_refs: refs,
			});
		}

		// Catch-all chunk for findings whose file matched no journey chunk
		const orphans: FindingRef[] = [];
		const orphanFiles: string[] = [];
		for (let i = 0; i < findings.length; i++) {
			if (assigned.has(i)) continue;
			assigned.add(i);
			orphans.push({
				finding_ref: findingRefId(findings[i]),
				source: findings[i].source,
				offset_in_processed: i,
			});
			const nf = normPath(findings[i].file);
			if (!orphanFiles.includes(nf)) orphanFiles.push(nf);
		}
		if (orphans.length > 0) {
			const diffPaths: string[] = [];
			for (const mf of manifest.files) {
				if (orphanFiles.some(of => fileMatchesEntry(mf.path, of)) && mf.cachedDiff) {
					if (!diffPaths.includes(mf.cachedDiff)) diffPaths.push(mf.cachedDiff);
				}
			}
			chunks.push({
				index: chunks.length,
				group: "Unassigned findings",
				complexity: "non-trivial",
				files: orphanFiles,
				journey_lines: null,
				diff_paths: diffPaths,
				finding_refs: orphans,
			});
		}
	} else {
		// Journey-less (downshifted route): single synthetic chunk over all manifest files
		const refs: FindingRef[] = findings.map((f, i) => {
			assigned.add(i);
			return {
				finding_ref: findingRefId(f),
				source: f.source,
				offset_in_processed: i,
			};
		});
		chunks.push({
			index: 0,
			group: "Downshifted review (whole PR)",
			complexity: "trivial",
			files: manifest.files.map(f => normPath(f.path)),
			journey_lines: null,
			diff_paths: manifest.files.map(f => f.cachedDiff).filter((p): p is string => !!p),
			finding_refs: refs,
		});
	}

	// ── Write outputs ────────────────────────────────────────────────────────────

	const chunkIndexPath = join(cacheDir, "chunk-index.json");
	const chunkIndex: ChunkIndex = { chunks };
	writeFileSync(chunkIndexPath, JSON.stringify(chunkIndex, null, 2) + "\n", "utf-8");

	const shardDir = join(cacheDir, "findings-by-chunk");
	mkdirSync(shardDir, { recursive: true });
	for (const chunk of chunks) {
		const shard = {
			chunk: chunk.index,
			group: chunk.group,
			findings: chunk.finding_refs.map(r => findings[r.offset_in_processed]),
		};
		writeFileSync(
			join(shardDir, `chunk-${chunk.index}.json`),
			JSON.stringify(shard, null, 2) + "\n",
			"utf-8"
		);
	}

	const envelope: Phase0Result = {
		pr_id: prId,
		cacheDir,
		cogDocsItemDir,
		journey_path: journeyPath,
		chunk_count: chunks.length,
		finding_counts: findingCounts,
		chunk_index_path: chunkIndexPath,
	};
	const envelopePath = join(cacheDir, "phase0-result.json");
	writeFileSync(envelopePath, JSON.stringify(envelope, null, 2) + "\n", "utf-8");

	// Assignment invariant check: every finding sharded exactly once
	if (assigned.size !== findings.length) {
		error(`invariant violation: ${findings.length} findings, ${assigned.size} sharded`);
		process.exit(1);
	}

	error(
		`wrote ${chunks.length} chunk(s), ${findings.length} finding(s) sharded ` +
		`(journey: ${journeyPath ? basename(journeyPath) : "none — downshifted single-chunk"})`
	);
	process.stdout.write(envelopePath + "\n");
}

main();
