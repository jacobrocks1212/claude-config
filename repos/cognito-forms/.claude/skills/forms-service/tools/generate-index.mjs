#!/usr/bin/env node
/**
 * FormsService.cs Index Generator
 *
 * Parses FormsService.cs and generates a JSON index of key structures:
 * - Regions
 * - Methods (with parameters, visibility, async status)
 * - Nested classes/enums/structs
 * - Constructor dependencies
 * - Method categorization by verb
 */

import { readFileSync, writeFileSync, statSync, existsSync } from 'fs';
import { dirname, join, resolve } from 'path';
import { fileURLToPath } from 'url';
import { execSync } from 'child_process';

const __dirname = dirname(fileURLToPath(import.meta.url));
const SKILL_DIR = resolve(__dirname, '..');
const HOME_DIR = process.env.HOME || process.env.USERPROFILE;
const FORMS_SERVICE_REL_PATH = 'Cognito.Core/Services/Forms/FormsService.cs';

/**
 * Find FormsService.cs path - supports git worktrees
 */
function findFormsServicePath() {
    // Check command line argument
    const repoRootArg = process.argv.find(arg => arg.startsWith('--repo-root='));
    if (repoRootArg) {
        const repoRoot = repoRootArg.split('=')[1];
        const path = join(repoRoot, FORMS_SERVICE_REL_PATH);
        if (existsSync(path)) {
            console.log(`Using repo root from argument: ${repoRoot}`);
            return path;
        }
        console.warn(`Warning: FormsService.cs not found at specified repo root: ${path}`);
    }

    // Try git rev-parse (works in worktrees)
    try {
        const gitRoot = execSync('git rev-parse --show-toplevel', { encoding: 'utf-8' }).trim();
        const path = join(gitRoot, FORMS_SERVICE_REL_PATH);
        if (existsSync(path)) {
            console.log(`Using git root: ${gitRoot}`);
            return path;
        }
    } catch {
        // Not in a git repo, fall through
    }

    // Fallback to hardcoded path
    const fallbackPath = join(HOME_DIR, 'source/repos/Cognito Forms', FORMS_SERVICE_REL_PATH);
    console.log(`Using fallback path: ${fallbackPath}`);
    return fallbackPath;
}

const INDEX_PATH = join(SKILL_DIR, 'forms-service-index.json');

/**
 * Extract #region blocks
 */
export function extractRegions(lines) {
    const regions = [];
    const stack = [];

    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        const lineNum = i + 1;

        const regionMatch = line.match(/#region\s+(.+)/);
        if (regionMatch) {
            stack.push({ line: lineNum, name: regionMatch[1].trim() });
        }

        if (line.includes('#endregion') && stack.length > 0) {
            const region = stack.pop();
            region.endLine = lineNum;
            regions.push(region);
        }
    }

    // Sort by start line
    return regions.sort((a, b) => a.line - b.line);
}

/**
 * Extract method signatures
 */
export function extractMethods(lines) {
    const methods = [];
    const visibilityPattern = /^\s*(public|private|internal|protected)\s+/;

    let multiLineBuffer = null;
    let multiLineStart = 0;

    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        const lineNum = i + 1;

        // Skip property declarations (has { get or { set on same line or next)
        if (line.includes('{') && (line.includes('get') || line.includes('set'))) {
            continue;
        }

        // Skip field declarations (= new, =>, readonly without method pattern)
        if (line.includes('readonly') && !line.includes('(')) {
            continue;
        }

        // Check for multi-line method start
        if (multiLineBuffer === null) {
            const visMatch = line.match(visibilityPattern);
            if (visMatch && line.includes('(') && !line.includes(')')) {
                // Start of multi-line method
                multiLineBuffer = line;
                multiLineStart = lineNum;
                continue;
            }
        } else {
            // Continue multi-line method
            multiLineBuffer += ' ' + line.trim();
            if (line.includes(')')) {
                // End of multi-line method
                const method = parseMethodSignature(multiLineBuffer, multiLineStart);
                if (method) {
                    methods.push(method);
                }
                multiLineBuffer = null;
                continue;
            }
            continue;
        }

        // Single-line method signature
        const visMatch = line.match(visibilityPattern);
        if (!visMatch) continue;

        // Must have parentheses for a method
        if (!line.includes('(')) continue;

        // Skip if it's a class/struct/enum declaration
        if (line.match(/\b(class|struct|enum|interface)\b/)) continue;

        const method = parseMethodSignature(line, lineNum);
        if (method) {
            methods.push(method);
        }
    }

    return methods;
}

