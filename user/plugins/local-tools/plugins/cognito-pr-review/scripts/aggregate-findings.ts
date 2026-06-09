#!/usr/bin/env npx tsx

import * as fs from "fs";
import * as path from "path";

// ── Interfaces ──────────────────────────────────────────────────────────────

interface InvestigationFinding {
  file: string;
  line: number;
  severity: "blocking" | "important" | "nit";
  title: string;
  hypothesis: string;
  evidence: { snippet: string; reference: string };
  suggestion: string;
  escalation_candidate: boolean;
  specialist_domain: string | null;
}

interface SweepFinding {
  file: string;
  line: number;
  severity: "blocking" | "important" | "nit";
  title: string;
  description: string;
  suggestion: string;
  rule_id: string;
  rule_category: string;
  effective_weight: number;
  tier: "critical" | "important" | "skim";
  escalation_candidate: boolean;
  specialist_domain: string | null;
}

interface Escalation {
  file: string;
  line: number;
  domain: string;
  concern: string;
  severity_estimate: string;
}

interface InvestigationGroup {
  findings: InvestigationFinding[];
  escalations: Escalation[];
  group: string;
}

interface SweepData {
  findings: SweepFinding[];
  escalations: Escalation[];
}

interface CombinedFindings {
  investigation: InvestigationGroup[];
  reuse: InvestigationGroup[];
  intrafile: InvestigationGroup[];
  sweep: SweepData;
  manifest_path: string;
  previous_review_path?: string;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function stripBom(content: string): string {
  return content.charCodeAt(0) === 0xfeff ? content.slice(1) : content;
}

function readJson(filePath: string): unknown {
  const raw = fs.readFileSync(filePath, "utf8");
  return JSON.parse(stripBom(raw));
}

function parseArgs(): {
  cacheDir: string;
  manifestPath: string;
  previousReviewPath?: string;
} {
  const argv = process.argv.slice(2);
  let cacheDir: string | undefined;
  let manifestPath: string | undefined;
  let previousReviewPath: string | undefined;

  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--cache-dir" && argv[i + 1]) {
      cacheDir = argv[++i];
    } else if (argv[i] === "--manifest" && argv[i + 1]) {
      manifestPath = argv[++i];
    } else if (argv[i] === "--previous-review" && argv[i + 1]) {
      previousReviewPath = argv[++i];
    }
  }

  if (!cacheDir) {
    process.stderr.write("Error: --cache-dir is required\n");
    process.exit(1);
  }
  if (!manifestPath) {
    process.stderr.write("Error: --manifest is required\n");
    process.exit(1);
  }

  return { cacheDir, manifestPath, previousReviewPath };
}

function filenameSlug(filePath: string): string {
  return path.basename(filePath, path.extname(filePath));
}

// ── Main ─────────────────────────────────────────────────────────────────────

