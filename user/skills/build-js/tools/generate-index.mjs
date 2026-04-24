#!/usr/bin/env node
/**
 * build.js Index Generator
 *
 * Parses build.js and generates a JSON index of key structures:
 * - Imports
 * - Cognito.ready blocks
 * - Regions
 * - form.meta.addProperty calls
 * - form.meta.addRule calls
 * - Event handlers (Cognito.Forms.XyzChanged)
 * - Top-level functions
 */

import { readFileSync, writeFileSync, statSync, existsSync } from 'fs';
import { dirname, join, resolve } from 'path';
import { fileURLToPath } from 'url';
import { execSync } from 'child_process';

const __dirname = dirname(fileURLToPath(import.meta.url));
const SKILL_DIR = resolve(__dirname, '..');
const HOME_DIR = process.env.HOME || process.env.USERPROFILE;
const BUILD_JS_REL_PATH = 'Cognito.Services/Views/Shared/build.js';

/**
 * Find build.js path - supports git worktrees
 * Priority:
 * 1. Command line argument (--repo-root=/path)
 * 2. Git repo root (works in worktrees)
 * 3. Fallback to hardcoded home path
 */
function findBuildJsPath() {
    // Check command line argument
    const repoRootArg = process.argv.find(arg => arg.startsWith('--repo-root='));
    if (repoRootArg) {
        const repoRoot = repoRootArg.split('=')[1];
        const path = join(repoRoot, BUILD_JS_REL_PATH);
        if (existsSync(path)) {
            console.log(`Using repo root from argument: ${repoRoot}`);
            return path;
        }
        console.warn(`Warning: build.js not found at specified repo root: ${path}`);
    }

    // Try git rev-parse (works in worktrees)
    try {
        const gitRoot = execSync('git rev-parse --show-toplevel', { encoding: 'utf-8' }).trim();
        const path = join(gitRoot, BUILD_JS_REL_PATH);
        if (existsSync(path)) {
            console.log(`Using git root: ${gitRoot}`);
            return path;
        }
    } catch {
        // Not in a git repo, fall through
    }

    // Fallback to hardcoded path
    const fallbackPath = join(HOME_DIR, 'source/repos/Cognito Forms', BUILD_JS_REL_PATH);
    console.log(`Using fallback path: ${fallbackPath}`);
    return fallbackPath;
}

const INDEX_PATH = join(SKILL_DIR, 'build-js-index.json');

function main() {
    const BUILD_JS_PATH = findBuildJsPath();
    console.log('Reading build.js...');
    const content = readFileSync(BUILD_JS_PATH, 'utf-8');
    const lines = content.split('\n');
    const stats = statSync(BUILD_JS_PATH);

    const index = {
        meta: {
            sourceFile: BUILD_JS_PATH,
            generatedAt: new Date().toISOString(),
            sourceModified: stats.mtime.toISOString(),
            lineCount: lines.length
        },
        imports: extractImports(lines),
        readyBlocks: extractReadyBlocks(lines),
        regions: extractRegions(lines),
        properties: extractProperties(lines),
        rules: extractRules(lines),
        eventHandlers: extractEventHandlers(lines),
        functions: extractFunctions(lines)
    };

    writeFileSync(INDEX_PATH, JSON.stringify(index, null, 2));
    console.log(`Index written to ${INDEX_PATH}`);
    console.log(`  - ${index.imports.length} imports`);
    console.log(`  - ${index.readyBlocks.length} ready blocks`);
    console.log(`  - ${index.regions.length} regions`);
    console.log(`  - ${index.properties.length} properties`);
    console.log(`  - ${index.rules.length} rules`);
    console.log(`  - ${index.eventHandlers.length} event handlers`);
    console.log(`  - ${index.functions.length} functions`);
}

/**
 * Extract ES6 imports
 * Pattern: import { ... } from '...';
 */
