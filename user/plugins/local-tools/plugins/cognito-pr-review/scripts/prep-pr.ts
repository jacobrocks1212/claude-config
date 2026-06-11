#!/usr/bin/env npx tsx
/**
 * prep-pr.ts - Deterministic PR preparation script
 *
 * Replaces the Haiku pr-prep agent with deterministic code that uses
 * GitHub REST API directly. This ensures correct file counts
 * regardless of local branch state.
 *
 * Usage:
 *   PR Mode:    npx tsx prep-pr.ts <pr_id> [--force]
 *   Local Mode: npx tsx prep-pr.ts --local [--base <branch>] [--include-untracked]
 *
 * Output (PR mode): writes all artifacts under the resolved cog-docs item dir
 *   (<item>/.pr-review/pr-cache/{pr_id}/), creating docs/bugs/<id>-<slug>/ if none exists,
 *   and hard-fails if no cog-docs repo is present. Local mode still uses .claude/pr-cache/local/.
 *   Prints the manifest JSON to stdout.
 */

import { execSync } from "child_process";
import * as fs from "fs";
import * as path from "path";
import { createTwoFilesPatch } from "diff";

function stripBom(content: string): string {
  return content.charCodeAt(0) === 0xFEFF ? content.slice(1) : content;
}

// Configuration
const GITHUB_OWNER = "cognitoforms";
const GITHUB_REPO = "cognito";

const WORK_GITHUB_ACCOUNT = "jacob-cognitoforms";
const WORK_GITHUB_ORGS = ["cognitoforms"];

function detectGitHubRepo(): { owner: string; repo: string } {
  try {
    const url = execSync("git remote get-url origin", { encoding: "utf-8", timeout: 5000 }).trim();
    const match = url.match(/github\.com[/:]([^/]+)\/([^/.]+)/);
    if (match) return { owner: match[1], repo: match[2] };
  } catch {}
  return { owner: GITHUB_OWNER, repo: GITHUB_REPO };
}

function ensureCorrectGitHubAccount(): void {
  const { owner } = detectGitHubRepo();
  if (!WORK_GITHUB_ORGS.includes(owner.toLowerCase())) return;

  try {
    const statusOutput = execSync("gh auth status 2>&1", { encoding: "utf-8", timeout: 10000 });
    const activeMatch = statusOutput.match(/Logged in to github\.com account (\S+).*Active account: true/s);
    if (!activeMatch) return;

    const activeAccount = activeMatch[1].replace(/\s.*/, "");
    if (activeAccount === WORK_GITHUB_ACCOUNT) return;

    console.error(`Active GitHub account is ${activeAccount}, switching to ${WORK_GITHUB_ACCOUNT}...`);
    execSync(`gh auth switch --user ${WORK_GITHUB_ACCOUNT}`, { encoding: "utf-8", timeout: 10000 });
    console.error(`Switched to ${WORK_GITHUB_ACCOUNT}`);
  } catch (err) {
    console.error(`Warning: Could not verify/switch GitHub account: ${err}`);
  }
}