/**
 * Parse a method signature line into structured data
 */
function parseMethodSignature(line, lineNum) {
    // Pattern: [visibility] [static] [async] [virtual|override] [returnType] [name]([params])
    const methodPattern = /^\s*(public|private|internal|protected)\s+(?:(static)\s+)?(?:(async)\s+)?(?:(virtual|override)\s+)?(\S+)\s+(\w+)\s*\(/;

    const match = line.match(methodPattern);
    if (!match) return null;

    const [, visibility, isStatic, isAsync, modifier, returnType, name] = match;

    // Skip constructors (return type equals name or no return type)
    if (returnType === name || name === 'FormsService') return null;

    // Extract parameters
    const paramsMatch = line.match(/\(([^)]*)\)?/);
    const paramsStr = paramsMatch ? paramsMatch[1] : '';
    const parameters = parseParameters(paramsStr);

    return {
        line: lineNum,
        name,
        returnType,
        visibility,
        isAsync: !!isAsync,
        isStatic: !!isStatic,
        isVirtual: modifier === 'virtual',
        isOverride: modifier === 'override',
        parameters
    };
}

/**
 * Parse parameter string into structured array
 */
function parseParameters(paramsStr) {
    if (!paramsStr.trim()) return [];

    const params = [];
    let current = '';
    let depth = 0;

    // Split by comma, respecting generics
    for (const char of paramsStr) {
        if (char === '<') depth++;
        else if (char === '>') depth--;
        else if (char === ',' && depth === 0) {
            if (current.trim()) {
                params.push(parseParam(current.trim()));
            }
            current = '';
            continue;
        }
        current += char;
    }
    if (current.trim()) {
        params.push(parseParam(current.trim()));
    }

    return params;
}

/**
 * Parse a single parameter
 */
function parseParam(paramStr) {
    // Pattern: [type] [name] [= default]
    const defaultMatch = paramStr.match(/^(.+?)\s*=\s*(.+)$/);
    let remaining = paramStr;
    let defaultValue = undefined;
    let hasDefault = false;

    if (defaultMatch) {
        remaining = defaultMatch[1].trim();
        defaultValue = defaultMatch[2].trim();
        hasDefault = true;
    }

    // Split type and name - last word is name, rest is type
    const parts = remaining.split(/\s+/);
    const name = parts.pop();
    const type = parts.join(' ');

    const result = { name, type, hasDefault };
    if (hasDefault) {
        result.defaultValue = defaultValue;
    }
    return result;
}

/**
 * Extract nested types (classes, enums, structs)
 */
export function extractNestedTypes(lines) {
    const types = [];

    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        const lineNum = i + 1;

        const typeMatch = line.match(/^\s*(public|private|internal|protected)?\s*(class|enum|struct)\s+(\w+)/);
        if (typeMatch) {
            const [, visibility, kind, name] = typeMatch;

            // Skip the main FormsService class
            if (name === 'FormsService') continue;

            types.push({
                line: lineNum,
                name,
                kind,
                visibility: visibility || 'private'
            });
        }
    }

    return types;
}

/**
 * Extract constructor dependencies
 */