function main() {
  const { cacheDir, manifestPath, previousReviewPath } = parseArgs();

  const agentOutputDir = path.join(cacheDir, "agent-output");

  // ── Read investigation files ─────────────────────────────────────────────

  const investigationGroups: InvestigationGroup[] = [];

  let investigationFiles: string[] = [];
  if (fs.existsSync(agentOutputDir)) {
    investigationFiles = fs
      .readdirSync(agentOutputDir)
      .filter((f) => f.startsWith("investigation-") && f.endsWith(".json"))
      .map((f) => path.join(agentOutputDir, f))
      .sort();
  }

  for (const filePath of investigationFiles) {
    let data: unknown;
    try {
      data = readJson(filePath);
    } catch (err) {
      process.stderr.write(
        `Warning: Failed to parse ${filePath}: ${(err as Error).message}\n`
      );
      continue;
    }

    if (typeof data !== "object" || data === null) {
      process.stderr.write(
        `Warning: ${filePath} has invalid structure (not an object), skipping\n`
      );
      continue;
    }

    const record = data as Record<string, unknown>;

    // Validate findings array
    if (!Array.isArray(record["findings"])) {
      process.stderr.write(
        `Warning: ${filePath} missing or invalid "findings" array, skipping\n`
      );
      continue;
    }

    // Validate escalations array
    const escalations: Escalation[] = Array.isArray(record["escalations"])
      ? (record["escalations"] as Escalation[])
      : [];

    // Resolve group name
    let group: string;
    if (typeof record["group"] === "string" && record["group"].trim() !== "") {
      group = record["group"];
    } else {
      const slug = filenameSlug(filePath);
      process.stderr.write(
        `Warning: ${filePath} missing "group" field — using filename slug "${slug}"\n`
      );
      group = slug;
    }

    investigationGroups.push({
      group,
      findings: record["findings"] as InvestigationFinding[],
      escalations,
    });
  }

  // ── Read reuse files ─────────────────────────────────────────────────────

  const reuseGroups: InvestigationGroup[] = [];

  let reuseFiles: string[] = [];
  if (fs.existsSync(agentOutputDir)) {
    reuseFiles = fs
      .readdirSync(agentOutputDir)
      .filter((f) => f.startsWith("reuse-") && f.endsWith(".json"))
      .map((f) => path.join(agentOutputDir, f))
      .sort();
  }

  for (const filePath of reuseFiles) {
    let data: unknown;
    try {
      data = readJson(filePath);
    } catch (err) {
      process.stderr.write(
        `Warning: Failed to parse ${filePath}: ${(err as Error).message}\n`
      );
      continue;
    }

    if (typeof data !== "object" || data === null) {
      process.stderr.write(
        `Warning: ${filePath} has invalid structure (not an object), skipping\n`
      );
      continue;
    }

    const record = data as Record<string, unknown>;

    // Validate findings array
    if (!Array.isArray(record["findings"])) {
      process.stderr.write(
        `Warning: ${filePath} missing or invalid "findings" array, skipping\n`
      );
      continue;
    }

    // Validate escalations array
    const escalations: Escalation[] = Array.isArray(record["escalations"])
      ? (record["escalations"] as Escalation[])
      : [];

    // Resolve group name
    let group: string;
    if (typeof record["group"] === "string" && record["group"].trim() !== "") {
      group = record["group"];
    } else {
      const slug = filenameSlug(filePath);
      process.stderr.write(
        `Warning: ${filePath} missing "group" field — using filename slug "${slug}"\n`
      );
      group = slug;
    }

    reuseGroups.push({
      group,
      findings: record["findings"] as InvestigationFinding[],
      escalations,
    });
  }

  // ── Read intrafile files ─────────────────────────────────────────────────

  const intrafileGroups: InvestigationGroup[] = [];

  let intrafileFiles: string[] = [];
  if (fs.existsSync(agentOutputDir)) {
    intrafileFiles = fs
      .readdirSync(agentOutputDir)
      .filter((f) => f.startsWith("intrafile-") && f.endsWith(".json"))
      .map((f) => path.join(agentOutputDir, f))
      .sort();
  }

  for (const filePath of intrafileFiles) {
    let data: unknown;
    try {
      data = readJson(filePath);
    } catch (err) {
      process.stderr.write(
        `Warning: Failed to parse ${filePath}: ${(err as Error).message}\n`
      );
      continue;
    }

    if (typeof data !== "object" || data === null) {
      process.stderr.write(
        `Warning: ${filePath} has invalid structure (not an object), skipping\n`
      );
      continue;
    }

    const record = data as Record<string, unknown>;

    // Validate findings array
    if (!Array.isArray(record["findings"])) {
      process.stderr.write(
        `Warning: ${filePath} missing or invalid "findings" array, skipping\n`
      );
      continue;
    }

    // Validate escalations array
    const escalations: Escalation[] = Array.isArray(record["escalations"])
      ? (record["escalations"] as Escalation[])
      : [];

    // Resolve group name
    let group: string;
    if (typeof record["group"] === "string" && record["group"].trim() !== "") {
      group = record["group"];
    } else {
      const slug = filenameSlug(filePath);
      process.stderr.write(
        `Warning: ${filePath} missing "group" field — using filename slug "${slug}"\n`
      );
      group = slug;
    }

    intrafileGroups.push({
      group,
      findings: record["findings"] as InvestigationFinding[],
      escalations,
    });
  }

  // ── Read sweep file ───────────────────────────────────────────────────────

  const sweepPath = path.join(agentOutputDir, "sweep.json");
  let sweep: SweepData = { findings: [], escalations: [] };

  if (fs.existsSync(sweepPath)) {
    let sweepData: unknown;
    try {
      sweepData = readJson(sweepPath);
    } catch (err) {
      process.stderr.write(
        `Warning: Failed to parse sweep.json: ${(err as Error).message} — using empty sweep\n`
      );
    }

    if (sweepData !== undefined) {
      if (typeof sweepData !== "object" || sweepData === null) {
        process.stderr.write(
          `Warning: sweep.json has invalid structure (not an object) — using empty sweep\n`
        );
      } else {
        const sweepRecord = sweepData as Record<string, unknown>;
        const sweepFindings = Array.isArray(sweepRecord["findings"])
          ? (sweepRecord["findings"] as SweepFinding[])
          : [];
        const sweepEscalations = Array.isArray(sweepRecord["escalations"])
          ? (sweepRecord["escalations"] as Escalation[])
          : [];

        if (!Array.isArray(sweepRecord["findings"])) {
          process.stderr.write(
            `Warning: sweep.json missing or invalid "findings" array — defaulting to []\n`
          );
        }

        sweep = { findings: sweepFindings, escalations: sweepEscalations };
      }
    }
  } else {
    process.stderr.write(
      `Warning: sweep.json not found in ${agentOutputDir} — using empty sweep section\n`
    );
  }

  // ── Guard: nothing to aggregate ───────────────────────────────────────────

  if (investigationGroups.length === 0 && reuseGroups.length === 0 && intrafileGroups.length === 0 && sweep.findings.length === 0) {
    process.stderr.write(
      "Error: No investigation files, reuse files, intrafile files, and no sweep findings found — nothing to aggregate\n"
    );
    process.exit(1);
  }

  // ── Assemble combined findings ────────────────────────────────────────────

  const combined: CombinedFindings = {
    investigation: investigationGroups,
    reuse: reuseGroups,
    intrafile: intrafileGroups,
    sweep,
    manifest_path: manifestPath,
    ...(previousReviewPath ? { previous_review_path: previousReviewPath } : {}),
  };

  // ── Write output ──────────────────────────────────────────────────────────

  const outputPath = path.join(cacheDir, "combined-findings.json");
  fs.writeFileSync(outputPath, JSON.stringify(combined, null, 2), "utf8");

  // ── Summary stats to stderr ───────────────────────────────────────────────

  const totalInvestigationFindings = investigationGroups.reduce(
    (sum, g) => sum + g.findings.length,
    0
  );

  const totalReuseFindings = reuseGroups.reduce(
    (sum, g) => sum + g.findings.length,
    0
  );

  process.stderr.write(
    `Aggregation complete:\n` +
      `  Investigation groups : ${investigationGroups.length}\n` +
      `  Total inv. findings  : ${totalInvestigationFindings}\n` +
      `  Reuse groups         : ${reuseGroups.length}\n` +
      `  Total reuse findings : ${totalReuseFindings}\n` +
      `  Sweep findings       : ${sweep.findings.length}\n`
  );

  // ── Output path to stdout ─────────────────────────────────────────────────

  process.stdout.write(outputPath + "\n");
}

main();