// File patterns to ignore (snapshots, test fixtures, binaries)
const IGNORE_PATTERNS = [
  /\/__snapshots__\//,
  /\/_snapshots\//,
  /\/snapshots\//,
  /\/TestFiles\//,
  /\.snap$/,
  /\.(png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$/i,
];

// Large file handling: We still cache diffs for large files, just skip full content
const MAX_FILE_SIZE_FOR_FULL_CONTENT = 500 * 1024; // 500KB - skip caching full content
const MAX_DIFF_SIZE = 100 * 1024; // 100KB - warn but don't skip diffs

// Diff generation settings
const DEFAULT_CONTEXT_LINES = 3;

const LARGE_FILE_LINE_THRESHOLD = 2000; // Lines — triggers context distillation

// Check if content appears to be binary
function isBinaryContent(content: string): boolean {
  // Null bytes are a strong indicator of binary
  if (content.includes("\0")) return true;
  // High ratio of non-printable characters (excluding common whitespace)
  const nonPrintable = content.match(/[\x00-\x08\x0B\x0C\x0E-\x1F]/g);
  return nonPrintable ? nonPrintable.length / content.length > 0.1 : false;
}

// Types
interface PullRequest {
  pullRequestId: number;
  title: string;
  description?: string;
  createdBy: { displayName: string };
  sourceRefName: string;
  targetRefName: string;
  lastMergeSourceCommit?: { commitId: string };
  lastMergeTargetCommit?: { commitId: string };
  status: string;
}

interface DiffChange {
  item: {
    path: string;
    gitObjectType?: string;
  };
  changeType: string;
}

interface DiffResponse {
  changes: DiffChange[];
  commonCommit: string;
  targetCommit: string;
  baseCommit: string;
}

interface Iteration {
  id: number;
  createdDate: string;
  sourceRefCommit: { commitId: string };
  targetRefCommit: { commitId: string };
}

interface ManifestFile {
  path: string;
  type: string;
  linesChanged: number;
  cachedFile: string;
  cachedDiff: string;
  baselines: Array<{
    path: string;
    similarityScore: number;
    cachedFile: string;
  }>;
}

interface Manifest {
  version: number;
  pr: {
    id: number;
    title: string;
    author: string;
    sourceBranch: string;
    targetBranch: string;
    sourceCommit: string;
    targetCommit: string;
    iterationId?: number;
    local?: boolean;
  };
  files: ManifestFile[];
  aspects: string[];
  ignoredFiles: string[];
  cacheDir: string;
  preparedAt: string;
  contextFile?: string;
  reviewHistory?: Array<{
    reviewedAt: string;
    iterationId: number;
    sourceCommit: string;
    filesReviewed: number;
    issuesFound: number;
  }>;
  incrementalUpdate?: boolean;
  // v2 fields
  isReReview: boolean;
  previousIterationId: number | null;
  journeyFile: string | null;
  timelineFile: string | null;
  iterationDiffFile: string | null;
  structuralContextFiles: string[];
  weights: string;
}

interface ThreadComment {
  id: number;
  content: string;
  author: { displayName: string };
  publishedDate: string;
  commentType: string;
}

interface PRThread {
  id: number;
  status: string; // active, resolved, wontFix, closed, byDesign
  publishedDate: string;
  lastUpdatedDate: string;
  comments: ThreadComment[];
  threadContext?: {
    filePath: string;
    rightFileStart?: { line: number };
    rightFileEnd?: { line: number };
  };
  properties?: Record<string, { $value: string }>;
  isDeleted: boolean;
}

interface PRStatus {
  id: number;
  state: string;
  description: string;
  creationDate: string;
  targetUrl?: string;
  context: { name: string; genre: string };
}

interface TimelineData {
  iterations: Array<{
    id: number;
    createdDate: string;
    sourceCommit: string;
    targetCommit: string;
  }>;
  threads: Array<{
    id: number;
    status: string;
    publishedDate: string;
    lastUpdatedDate: string;
    authorRole: "reviewer" | "author" | "other";
    filePath?: string;
    lineRange?: { start: number; end: number };
    iterationContext?: number;
    commentCount: number;
    comments: Array<{
      author: string;
      body: string;
      createdAt: string;
    }>;
  }>;
  statuses: Array<{
    state: string;
    description: string;
    createdDate: string;
    context: string;
  }>;
  votes: Array<{
    reviewer: string;
    vote: number;
    timestamp: string;
  }>;
}

interface EnhancedThreadStatus {
  threadId: number;
  status: string;
  authorRole: "reviewer" | "author" | "other";
  filePath?: string;
  lineStart?: number;
  lineEnd?: number;
  iterationId?: number;
  commentCount: number;
  lastUpdated: string;
  comments: Array<{
    author: string;
    body: string;
    createdAt: string;
  }>;
}

interface IterationDiffData {
  previousIterationId: number;
  currentIterationId: number;
  filesAdded: string[];
  filesRemoved: string[];
  filesModified: string[];
}

interface ReReviewInfo {
  isReReview: boolean;
  previousIterationId: number | null;
  journeyFilePath: string | null;
}

// Local mode types
interface LocalChange {
  path: string;
  status: "staged" | "unstaged" | "untracked";
  changeType: "add" | "modify" | "delete" | "rename";
}

// Git helper functions for local mode
function execGit(args: string): string {
  try {
    return execSync(`git ${args}`, { encoding: "utf-8", timeout: 30000 }).trim();
  } catch (error) {
    throw new Error(`Git command failed: git ${args}`);
  }
}

function getGitUserName(): string {
  try {
    return execGit("config user.name");
  } catch {
    return "Local User";
  }
}

function getCurrentBranch(): string {
  return execGit("rev-parse --abbrev-ref HEAD");
}

function getBaseCommitHash(baseBranch: string): string {
  // Get the merge-base (common ancestor) with the base branch
  try {
    return execGit(`merge-base HEAD ${baseBranch}`);
  } catch {
    // If no merge-base, use the base branch's HEAD
    return execGit(`rev-parse ${baseBranch}`);
  }
}

function getLocalChangedFiles(baseBranch: string, includeUntracked: boolean): LocalChange[] {
  const changes: LocalChange[] = [];

  // Get staged changes
  const stagedOutput = execGit("diff --cached --name-status");
  for (const line of stagedOutput.split("\n").filter(Boolean)) {
    const [status, ...pathParts] = line.split("\t");
    const filePath = pathParts.join("\t"); // Handle paths with tabs
    changes.push({
      path: filePath,
      status: "staged",
      changeType: parseGitStatus(status),
    });
  }

  // Get unstaged changes (modified tracked files)
  const unstagedOutput = execGit("diff --name-status");
  for (const line of unstagedOutput.split("\n").filter(Boolean)) {
    const [status, ...pathParts] = line.split("\t");
    const filePath = pathParts.join("\t");
    // Don't add if already in staged
    if (!changes.find((c) => c.path === filePath)) {
      changes.push({
        path: filePath,
        status: "unstaged",
        changeType: parseGitStatus(status),
      });
    }
  }

  // Get changes compared to base branch (committed but not merged)
  const baseDiffOutput = execGit(`diff --name-status ${baseBranch}...HEAD`);
  for (const line of baseDiffOutput.split("\n").filter(Boolean)) {
    const [status, ...pathParts] = line.split("\t");
    const filePath = pathParts.join("\t");
    // Don't add if already tracked as local change
    if (!changes.find((c) => c.path === filePath)) {
      changes.push({
        path: filePath,
        status: "staged", // Committed changes treated as staged
        changeType: parseGitStatus(status),
      });
    }
  }

  // Get untracked files
  if (includeUntracked) {
    const untrackedOutput = execGit("ls-files --others --exclude-standard");
    for (const filePath of untrackedOutput.split("\n").filter(Boolean)) {
      if (!changes.find((c) => c.path === filePath)) {
        changes.push({
          path: filePath,
          status: "untracked",
          changeType: "add",
        });
      }
    }
  }

  return changes;
}

function parseGitStatus(status: string): LocalChange["changeType"] {
  switch (status.charAt(0)) {
    case "A":
      return "add";
    case "D":
      return "delete";
    case "R":
      return "rename";
    default:
      return "modify";
  }
}

function readLocalFile(filePath: string): string | null {
  try {
    return fs.readFileSync(filePath, "utf-8");
  } catch {
    return null;
  }
}

function getFileFromBaseCommit(filePath: string, baseCommit: string): string | null {
  try {
    return execSync(`git show ${baseCommit}:${filePath}`, { encoding: "utf-8", timeout: 30000 });
  } catch {
    return null; // File doesn't exist in base commit (new file)
  }
}

function generateLocalDiff(
  filePath: string,
  baseBranch: string,
  contextLines: number = DEFAULT_CONTEXT_LINES
): string {
  const baseCommit = getBaseCommitHash(baseBranch);
  const baseContent = getFileFromBaseCommit(filePath, baseCommit);
  const currentContent = readLocalFile(filePath);

  if (!currentContent && !baseContent) return "";

  // New file
  if (!baseContent && currentContent) {
    return createTwoFilesPatch(
      "/dev/null",
      `b/${filePath}`,
      "",
      currentContent,
      "",
      "",
      { context: contextLines }
    );
  }

  // Deleted file
  if (baseContent && !currentContent) {
    return createTwoFilesPatch(
      `a/${filePath}`,
      "/dev/null",
      baseContent,
      "",
      "",
      "",
      { context: contextLines }
    );
  }

  // Check for binary content
  if (isBinaryContent(currentContent!) || isBinaryContent(baseContent!)) {
    return `Binary files a/${filePath} and b/${filePath} differ`;
  }

  // No changes
  if (baseContent === currentContent) return "";

  // Generate unified diff
  return createTwoFilesPatch(
    `a/${filePath}`,
    `b/${filePath}`,
    baseContent!,
    currentContent!,
    "",
    "",
    { context: contextLines }
  );
}

// Get GitHub token from env or gh CLI
function getGitHubToken(): string {
  if (process.env.GITHUB_TOKEN) return process.env.GITHUB_TOKEN;
  try {
    return execSync("gh auth token", { encoding: "utf-8", timeout: 10000 }).trim();
  } catch {
    console.error("Failed to get GitHub token. Ensure you're logged in with 'gh auth login' or set GITHUB_TOKEN.");
    process.exit(1);
  }
}

// Make authenticated GitHub API request
async function ghFetch<T>(endpoint: string, token: string, owner?: string, repo?: string): Promise<T> {
  const o = owner || GITHUB_OWNER;
  const r = repo || GITHUB_REPO;
  const url = `https://api.github.com/repos/${o}/${r}${endpoint}`;
  const response = await fetch(url, {
    headers: {
      Authorization: `token ${token}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
    },
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`GitHub API error ${response.status}: ${text}`);
  }
  return response.json();
}

// Paginated GitHub API request (follows Link header)
async function ghFetchPaginated<T>(endpoint: string, token: string, owner?: string, repo?: string): Promise<T[]> {
  const o = owner || GITHUB_OWNER;
  const r = repo || GITHUB_REPO;
  const results: T[] = [];
  let url: string | null = `https://api.github.com/repos/${o}/${r}${endpoint}`;

  while (url) {
    const currentUrl: string = url;
    const response: Response = await fetch(currentUrl, {
      headers: {
        Authorization: `token ${token}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
      },
    });
    if (!response.ok) {
      const text = await response.text();
      throw new Error(`GitHub API error ${response.status}: ${text}`);
    }
    const data = await response.json();
    results.push(...(Array.isArray(data) ? data : []));

    // Parse Link header for next page
    const linkHeader: string | null = response.headers.get("link");
    url = null;
    if (linkHeader) {
      const nextMatch: RegExpMatchArray | null = linkHeader.match(/<([^>]+)>;\s*rel="next"/);
      if (nextMatch) url = nextMatch[1];
    }
  }
  return results;
}

// Get PR metadata
async function getPullRequest(prNumber: number, token: string): Promise<PullRequest> {
  const ghPr = await ghFetch<any>(`/pulls/${prNumber}`, token);
  return {
    pullRequestId: ghPr.number,
    title: ghPr.title,
    description: ghPr.body || "",
    createdBy: { displayName: ghPr.user.login },
    sourceRefName: `refs/heads/${ghPr.head.ref}`,
    targetRefName: `refs/heads/${ghPr.base.ref}`,
    lastMergeSourceCommit: { commitId: ghPr.head.sha },
    lastMergeTargetCommit: { commitId: ghPr.base.sha },
    status: ghPr.state,
  };
}

// Get changed files from GitHub PR files endpoint (paginated)
async function getChangedFiles(prNumber: number, token: string): Promise<DiffResponse> {
  const files = await ghFetchPaginated<any>(`/pulls/${prNumber}/files?per_page=100`, token);
  const changes: DiffChange[] = files.map((f: any) => ({
    item: { path: `/${f.filename}` },
    changeType: mapGitHubStatus(f.status),
  }));
  return {
    changes,
    commonCommit: "",
    targetCommit: "",
    baseCommit: "",
  };
}

function mapGitHubStatus(status: string): string {
  switch (status) {
    case "added": return "add";
    case "removed": return "delete";
    case "renamed": return "rename";
    default: return "edit";
  }
}

// Get file content from specific commit via raw.githubusercontent.com
async function getFileContent(
  filePath: string,
  commitId: string,
  token: string
): Promise<string | null> {
  try {
    const { owner, repo } = detectGitHubRepo();
    const cleanPath = filePath.startsWith("/") ? filePath.slice(1) : filePath;
    const url = `https://raw.githubusercontent.com/${owner}/${repo}/${commitId}/${cleanPath}`;
    const response = await fetch(url, {
      headers: { Authorization: `token ${token}` },
    });
    if (!response.ok) {
      if (response.status === 404) return null;
      throw new Error(`Failed to fetch ${filePath}: ${response.status}`);
    }
    return response.text();
  } catch (err) {
    console.error(`  Warning: Failed to fetch ${filePath}@${commitId.slice(0, 8)}: ${err}`);
    return null;
  }
}

// Count changed lines from a unified diff (only +/- lines, excluding headers)
function countDiffLines(diffContent: string): number {
  if (!diffContent) return 0;
  return diffContent.split('\n')
    .filter(line => (line.startsWith('+') || line.startsWith('-'))
      && !line.startsWith('+++') && !line.startsWith('---'))
    .length;
}

// Get iterations for incremental review support (synthetic: one per commit)
async function getIterations(prNumber: number, token: string): Promise<Iteration[]> {
  const commits = await ghFetchPaginated<any>(`/pulls/${prNumber}/commits?per_page=100`, token);
  return commits.map((c: any, idx: number) => ({
    id: idx + 1,
    createdDate: c.commit.committer.date || c.commit.author.date,
    sourceRefCommit: { commitId: c.sha },
    targetRefCommit: { commitId: c.parents?.[0]?.sha || "" },
  }));
}

async function fetchTimeline(prNumber: number, token: string, cacheDir: string, prAuthor: string): Promise<TimelineData> {
  console.error("Fetching PR timeline data...");

  // Fetch PR commits (synthetic iterations)
  const iterations = await getIterations(prNumber, token);

  // Fetch review comments (inline)
  const reviewComments = await ghFetchPaginated<any>(`/pulls/${prNumber}/comments?per_page=100`, token);

  // Fetch issue comments (general PR comments)
  const issueComments = await ghFetchPaginated<any>(`/issues/${prNumber}/comments?per_page=100`, token);

  // Fetch reviews (for votes)
  const reviews = await ghFetchPaginated<any>(`/pulls/${prNumber}/reviews?per_page=100`, token);

  // Fetch check runs for latest commit
  const latestCommit = iterations[iterations.length - 1]?.sourceRefCommit.commitId;
  let checkRuns: any[] = [];
  if (latestCommit) {
    try {
      const checksResult = await ghFetch<any>(`/commits/${latestCommit}/check-runs?per_page=100`, token);
      checkRuns = checksResult.check_runs || [];
    } catch {}
  }

  // Build threads from review comments (group by in_reply_to_id)
  const threadMap = new Map<number, any[]>();
  for (const comment of reviewComments) {
    const threadId = comment.in_reply_to_id || comment.id;
    if (!threadMap.has(threadId)) threadMap.set(threadId, []);
    threadMap.get(threadId)!.push(comment);
  }

  // Add issue comments as individual threads
  for (const comment of issueComments) {
    threadMap.set(comment.id + 1000000, [comment]); // offset to avoid ID collision
  }

  const threads = Array.from(threadMap.entries()).map(([threadId, comments]) => {
    const firstComment = comments[0];
    const authorLogin = firstComment.user?.login || "unknown";
    let authorRole: "reviewer" | "author" | "other" = "other";
    if (authorLogin === prAuthor) {
      authorRole = "author";
    } else {
      authorRole = "reviewer";
    }

    const lastComment = comments[comments.length - 1];

    return {
      id: threadId,
      status: "active",
      publishedDate: firstComment.created_at,
      lastUpdatedDate: lastComment.updated_at || lastComment.created_at,
      authorRole,
      filePath: firstComment.path?.replace(/^\//, ""),
      lineRange: firstComment.line ? {
        start: firstComment.original_line || firstComment.line,
        end: firstComment.line,
      } : undefined,
      iterationContext: undefined,
      commentCount: comments.length,
      comments: comments.map((c: any) => ({
        author: c.user?.login || "unknown",
        body: c.body || "",
        createdAt: c.created_at,
      })),
    };
  });

  // Map reviews to votes
  const votes = reviews
    .filter((r: any) => r.state !== "PENDING" && r.state !== "COMMENTED")
    .map((r: any) => ({
      reviewer: r.user.login,
      vote: r.state === "APPROVED" ? 10 : r.state === "CHANGES_REQUESTED" ? -5 : 0,
      timestamp: r.submitted_at || new Date().toISOString(),
    }));

  // Map check runs to statuses
  const statuses = checkRuns.map((cr: any) => ({
    state: cr.conclusion || cr.status,
    description: cr.output?.title || cr.name,
    createdDate: cr.started_at || cr.created_at,
    context: cr.name,
  }));

  const timelineData: TimelineData = {
    iterations: iterations.map(iter => ({
      id: iter.id,
      createdDate: iter.createdDate,
      sourceCommit: iter.sourceRefCommit.commitId,
      targetCommit: iter.targetRefCommit.commitId,
    })),
    threads,
    statuses,
    votes,
  };

  const timelinePath = path.join(cacheDir, "pr-timeline.json");
  fs.writeFileSync(timelinePath, JSON.stringify(timelineData, null, 2));
  console.error(`  Timeline saved: ${timelineData.iterations.length} iterations, ${timelineData.threads.length} threads, ${timelineData.statuses.length} statuses`);

  return timelineData;
}

function getEnhancedThreadStatuses(timelineData: TimelineData): EnhancedThreadStatus[] {
  return timelineData.threads.map(thread => ({
    threadId: thread.id,
    status: thread.status,
    authorRole: thread.authorRole,
    filePath: thread.filePath,
    lineStart: thread.lineRange?.start,
    lineEnd: thread.lineRange?.end,
    iterationId: thread.iterationContext,
    commentCount: thread.commentCount,
    lastUpdated: thread.lastUpdatedDate,
    comments: thread.comments,
  }));
}

async function computeIterationDiff(
  prNumber: number,
  currentIterationId: number,
  previousIterationId: number,
  token: string,
  cacheDir: string,
  iterations: Iteration[]
): Promise<IterationDiffData> {
  console.error(`Computing iteration diff: iteration ${previousIterationId} → ${currentIterationId}...`);

  const previousSha = iterations[previousIterationId - 1]?.sourceRefCommit.commitId;
  const currentSha = iterations[currentIterationId - 1]?.sourceRefCommit.commitId;

  if (!previousSha || !currentSha) {
    console.error("  Warning: Cannot find commits for iteration diff, returning empty diff");
    return { previousIterationId, currentIterationId, filesAdded: [], filesRemoved: [], filesModified: [] };
  }

  const comparison = await ghFetch<any>(`/compare/${previousSha}...${currentSha}`, token);
  const files = comparison.files || [];

  const filesAdded: string[] = [];
  const filesRemoved: string[] = [];
  const filesModified: string[] = [];

  for (const file of files) {
    if (file.status === "added" || file.status === "renamed") {
      filesAdded.push(file.filename);
    } else if (file.status === "removed") {
      filesRemoved.push(file.filename);
    } else {
      filesModified.push(file.filename);
    }
  }

  const diffData: IterationDiffData = {
    previousIterationId,
    currentIterationId,
    filesAdded,
    filesRemoved,
    filesModified,
  };

  const diffPath = path.join(cacheDir, "iteration-diff.json");
  fs.writeFileSync(diffPath, JSON.stringify(diffData, null, 2));
  console.error(`  Iteration diff: ${filesAdded.length} added, ${filesRemoved.length} removed, ${filesModified.length} modified`);

  return diffData;
}

function detectReReview(prId: number, cogDocsItemDir: string): ReReviewInfo {
  const journeyPath = path.join(cogDocsItemDir, `PR-${prId}-journey.md`);

  if (!fs.existsSync(journeyPath)) {
    console.error("  No previous journey file found — initial review");
    return { isReReview: false, previousIterationId: null, journeyFilePath: null };
  }

  console.error(`  Found existing journey file: ${journeyPath}`);

  // Try to extract previousIterationId from journey file metadata
  let previousIterationId: number | null = null;
  try {
    const journeyContent = fs.readFileSync(journeyPath, "utf-8");
    // Look for iteration references in the journey file
    // Pattern: "### Iteration N" — find the highest iteration number
    const iterationMatches = journeyContent.matchAll(/### Iteration (\d+)/g);
    let maxIteration = 0;
    for (const match of iterationMatches) {
      const iterNum = parseInt(match[1], 10);
      if (iterNum > maxIteration) maxIteration = iterNum;
    }
    if (maxIteration > 0) {
      previousIterationId = maxIteration;
      console.error(`  Previous iteration from journey: ${previousIterationId}`);
    }
  } catch (err) {
    console.error(`  Warning: Could not parse journey file for iteration info: ${err}`);
  }

  return {
    isReReview: true,
    previousIterationId,
    journeyFilePath: journeyPath,
  };
}

function extractCSharpStructure(content: string): string[] {
  const lines = content.split("\n");
  const entries: string[] = [];
  let currentClass = "";
  let braceDepth = 0;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();

    braceDepth += (line.match(/\{/g) || []).length - (line.match(/\}/g) || []).length;

    const classMatch = trimmed.match(/^(public|internal|private|protected|static|abstract|sealed|partial|\s)*(class|struct|interface|enum|record)\s+(\w+)/);
    if (classMatch) {
      currentClass = classMatch[3];
      entries.push(`L${i + 1}: ${trimmed.replace(/\s*\{?\s*$/, "")}`);
      continue;
    }

    const methodMatch = trimmed.match(/^(?:(?:public|internal|private|protected|static|virtual|override|abstract|async|new|sealed)\s+)*([\w<>\[\]?,]+)\s+(\w+)\s*\(/);
    if (methodMatch && !trimmed.startsWith("//") && !trimmed.startsWith("*") && !trimmed.startsWith("/*")
      && !trimmed.startsWith("if") && !trimmed.startsWith("while") && !trimmed.startsWith("for")
      && !trimmed.startsWith("switch") && !trimmed.startsWith("catch") && !trimmed.startsWith("lock")
      && !trimmed.startsWith("using") && !trimmed.startsWith("return") && !trimmed.startsWith("throw")
      && !trimmed.startsWith("var ") && !trimmed.startsWith("new ")) {
      let sig = trimmed.replace(/\s*\{?\s*$/, "").replace(/\s+/g, " ");
      if (sig.length > 200) sig = sig.slice(0, 197) + "...";
      entries.push(`L${i + 1}: ${sig}`);
      continue;
    }

    const propMatch = trimmed.match(/^(?:(?:public|internal|private|protected|static|virtual|override|abstract|new)\s+)+([\w<>\[\]?,\s]+)\s+(\w+)\s*\{\s*(get|set)/);
    if (propMatch && !trimmed.startsWith("//")) {
      entries.push(`L${i + 1}: ${trimmed.replace(/\s+/g, " ").slice(0, 120)}`);
    }
  }

  return entries;
}

function extractTypeScriptStructure(content: string): string[] {
  const lines = content.split("\n");
  const entries: string[] = [];

  for (let i = 0; i < lines.length; i++) {
    const trimmed = lines[i].trim();

    if (trimmed.match(/^(export\s+)?(default\s+)?(class|interface|type|enum|function|const\s+\w+\s*=\s*\(|async\s+function)\s/)) {
      let sig = trimmed.replace(/\s*\{?\s*$/, "").replace(/\s+/g, " ");
      if (sig.length > 200) sig = sig.slice(0, 197) + "...";
      entries.push(`L${i + 1}: ${sig}`);
    }
  }

  return entries;
}

function extractStructure(content: string, fileType: string): string[] {
  switch (fileType) {
    case "cs": return extractCSharpStructure(content);
    case "ts": case "tsx": case "js": case "jsx": case "vue": return extractTypeScriptStructure(content);
    default: return [];
  }
}

const TREE_SITTER_CLI = path.join(
  process.env.HOME || process.env.USERPROFILE || "",
  ".claude", "mcp-servers", "tree-sitter", "dist", "cli-structure.js"
);

function tryTreeSitterExtract(filePath: string): string[] | null {
  if (!fs.existsSync(TREE_SITTER_CLI)) return null;
  try {
    const output = execSync(`node "${TREE_SITTER_CLI}" "${filePath}"`, {
      encoding: "utf-8",
      timeout: 15000,
      stdio: ["pipe", "pipe", "pipe"],
    });
    const lines = output.trim().split("\n").filter(l => l.startsWith("L"));
    return lines.length > 0 ? lines : null;
  } catch {
    return null;
  }
}

async function distillLargeFiles(
  files: ManifestFile[],
  cacheDir: string,
  sourceCommit: string,
  token: string
): Promise<string[]> {
  const structuralContextFiles: string[] = [];
  const structuralDir = path.join(cacheDir, "structural-context");

  for (const file of files) {
    const cachedPath = file.cachedFile ? path.join(cacheDir, file.cachedFile) : null;
    let content: string | null = null;
    let lineCount = 0;

    if (cachedPath && fs.existsSync(cachedPath)) {
      content = fs.readFileSync(cachedPath, "utf-8");
      lineCount = countLines(content);
    } else if (!file.cachedFile) {
      lineCount = LARGE_FILE_LINE_THRESHOLD + 1;
    }

    if (lineCount <= LARGE_FILE_LINE_THRESHOLD) continue;

    const fileName = path.basename(file.path);
    const contextFileName = `structural-context/${fileName}.md`;
    const contextPath = path.join(cacheDir, contextFileName);
    fs.mkdirSync(structuralDir, { recursive: true });

    const sections: string[] = [
      `# Structural Context: ${fileName}`,
      ``,
      `**File:** \`${file.path}\``,
      `**Lines:** ~${lineCount}`,
      `**Diff:** \`${file.cachedDiff}\``,
    ];

    if (content) {
      let entries: string[] | null = null;
      let source = "regex";

      if (cachedPath) {
        entries = tryTreeSitterExtract(cachedPath);
        if (entries) source = "tree-sitter";
      }
      if (!entries || entries.length === 0) {
        entries = extractStructure(content, file.type);
        source = "regex";
      }

      if (entries.length > 0) {
        sections.push(
          ``,
          `## Method / Type Index (${entries.length} entries, ${source})`,
          ``,
          `Use these line numbers to target-read specific sections from the cached file.`,
          ``,
          "```",
          ...entries,
          "```",
        );
        console.error(`  ${file.path}: structural context (${entries.length} entries via ${source} from ${lineCount} lines)`);
      } else {
        sections.push(``, `No structural entries extracted — read the diff and cached file directly.`);
        console.error(`  ${file.path}: structural context (no entries extracted, ${lineCount} lines)`);
      }
    } else {
      sections.push(
        ``,
        `Full content not cached (file exceeds ${MAX_FILE_SIZE_FOR_FULL_CONTENT / 1024}KB).`,
        `Review the diff at \`${file.cachedDiff}\` and read surrounding context from the repository if needed.`,
      );
      console.error(`  ${file.path}: structural context (content not cached, ${lineCount} lines)`);
    }

    fs.writeFileSync(contextPath, sections.join("\n"));
    structuralContextFiles.push(contextFileName);
  }

  if (structuralContextFiles.length > 0) {
    console.error(`  Generated ${structuralContextFiles.length} structural context file(s)`);
  }

  return structuralContextFiles;
}

interface WorkItemRef { id: number; type: string; title: string; }

// Parse work item IDs from PR title + description (AB#NNNNN), with a branch-name fallback (p/NNNNN-...).
function parseWorkItems(prData: PullRequest): WorkItemRef[] {
  const workItems: WorkItemRef[] = [];
  const wiText = `${prData.title || ""}\n${prData.description || ""}`;
  const seenWiIds = new Set<number>();
  for (const match of wiText.matchAll(/AB#(\d+)/g)) {
    const id = parseInt(match[1], 10);
    if (seenWiIds.has(id)) continue;
    seenWiIds.add(id);
    workItems.push({ id, type: "Work Item", title: `AB#${match[1]}` });
  }
  if (workItems.length === 0) {
    const branchName = (prData.sourceRefName || "").replace(/^refs\/heads\//, "");
    const branchWiMatch = branchName.match(/^p\/(\d+)-/);
    if (branchWiMatch) {
      const wiId = parseInt(branchWiMatch[1], 10);
      workItems.push({ id: wiId, type: "Work Item", title: `AB#${branchWiMatch[1]}` });
    }
  }
  return workItems;
}

// Derive a kebab slug for a new item dir from the source branch (or PR title fallback).
function deriveItemSlug(prData: PullRequest): string {
  const branch = (prData.sourceRefName || "").replace(/^refs\/heads\//, "");
  let slug = branch.replace(/^p\//, "").replace(/^\d+-/, "");
  if (!slug) {
    slug = (prData.title || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 60);
  }
  return slug || "review";
}

// Resolve the cog-docs item directory for this PR's work item, creating docs/bugs/<id>-<slug>/
// (with a minimal SPEC.md) when none exists. Hard-fails if no cog-docs repo can be located, since
// cog-docs is the sole output destination for this plugin.
function resolveOrCreateCogDocsItemDir(prId: number, prData: PullRequest, workItems: WorkItemRef[]): { cogDocsRoot: string; cogDocsItemDir: string; created: boolean } {
  let cogDocsRoot: string | null = null;
  if (process.env.COG_DOCS_ROOT && fs.existsSync(process.env.COG_DOCS_ROOT)) {
    cogDocsRoot = process.env.COG_DOCS_ROOT;
  } else {
    const siblingCogDocs = path.resolve(process.cwd(), "..", "cog-docs");
    if (fs.existsSync(siblingCogDocs)) {
      cogDocsRoot = siblingCogDocs;
    }
  }
  if (!cogDocsRoot) {
    throw new Error(
      "cog-docs repository not found. cognito-pr-review writes all artifacts to cog-docs, so it is required. " +
      "Check out cog-docs as a sibling directory (../cog-docs) or set COG_DOCS_ROOT."
    );
  }

  const pipelineDirs = ["features", "bugs"].map(p => path.join(cogDocsRoot!, "docs", p));
  let cogDocsItemDir: string | null = null;

  // 1. Materialized lookup (lazy-pipeline items): wi_id -> feature_id slug
  if (workItems.length > 0) {
    const materializedPath = path.join(cogDocsRoot, "docs", "work", "materialized.json");
    if (fs.existsSync(materializedPath)) {
      try {
        const materialized: Array<{ wi_id: number | string; feature_id: string }> = JSON.parse(fs.readFileSync(materializedPath, "utf-8"));
        const record = materialized.find(rec => String(rec.wi_id) === String(workItems[0].id));
        if (record && record.feature_id) {
          for (const base of pipelineDirs) {
            const candidate = path.join(base, record.feature_id);
            if (fs.existsSync(candidate)) { cogDocsItemDir = candidate; break; }
          }
        }
      } catch { /* ignore malformed materialized.json */ }
    }
  }

  // 2. Id-prefix dir scan (manual items): docs/{features,bugs}/<id> or <id>-*
  if (!cogDocsItemDir && workItems.length > 0) {
    const wid = String(workItems[0].id);
    outer: for (const base of pipelineDirs) {
      if (!fs.existsSync(base)) continue;
      for (const name of fs.readdirSync(base).sort()) {
        const candidate = path.join(base, name);
        if (!fs.statSync(candidate).isDirectory()) continue;
        if (name === wid || name.startsWith(`${wid}-`)) { cogDocsItemDir = candidate; break outer; }
      }
    }
  }

  // 3. WIP.md branch match: an item dir whose liveness sentinel records this PR's source branch.
  if (!cogDocsItemDir) {
    const sourceBranch = (prData.sourceRefName || "").replace(/^refs\/heads\//, "");
    if (sourceBranch) {
      const branchMatches: string[] = [];
      for (const base of pipelineDirs) {
        if (!fs.existsSync(base)) continue;
        for (const name of fs.readdirSync(base).sort()) {
          const candidate = path.join(base, name);
          const wipPath = path.join(candidate, "WIP.md");
          if (!fs.existsSync(wipPath)) continue;
          const branchLine = fs.readFileSync(wipPath, "utf-8").match(/^branch:\s*(.+)\s*$/m);
          if (branchLine && branchLine[1].trim() === sourceBranch) branchMatches.push(candidate);
        }
      }
      if (branchMatches.length === 1) cogDocsItemDir = branchMatches[0];
    }
  }

  if (cogDocsItemDir) {
    return { cogDocsRoot, cogDocsItemDir, created: false };
  }

  // 4. Nothing resolved — create a minimal bug item dir so the review has a durable home.
  const slug = deriveItemSlug(prData);
  const wiId = workItems.length > 0 ? workItems[0].id : null;
  const dirName = wiId !== null ? `${wiId}-${slug}` : slug;
  const newDir = path.join(cogDocsRoot, "docs", "bugs", dirName);
  fs.mkdirSync(newDir, { recursive: true });

  const specPath = path.join(newDir, "SPEC.md");
  if (!fs.existsSync(specPath)) {
    const sourceBranch = (prData.sourceRefName || "").replace(/^refs\/heads\//, "");
    const lines = [`# ${prData.title || dirName}`, "", `**Branch:** ${sourceBranch}`, ""];
    if (wiId !== null) lines.push(`**Work item:** AB#${wiId}`);
    lines.push(`**PR:** #${prId}`, "");
    lines.push("_Auto-created by cognito-pr-review as the output home for this PR's review. Replace with the real spec when one is written._", "");
    fs.writeFileSync(specPath, lines.join("\n"));
  }
  console.error(`  Created cog-docs item dir: ${newDir}`);
  return { cogDocsRoot, cogDocsItemDir: newDir, created: true };
}

// Fetch PR context (description, comments, work items) — built inline from GitHub data
function fetchPrContext(prNumber: number, cacheDir: string, token: string, prData: PullRequest, cogDocsItemDir: string, workItems: WorkItemRef[], timelineData?: TimelineData): void {
  console.error("Fetching PR context (description, comments, work items)...");
  const outputFile = path.join(cacheDir, "pr-context.json");

  try {
    // PR description comes from the PR data we already fetched
    const prDescription = {
      title: prData.title,
      description: prData.description || "",
      author: prData.createdBy.displayName,
    };

    // Work items and the cog-docs destination were resolved by the caller and passed in.

    // Build the context object matching the expected format
    const context: any = {
      prId: prNumber,
      prDescription,
      workItems,
      comments: [],
      generatedAt: new Date().toISOString(),
      cogDocsItemDir,
    };

    // Enrich with thread statuses if available
    if (timelineData) {
      context.threadStatuses = getEnhancedThreadStatuses(timelineData);
    }

    fs.writeFileSync(outputFile, JSON.stringify(context, null, 2));
    console.error(`  PR context saved to ${outputFile}`);
  } catch (error) {
    console.error(`  Warning: Failed to build PR context: ${error}`);
    // Non-fatal - review can proceed without context
  }
}

// Determine file type from path
function getFileType(filePath: string): string {
  const ext = path.extname(filePath).toLowerCase();
  const typeMap: Record<string, string> = {
    ".cs": "cs",
    ".vue": "vue",
    ".ts": "ts",
    ".tsx": "tsx",
    ".js": "js",
    ".jsx": "jsx",
    ".json": "json",
    ".md": "md",
    ".css": "css",
    ".scss": "scss",
    ".html": "html",
  };
  return typeMap[ext] || "other";
}

// Check if file should be ignored
function shouldIgnoreFile(filePath: string): boolean {
  return IGNORE_PATTERNS.some((pattern) => pattern.test(filePath));
}

// Count lines in a string
function countLines(content: string): number {
  return content.split("\n").length;
}

// Determine aspects from file types
function determineAspects(files: ManifestFile[]): string[] {
  const aspects = new Set<string>();

  for (const file of files) {
    if (file.type === "cs") {
      aspects.add("csharp");
      if (file.path.includes("Controllers/") || file.path.includes("Controller.cs")) {
        aspects.add("api");
      }
    }
    if (["vue", "ts", "tsx", "js", "jsx"].includes(file.type)) {
      aspects.add("frontend");
    }
  }

  // Always include consistency if there are substantive files
  if (files.length > 0) {
    aspects.add("consistency");
  }

  return Array.from(aspects);
}

// Score token overlap between two filenames (0–1)
function filenameTokenOverlap(nameA: string, nameB: string): number {
  const tokenize = (n: string): Set<string> => {
    const parts = n.replace(/\.[^.]+$/, "").split(/(?=[A-Z])|[-_.]/).filter(Boolean);
    return new Set(parts.map(p => p.toLowerCase()));
  };
  const tokA = tokenize(nameA);
  const tokB = tokenize(nameB);
  if (tokA.size === 0 || tokB.size === 0) return 0;
  let shared = 0;
  for (const t of tokA) { if (tokB.has(t)) shared++; }
  return shared / Math.max(tokA.size, tokB.size);
}

// Cheap content similarity: ratio of shared structural declaration lines
function contentLineSimilarity(contentA: string, contentB: string): number {
  const extractSignalLines = (content: string): Set<string> => {
    const set = new Set<string>();
    for (const raw of content.split("\n")) {
      const line = raw.trim();
      if (line.length < 8) continue;
      if (
        line.startsWith("import ") ||
        line.startsWith("using ") ||
        line.startsWith("export ") ||
        line.startsWith("namespace ") ||
        /^(public|internal|private|protected)\s+(class|interface|enum|record|struct|abstract)\s/.test(line) ||
        /^(export\s+)?(default\s+)?(class|interface|type|enum|function)\s/.test(line)
      ) {
        set.add(line.slice(0, 120));
      }
    }
    return set;
  };
  const sigA = extractSignalLines(contentA);
  const sigB = extractSignalLines(contentB);
  const total = Math.max(sigA.size, sigB.size);
  if (total === 0) return 0;
  let shared = 0;
  for (const l of sigA) { if (sigB.has(l)) shared++; }
  return shared / total;
}

// Find baseline files for consistency checking
export async function findBaselines(
  file: ManifestFile,
  token: string,
  cacheDir: string
): Promise<ManifestFile["baselines"]> {
  // Skip small files — not enough surface area for meaningful comparison
  if (file.linesChanged < 20) return [];

  const fileName = path.basename(file.path);
  const fileExt = path.extname(file.path).toLowerCase();
  const fileDirNorm = path.dirname(file.path).replace(/\\/g, "/");

  // List all files on main branch (local checkout)
  let allFiles: string[];
  try {
    const output = execSync("git ls-tree -r --name-only main", {
      encoding: "utf-8",
      timeout: 15000,
    }).trim();
    allFiles = output.split("\n").filter(Boolean);
  } catch {
    // Fall back to HEAD if main branch isn't available (e.g. fixture/detached HEAD)
    try {
      const output = execSync("git ls-tree -r --name-only HEAD", {
        encoding: "utf-8",
        timeout: 15000,
      }).trim();
      allFiles = output.split("\n").filter(Boolean);
    } catch {
      return [];
    }
  }

  // Read the changed file's cached content for similarity scoring
  let fileContent: string | null = null;
  if (file.cachedFile) {
    try {
      fileContent = fs.readFileSync(path.join(cacheDir, file.cachedFile), "utf-8");
    } catch { /* non-fatal */ }
  }

  interface Candidate {
    repoPath: string;
    score: number;
  }
  const candidates: Candidate[] = [];

  for (const candidate of allFiles) {
    if (candidate === file.path) continue;

    const candExt = path.extname(candidate).toLowerCase();
    if (candExt !== fileExt) continue;

    const candName = path.basename(candidate);
    const candDirNorm = path.dirname(candidate).replace(/\\/g, "/");

    // --- Path/name proximity score (0–80 points) ---
    let score = 0;

    if (candDirNorm === fileDirNorm) {
      score += 30;
    } else {
      const fileParent = fileDirNorm.split("/").slice(0, -1).join("/");
      const candParent = candDirNorm.split("/").slice(0, -1).join("/");
      if (fileParent && fileParent === candParent) {
        score += 15;
      } else {
        const fileParts = fileDirNorm.split("/");
        const candParts = candDirNorm.split("/");
        let sharedDepth = 0;
        for (let i = 0; i < Math.min(fileParts.length, candParts.length); i++) {
          if (fileParts[i] === candParts[i]) sharedDepth++;
          else break;
        }
        score += Math.round((sharedDepth / Math.max(fileParts.length, candParts.length)) * 10);
      }
    }

    // Filename token overlap (0–20 points)
    score += Math.round(filenameTokenOverlap(fileName, candName) * 20);

    // Common role suffix bonus (Service, Controller, Repository, etc.)
    const roleSuffixRe = /(Service|Controller|Repository|Store|Handler|Manager|Validator|Provider|Factory|Component|Composable|Helper|Middleware|Extension)(\.[^.]+)?$/i;
    const fileRole = fileName.match(roleSuffixRe)?.[1]?.toLowerCase();
    const candRole = candName.match(roleSuffixRe)?.[1]?.toLowerCase();
    if (fileRole && candRole && fileRole === candRole) {
      score += 30;
    }

    // Early-out: skip content scoring for clearly unrelated files
    if (score < 10) continue;

    // --- Content similarity (0–20 points) ---
    if (fileContent) {
      try {
        const candContent = execSync(`git show main:"${candidate}"`, {
          encoding: "utf-8",
          timeout: 10000,
          maxBuffer: 2 * 1024 * 1024,
        });
        score += Math.round(contentLineSimilarity(fileContent, candContent) * 20);
      } catch { /* non-fatal: content scoring is best-effort */ }
    }

    score = Math.min(score, 100);
    candidates.push({ repoPath: candidate, score });
  }

  // Sort by score descending, take top 3
  candidates.sort((a, b) => b.score - a.score);
  const top = candidates.slice(0, 3);

  const baselinesDir = path.join(cacheDir, "baselines");
  fs.mkdirSync(baselinesDir, { recursive: true });

  const result: ManifestFile["baselines"] = [];

  for (const { repoPath, score } of top) {
    if (score < 20) break;

    const safeFileName = repoPath.replace(/[/\\]/g, "_");
    const cachedFile = `baselines/${safeFileName}`;
    const cachedFilePath = path.join(cacheDir, cachedFile);

    try {
      const content = execSync(`git show main:"${repoPath}"`, {
        encoding: "utf-8",
        timeout: 10000,
        maxBuffer: 2 * 1024 * 1024,
      });
      fs.writeFileSync(cachedFilePath, content);
    } catch {
      continue;
    }

    result.push({ path: repoPath, similarityScore: score, cachedFile });
  }

  return result;
}

// Generate proper unified diff between two versions
async function generateDiff(
  filePath: string,
  sourceCommit: string,
  targetCommit: string,
  token: string,
  contextLines: number = DEFAULT_CONTEXT_LINES
): Promise<string> {
  const sourceContent = await getFileContent(filePath, sourceCommit, token);
  const targetContent = await getFileContent(filePath, targetCommit, token);

  if (!sourceContent && !targetContent) return "";

  // New file (exists in source/PR but not in target/base)
  if (!targetContent) {
    return createTwoFilesPatch(
      "/dev/null",
      `b/${filePath}`,
      "",
      sourceContent!,
      "",
      "",
      { context: contextLines }
    );
  }

  // Deleted file (exists in target/base but not in source/PR)
  if (!sourceContent) {
    return createTwoFilesPatch(
      `a/${filePath}`,
      "/dev/null",
      targetContent,
      "",
      "",
      "",
      { context: contextLines }
    );
  }

  // Check for binary content
  if (isBinaryContent(sourceContent) || isBinaryContent(targetContent)) {
    return `Binary files a/${filePath} and b/${filePath} differ`;
  }

  // No changes
  if (sourceContent === targetContent) return "";

  // Generate proper unified diff
  // Note: diff uses (oldStr, newStr) order
  // targetContent = target branch (main) = old version (what we're comparing against)
  // sourceContent = source branch (PR) = new version (the changes)
  return createTwoFilesPatch(
    `a/${filePath}`,
    `b/${filePath}`,
    targetContent,
    sourceContent,
    "",
    "",
    { context: contextLines }
  );
}

// Main prep function
async function prepPR(prId: number, force = false, contextLines = DEFAULT_CONTEXT_LINES): Promise<Manifest> {
  console.error(`Preparing PR #${prId}...`);

  // Ensure correct GitHub account is active for this repo
  ensureCorrectGitHubAccount();

  // Get auth token
  const token = getGitHubToken();
  console.error("Got GitHub token");

  // Fetch PR metadata
  const pr = await getPullRequest(prId, token);
  console.error(`PR: ${pr.title}`);

  if (!pr.lastMergeSourceCommit?.commitId || !pr.lastMergeTargetCommit?.commitId) {
    throw new Error("PR is missing merge commit information. Is it still being processed?");
  }

  const sourceCommit = pr.lastMergeSourceCommit.commitId;
  const targetCommit = pr.lastMergeTargetCommit.commitId;
  const sourceBranch = pr.sourceRefName.replace("refs/heads/", "");
  const targetBranch = pr.targetRefName.replace("refs/heads/", "");

  console.error(`Source: ${sourceBranch} (${sourceCommit.slice(0, 8)})`);
  console.error(`Target: ${targetBranch} (${targetCommit.slice(0, 8)})`);

  // Get iterations for incremental support
  const iterations = await getIterations(prId, token);
  const latestIteration = iterations[iterations.length - 1];
  const iterationId = latestIteration?.id;
  console.error(`Latest iteration: ${iterationId}`);

  // Resolve (or create) the cog-docs item dir — the sole output home for this review.
  const workItems = parseWorkItems(pr);
  const { cogDocsItemDir, created: cogDocsCreated } = resolveOrCreateCogDocsItemDir(prId, pr, workItems);
  console.error(`Cog-docs item dir: ${cogDocsItemDir}${cogDocsCreated ? " (created)" : ""}`);

  // Check for existing manifest. All artifacts (cache, review, journey) live under the item dir.
  const cacheDir = path.join(cogDocsItemDir, ".pr-review", "pr-cache", String(prId));
  const manifestPath = path.join(cacheDir, "manifest.json");
  let existingManifest: Manifest | null = null;

  if (!force && fs.existsSync(manifestPath)) {
    try {
      existingManifest = JSON.parse(stripBom(fs.readFileSync(manifestPath, "utf-8")));
      if (
        existingManifest &&
        existingManifest.pr.iterationId === iterationId &&
        existingManifest.pr.sourceCommit === sourceCommit
      ) {
        console.error("Cache is current (same iteration and commit)");
        console.log(JSON.stringify(existingManifest, null, 2));
        return existingManifest;
      }
    } catch {
      // Invalid manifest, will rebuild
    }
  }

  // Get changed files from GitHub PR files endpoint
  const diff = await getChangedFiles(prId, token);
  // Use the target (base) commit as the merge base for diff generation
  const mergeBase = targetCommit;
  console.error(`GitHub reported ${diff.changes.length} changes`);

  // Filter and process files
  const files: ManifestFile[] = [];
  const ignoredFiles: string[] = [];

  for (const change of diff.changes) {
    const filePath = change.item.path.replace(/^\//, ""); // Remove leading slash

    // Skip directories and ignored patterns
    if (change.item.gitObjectType === "tree") continue;
    if (shouldIgnoreFile(filePath)) {
      ignoredFiles.push(filePath);
      continue;
    }

    // Skip deleted files (no content to review)
    if (change.changeType === "delete") {
      ignoredFiles.push(`${filePath} (deleted)`);
      continue;
    }

    const fileType = getFileType(filePath);

    files.push({
      path: filePath,
      type: fileType,
      linesChanged: 0, // Will be filled in
      cachedFile: `files/${filePath}`,
      cachedDiff: `diffs/${filePath}.diff`,
      baselines: [],
    });
  }

  console.error(`Processing ${files.length} files (${ignoredFiles.length} ignored)`);

  // Create cache directories
  fs.mkdirSync(path.join(cacheDir, "files"), { recursive: true });
  fs.mkdirSync(path.join(cacheDir, "diffs"), { recursive: true });
  fs.mkdirSync(path.join(cacheDir, "baselines"), { recursive: true });

  // Fetch timeline data
  const timelineData = await fetchTimeline(prId, token, cacheDir, pr.createdBy.displayName);

  // Fetch PR context with thread status enrichment
  fetchPrContext(prId, cacheDir, token, pr, cogDocsItemDir, workItems, timelineData);

  // Detect re-review
  const reReviewInfo = detectReReview(prId, cogDocsItemDir);

  // Compute iteration diff if re-review and we have iteration info
  let iterationDiffData: IterationDiffData | null = null;
  if (reReviewInfo.isReReview && reReviewInfo.previousIterationId && iterationId) {
    iterationDiffData = await computeIterationDiff(
      prId, iterationId, reReviewInfo.previousIterationId, token, cacheDir, iterations
    );
  }

  // Fetch and cache file contents
  for (const file of files) {
    const content = await getFileContent(file.path, sourceCommit, token);
    if (content === null) {
      ignoredFiles.push(`${file.path} (not found)`);
      continue;
    }

    // Generate and write diff FIRST (always needed for review)
    // Use mergeBase (common ancestor) instead of targetCommit to get three-dot semantics:
    // only changes the PR added on top of the branch point
    const diffContent = await generateDiff(file.path, sourceCommit, mergeBase, token, contextLines);
    file.linesChanged = countDiffLines(diffContent) || countLines(content);
    const cachedDiffPath = path.join(cacheDir, file.cachedDiff);
    fs.mkdirSync(path.dirname(cachedDiffPath), { recursive: true });
    fs.writeFileSync(cachedDiffPath, diffContent);

    // For large files, cache diff but skip full content (diff is what matters for review)
    if (content.length > MAX_FILE_SIZE_FOR_FULL_CONTENT) {
      console.error(`  ${file.path} (${file.linesChanged} lines) [large file - diff only]`);
      // Don't cache full content, but DO keep the file in the manifest
      file.cachedFile = ""; // Signal that full content not cached
      continue;
    }

    // Write cached file (for smaller files)
    const cachedFilePath = path.join(cacheDir, file.cachedFile);
    fs.mkdirSync(path.dirname(cachedFilePath), { recursive: true });
    fs.writeFileSync(cachedFilePath, content);

    // Find baseline files for consistency checking
    file.baselines = await findBaselines(file, token, cacheDir);

    console.error(`  ${file.path} (${file.linesChanged} lines)${file.baselines.length > 0 ? ` [${file.baselines.length} baseline(s)]` : ""}`);
  }

  // Filter out any files that weren't successfully processed (content not found)
  // Note: Large files with empty cachedFile are still valid (diff-only mode)
  const validFiles = files.filter((f) => f.linesChanged > 0);

  // Build manifest
  const contextFilePath = path.join(cacheDir, "pr-context.json");
  const hasContextFile = fs.existsSync(contextFilePath);

  // Distill large files
  const structuralContextFiles = await distillLargeFiles(validFiles, cacheDir, sourceCommit, token);

  const manifest: Manifest = {
    version: 2,
    pr: {
      id: prId,
      title: pr.title,
      author: pr.createdBy.displayName,
      sourceBranch,
      targetBranch,
      sourceCommit,
      targetCommit,
      iterationId,
    },
    files: validFiles,
    aspects: determineAspects(validFiles),
    ignoredFiles,
    cacheDir,
    preparedAt: new Date().toISOString(),
    contextFile: hasContextFile ? "pr-context.json" : undefined,
    reviewHistory: existingManifest?.reviewHistory,
    incrementalUpdate: existingManifest !== null,
    // v2 fields
    isReReview: reReviewInfo.isReReview,
    previousIterationId: reReviewInfo.previousIterationId,
    journeyFile: reReviewInfo.journeyFilePath,
    timelineFile: "pr-timeline.json",
    iterationDiffFile: iterationDiffData ? "iteration-diff.json" : null,
    structuralContextFiles,
    weights: "weights.yaml",
  };

  // Write manifest
  fs.writeFileSync(manifestPath, JSON.stringify(manifest, null, 2));

  // Verification
  console.error(`\nVerification:`);
  console.error(`  GitHub reported: ${diff.changes.length} changes`);
  console.error(`  Processed: ${validFiles.length} files`);
  console.error(`  Ignored: ${ignoredFiles.length} files`);

  // Print manifest to stdout
  console.log(JSON.stringify(manifest, null, 2));

  return manifest;
}

// Local mode prep function
async function prepLocal(
  baseBranch: string,
  includeUntracked: boolean,
  contextLines: number = DEFAULT_CONTEXT_LINES
): Promise<Manifest> {
  console.error(`Preparing local changes (vs ${baseBranch})...`);

  const currentBranch = getCurrentBranch();
  const gitUserName = getGitUserName();
  const baseCommit = getBaseCommitHash(baseBranch);

  console.error(`Current branch: ${currentBranch}`);
  console.error(`Base: ${baseBranch} (${baseCommit.slice(0, 8)})`);
  console.error(`Include untracked: ${includeUntracked}`);

  // Get changed files from git
  const changes = getLocalChangedFiles(baseBranch, includeUntracked);
  console.error(`Found ${changes.length} changed files`);

  // Filter and process files
  const files: ManifestFile[] = [];
  const ignoredFiles: string[] = [];

  for (const change of changes) {
    const filePath = change.path;

    // Skip ignored patterns
    if (shouldIgnoreFile(filePath)) {
      ignoredFiles.push(`${filePath} (ignored pattern)`);
      continue;
    }

    // Skip deleted files (no content to review)
    if (change.changeType === "delete") {
      ignoredFiles.push(`${filePath} (deleted)`);
      continue;
    }

    const fileType = getFileType(filePath);

    files.push({
      path: filePath,
      type: fileType,
      linesChanged: 0, // Will be filled in
      cachedFile: `files/${filePath}`,
      cachedDiff: `diffs/${filePath}.diff`,
      baselines: [],
    });
  }

  console.error(`Processing ${files.length} files (${ignoredFiles.length} ignored)`);

  // Create cache directories
  const cacheDir = ".claude/pr-cache/local";
  fs.mkdirSync(path.join(cacheDir, "files"), { recursive: true });
  fs.mkdirSync(path.join(cacheDir, "diffs"), { recursive: true });

  // Process each file
  for (const file of files) {
    const content = readLocalFile(file.path);
    if (content === null) {
      ignoredFiles.push(`${file.path} (not found)`);
      continue;
    }

    file.linesChanged = countLines(content);

    // Generate and write diff
    const diffContent = generateLocalDiff(file.path, baseBranch, contextLines);
    const cachedDiffPath = path.join(cacheDir, file.cachedDiff);
    fs.mkdirSync(path.dirname(cachedDiffPath), { recursive: true });
    fs.writeFileSync(cachedDiffPath, diffContent);

    // Skip full content for large files
    if (content.length > MAX_FILE_SIZE_FOR_FULL_CONTENT) {
      console.error(`  ${file.path} (${file.linesChanged} lines) [large file - diff only]`);
      file.cachedFile = "";
      continue;
    }

    // Write cached file
    const cachedFilePath = path.join(cacheDir, file.cachedFile);
    fs.mkdirSync(path.dirname(cachedFilePath), { recursive: true });
    fs.writeFileSync(cachedFilePath, content);

    // Note status in output
    const statusTag = changes.find((c) => c.path === file.path)?.status || "unknown";
    console.error(`  ${file.path} (${file.linesChanged} lines) [${statusTag}]`);
  }

  // Filter out files that weren't successfully processed
  const validFiles = files.filter((f) => f.linesChanged > 0);

  // Build manifest
  const manifest: Manifest = {
    version: 2,
    pr: {
      id: 0, // Sentinel for local mode
      title: `Local changes on ${currentBranch}`,
      author: gitUserName,
      sourceBranch: currentBranch,
      targetBranch: baseBranch,
      sourceCommit: "working-tree",
      targetCommit: baseCommit,
      local: true,
    },
    files: validFiles,
    aspects: determineAspects(validFiles),
    ignoredFiles,
    cacheDir,
    preparedAt: new Date().toISOString(),
    isReReview: false,
    previousIterationId: null,
    journeyFile: null,
    timelineFile: null,
    iterationDiffFile: null,
    structuralContextFiles: [],
    weights: "weights.yaml",
  };

  // Write manifest
  const manifestPath = path.join(cacheDir, "manifest.json");
  fs.writeFileSync(manifestPath, JSON.stringify(manifest, null, 2));

  // Verification
  console.error(`\nVerification:`);
  console.error(`  Git reported: ${changes.length} changes`);
  console.error(`  Processed: ${validFiles.length} files`);
  console.error(`  Ignored: ${ignoredFiles.length} files`);

  // Print manifest to stdout
  console.log(JSON.stringify(manifest, null, 2));

  return manifest;
}

// Parse CLI arguments
interface CliArgs {
  prId: number;
  force: boolean;
  cacheRoot: string;
  contextLines: number;
  // Local mode options
  local: boolean;
  baseBranch: string;
  includeUntracked: boolean;
}

function parseArgs(argv: string[]): CliArgs {
  const args = argv.slice(2);
  let prId = NaN;
  let force = false;
  let cacheRoot = process.cwd(); // Default to current working directory
  let contextLines = DEFAULT_CONTEXT_LINES;
  let local = false;
  let baseBranch = "main";
  let includeUntracked = false;

  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    if (arg === "--force") {
      force = true;
    } else if (arg === "--local") {
      local = true;
    } else if (arg === "--base" && args[i + 1]) {
      baseBranch = args[++i];
    } else if (arg === "--include-untracked") {
      includeUntracked = true;
    } else if (arg === "--cache-root" && args[i + 1]) {
      cacheRoot = args[++i];
    } else if (arg === "--context" && args[i + 1]) {
      contextLines = parseInt(args[++i], 10);
    } else if (!isNaN(parseInt(arg, 10))) {
      prId = parseInt(arg, 10);
    }
  }

  return { prId, force, cacheRoot, contextLines, local, baseBranch, includeUntracked };
}

// CLI entry point
const { prId, force, cacheRoot, contextLines, local, baseBranch, includeUntracked } = parseArgs(process.argv);

// Change to cache root before running
process.chdir(cacheRoot);

if (local) {
  // Local mode - review uncommitted/unpushed changes
  prepLocal(baseBranch, includeUntracked, contextLines).catch((error) => {
    console.error(`Error: ${error.message}`);
    process.exit(1);
  });
} else if (!isNaN(prId)) {
  // PR mode - review a specific PR via GitHub API
  prepPR(prId, force, contextLines).catch((error) => {
    console.error(`Error: ${error.message}`);
    process.exit(1);
  });
} else {
  // No valid mode specified
  console.error("Usage:");
  console.error("  PR Mode:    npx tsx prep-pr.ts <pr_id> [--force] [--cache-root <path>] [--context <lines>]");
  console.error("  Local Mode: npx tsx prep-pr.ts --local [--base <branch>] [--include-untracked]");
  console.error("");
  console.error("PR Mode Options:");
  console.error("  <pr_id>        Pull request ID to review");
  console.error("  --force        Force rebuild even if cache is current");
  console.error("  --cache-root   Directory for .claude/pr-cache (default: current dir)");
  console.error("  --context      Number of context lines in diffs (default: 3)");
  console.error("");
  console.error("Local Mode Options:");
  console.error("  --local              Enable local mode (review uncommitted changes)");
  console.error("  --base <branch>      Target branch to diff against (default: main)");
  console.error("  --include-untracked  Include untracked files in review");
  console.error("  --cache-root         Directory for .claude/pr-cache (default: current dir)");
  console.error("  --context            Number of context lines in diffs (default: 3)");
  process.exit(1);
}