export function extractDependencies(lines) {
    const dependencies = [];
    let inConstructor = false;
    let buffer = '';

    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];

        // Start of FormsService constructor
        if (line.includes('FormsService(') && !line.includes('new FormsService')) {
            inConstructor = true;
            buffer = line;
            continue;
        }

        if (inConstructor) {
            buffer += ' ' + line.trim();

            // End of constructor params (base call or opening brace)
            if (line.includes(': base') || (line.includes(')') && !line.match(/\(\s*$/))) {
                inConstructor = false;

                // Extract parameters from buffer
                const paramsMatch = buffer.match(/FormsService\s*\(([^)]+)\)/);
                if (paramsMatch) {
                    const paramsStr = paramsMatch[1];
                    const params = parseParameters(paramsStr);
                    for (const p of params) {
                        dependencies.push({ name: p.name, type: p.type });
                    }
                }
            }
        }
    }

    return dependencies;
}

/**
 * Categorize methods by their verb prefix
 */
export function categorizeByVerb(methods) {
    const categories = {
        create: [],
        get: [],
        update: [],
        delete: [],
        store: [],
        save: [],
        assert: [],
        validate: [],
        can: [],
        remove: [],
        add: [],
        set: [],
        link: [],
        other: []
    };

    const verbPatterns = [
        { pattern: /^Create/, category: 'create' },
        { pattern: /^Get/, category: 'get' },
        { pattern: /^Update/, category: 'update' },
        { pattern: /^Delete/, category: 'delete' },
        { pattern: /^Store/, category: 'store' },
        { pattern: /^Save/, category: 'save' },
        { pattern: /^Assert/, category: 'assert' },
        { pattern: /^Validate/, category: 'validate' },
        { pattern: /^Can/, category: 'can' },
        { pattern: /^Remove/, category: 'remove' },
        { pattern: /^Add/, category: 'add' },
        { pattern: /^Set/, category: 'set' },
        { pattern: /Link$/, category: 'link' }
    ];

    for (const method of methods) {
        let matched = false;
        for (const { pattern, category } of verbPatterns) {
            if (pattern.test(method.name)) {
                categories[category].push(method.name);
                matched = true;
                break;
            }
        }
        if (!matched) {
            categories.other.push(method.name);
        }
    }

    // Remove empty categories
    for (const key of Object.keys(categories)) {
        if (categories[key].length === 0) {
            delete categories[key];
        }
    }

    return categories;
}

/**
 * Main parse function
 */
export function parseFormsService(content, sourceFile = null, stats = null) {
    const lines = content.split('\n');

    const regions = extractRegions(lines);
    const methods = extractMethods(lines);
    const nestedTypes = extractNestedTypes(lines);
    const dependencies = extractDependencies(lines);
    const methodsByVerb = categorizeByVerb(methods);

    return {
        meta: {
            sourceFile,
            generatedAt: new Date().toISOString(),
            sourceModified: stats?.mtime?.toISOString() || null,
            lineCount: lines.length
        },
        regions,
        methods,
        nestedTypes,
        dependencies,
        methodsByVerb
    };
}

/**
 * Main entry point when run as script
 */
function main() {
    const FORMS_SERVICE_PATH = findFormsServicePath();
    console.log('Reading FormsService.cs...');
    const content = readFileSync(FORMS_SERVICE_PATH, 'utf-8');
    const stats = statSync(FORMS_SERVICE_PATH);

    const index = parseFormsService(content, FORMS_SERVICE_PATH, stats);

    writeFileSync(INDEX_PATH, JSON.stringify(index, null, 2));
    console.log(`Index written to ${INDEX_PATH}`);
    console.log(`  - ${index.regions.length} regions`);
    console.log(`  - ${index.methods.length} methods`);
    console.log(`  - ${index.nestedTypes.length} nested types`);
    console.log(`  - ${index.dependencies.length} dependencies`);
    console.log(`  - ${Object.keys(index.methodsByVerb).length} verb categories`);
}

// Run main if invoked directly
const isMain = process.argv[1] && import.meta.url.endsWith(process.argv[1].replace(/\\/g, '/').split('/').pop());
if (isMain) {
    main();
}