function extractImports(lines) {
    const imports = [];
    let inImport = false;
    let currentImport = { line: 0, source: '', symbols: [] };
    let buffer = '';

    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        const lineNum = i + 1;

        // Stop looking for imports once we hit export default or function declarations
        if (line.match(/^export default|^function\s+\w+/)) {
            break;
        }

        // Start of import
        if (line.match(/^import\s/)) {
            inImport = true;
            currentImport = { line: lineNum, source: '', symbols: [] };
            buffer = line;
        } else if (inImport) {
            buffer += ' ' + line.trim();
        }

        // End of import (has 'from' and ends with semicolon or has closing quote)
        if (inImport && buffer.includes('from') && (buffer.includes(';') || buffer.match(/['"]$/))) {
            // Extract source path
            const sourceMatch = buffer.match(/from\s+['"]([^'"]+)['"]/);
            if (sourceMatch) {
                currentImport.source = sourceMatch[1];
            }

            // Extract symbols
            const symbolsMatch = buffer.match(/import\s+\{([^}]+)\}/);
            if (symbolsMatch) {
                currentImport.symbols = symbolsMatch[1]
                    .split(',')
                    .map(s => s.trim())
                    .filter(s => s.length > 0);
            } else {
                // Default import: import foo from '...'
                const defaultMatch = buffer.match(/import\s+(\w+)\s+from/);
                if (defaultMatch) {
                    currentImport.symbols = [defaultMatch[1]];
                }
            }

            imports.push(currentImport);
            inImport = false;
            buffer = '';
        }
    }

    return imports;
}

/**
 * Extract Cognito.ready blocks
 * Pattern: Cognito.ready("Name", ["dep1", "dep2"], function
 */
function extractReadyBlocks(lines) {
    const blocks = [];

    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        const lineNum = i + 1;

        const match = line.match(/Cognito\.ready\(\s*["']([^"']+)["']\s*,\s*\[([^\]]*)\]/);
        if (match) {
            const name = match[1];
            const depsStr = match[2];
            const dependencies = depsStr
                .split(',')
                .map(d => d.trim().replace(/["']/g, ''))
                .filter(d => d.length > 0);

            blocks.push({ line: lineNum, name, dependencies });
        }
    }

    return blocks;
}

/**
 * Extract region blocks
 * Pattern: //#region Name ... //#endregion
 */
function extractRegions(lines) {
    const regions = [];
    const stack = [];

    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        const lineNum = i + 1;

        const regionMatch = line.match(/\/\/#region\s+(.+)/);
        if (regionMatch) {
            stack.push({ line: lineNum, name: regionMatch[1].trim() });
        }

        if (line.includes('//#endregion') && stack.length > 0) {
            const region = stack.pop();
            region.endLine = lineNum;
            regions.push(region);
        }
    }

    // Sort by start line
    return regions.sort((a, b) => a.line - b.line);
}

/**
 * Extract form.meta.addProperty calls
 * Pattern: form.meta.addProperty({ name: "...", type: ... })
 * Optionally with .calculated({ ... onChangeOf: [...] })
 */
function extractProperties(lines) {
    const properties = [];

    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        const lineNum = i + 1;

        // Match addProperty call
        const propMatch = line.match(/form\.meta\.addProperty\(\{\s*name:\s*["']([^"']+)["']\s*,\s*type:\s*(\w+(?:\.\w+)*)/);
        if (propMatch) {
            const prop = {
                line: lineNum,
                name: propMatch[1],
                type: propMatch[2],
                isList: line.includes('isList: true'),
                isCalculated: false,
                onChangeOf: []
            };

            // Look ahead for .calculated() chain
            if (line.includes('.calculated(')) {
                prop.isCalculated = true;

                // Look for onChangeOf in next 20 lines
                let buffer = line;
                for (let j = i + 1; j < Math.min(i + 20, lines.length); j++) {
                    buffer += ' ' + lines[j];
                    if (lines[j].includes('});') || lines[j].includes('}).')) {
                        break;
                    }
                }

                const onChangeMatch = buffer.match(/onChangeOf:\s*\[([^\]]+)\]/);
                if (onChangeMatch) {
                    prop.onChangeOf = parseQuotedArray(onChangeMatch[1]);
                }
            }

            properties.push(prop);
        }
    }

    return properties;
}

/**
 * Extract form.meta.addRule calls
 * Pattern: form.meta.addRule({ execute: ..., onChangeOf: [...] })
 */
function extractRules(lines) {
    const rules = [];

    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        const lineNum = i + 1;

        if (line.includes('form.meta.addRule({')) {
            // Gather the full rule (look ahead up to 30 lines)
            let buffer = line;
            let braceCount = (line.match(/\{/g) || []).length - (line.match(/\}/g) || []).length;
            let endLine = i;

            for (let j = i + 1; j < Math.min(i + 30, lines.length) && braceCount > 0; j++) {
                buffer += ' ' + lines[j];
                braceCount += (lines[j].match(/\{/g) || []).length;
                braceCount -= (lines[j].match(/\}/g) || []).length;
                endLine = j;
            }

            const rule = {
                line: lineNum,
                onChangeOf: [],
                isHasChangesRule: false
            };

            // Extract onChangeOf
            const onChangeMatch = buffer.match(/onChangeOf:\s*\[([^\]]+)\]/);
            if (onChangeMatch) {
                rule.onChangeOf = parseQuotedArray(onChangeMatch[1]);
            }

            // Detect HasChanges rule
            if (buffer.includes('set_HasChanges(true)') ||
                buffer.includes("HasChanges")) {
                rule.isHasChangesRule = true;
            }

            // Add description from execute body
            if (buffer.includes('handleKnownValueRename')) {
                rule.description = 'Role rename handler';
            } else if (buffer.includes('set_HasChanges')) {
                rule.description = 'Mark form dirty on change';
            } else if (buffer.includes('data-dirty')) {
                rule.description = 'Update save button state';
            }

            rules.push(rule);
        }
    }

    return rules;
}

/**
 * Extract event handlers
 * Pattern: Cognito.Forms.XyzChanged = function
 */
function extractEventHandlers(lines) {
    const handlers = [];

    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        const lineNum = i + 1;

        const match = line.match(/Cognito\.Forms\.(\w+Changed)\s*=\s*function/);
        if (match) {
            handlers.push({
                line: lineNum,
                name: match[1]
            });
        }
    }

    return handlers;
}

/**
 * Extract top-level functions
 * Pattern: function name(...) { at reasonable indent levels
 * Also: Cognito.Forms.methodName = function
 */
function extractFunctions(lines) {
    const functions = [];

    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        const lineNum = i + 1;

        // Named function declarations (indented 0-2 tabs)
        const funcMatch = line.match(/^(\t{0,2})function\s+(\w+)\s*\(/);
        if (funcMatch) {
            const indent = funcMatch[1].length;
            functions.push({
                line: lineNum,
                name: funcMatch[2],
                scope: indent === 0 ? 'export' : 'local',
                indent
            });
            continue;
        }

        // Cognito.Forms methods (not event handlers)
        const cognitoMethod = line.match(/Cognito\.Forms\.(\w+)\s*=\s*function/);
        if (cognitoMethod && !cognitoMethod[1].endsWith('Changed')) {
            functions.push({
                line: lineNum,
                name: cognitoMethod[1],
                scope: 'Cognito.Forms'
            });
        }
    }

    return functions;
}

/**
 * Parse an array of quoted strings, handling commas inside braces
 * e.g., '"foo", "bar{a,b}", "baz"' => ["foo", "bar{a,b}", "baz"]
 */
function parseQuotedArray(str) {
    const results = [];
    let current = '';
    let braceDepth = 0;
    let inQuote = false;
    let quoteChar = null;

    for (let i = 0; i < str.length; i++) {
        const char = str[i];

        if (!inQuote && (char === '"' || char === "'")) {
            inQuote = true;
            quoteChar = char;
        } else if (inQuote && char === quoteChar && str[i - 1] !== '\\') {
            inQuote = false;
            quoteChar = null;
        } else if (char === '{') {
            braceDepth++;
            current += char;
        } else if (char === '}') {
            braceDepth--;
            current += char;
        } else if (char === ',' && braceDepth === 0 && !inQuote) {
            const trimmed = current.trim();
            if (trimmed.length > 0) {
                results.push(trimmed);
            }
            current = '';
        } else if (inQuote || (char !== '"' && char !== "'")) {
            current += char;
        }
    }

    const trimmed = current.trim();
    if (trimmed.length > 0) {
        results.push(trimmed);
    }

    return results;
}

// Run
main();
