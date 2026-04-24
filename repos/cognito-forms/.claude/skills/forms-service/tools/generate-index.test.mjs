#!/usr/bin/env node
/**
 * Tests for FormsService.cs Index Generator
 * Run with: node --test ~/.claude/skills/forms-service/tools/generate-index.test.mjs
 */

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'fs';
import { dirname, join, resolve } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));

// Import the generator module (will fail until implemented)
let generator;
try {
    generator = await import('./generate-index.mjs');
} catch (e) {
    console.error('Generator module not yet implemented:', e.message);
    process.exit(1);
}

const {
    extractRegions,
    extractMethods,
    extractNestedTypes,
    extractDependencies,
    categorizeByVerb,
    parseFormsService
} = generator;

// ============================================================================
// Phase 1: Test Infrastructure
// ============================================================================

describe('Phase 1: Test Infrastructure', () => {
    it('parses sample C# content without error', () => {
        const sample = `
using System;

namespace Cognito.Forms.Services
{
    public class FormsService
    {
        public Form GetForm(string id)
        {
            return context.Get<Form>(id);
        }
    }
}
`;
        const result = parseFormsService(sample);
        assert.ok(result, 'Should return a result');
        assert.ok(result.meta, 'Should have meta property');
        assert.ok(result.meta.lineCount > 0, 'Should have line count');
    });

    it('extracts metadata correctly', () => {
        const sample = 'line1\nline2\nline3';
        const result = parseFormsService(sample);
        assert.ok(result.meta.generatedAt, 'Should have generatedAt');
        assert.equal(result.meta.lineCount, 3, 'Should count lines correctly');
    });
});

// ============================================================================
// Phase 2: Region Extraction
// ============================================================================

describe('Phase 2: Region Extraction', () => {
    it('extracts regions with start/end lines', () => {
        const lines = [
            '',
            '		#region Email Domains',
            '		// ... content ...',
            '		// more content',
            '		#endregion'
        ];
        const result = extractRegions(lines);
        assert.equal(result.length, 1, 'Should find 1 region');
        assert.deepEqual(result[0], {
            line: 2,
            name: 'Email Domains',
            endLine: 5
        });
    });

    it('handles nested regions', () => {
        const lines = [
            '		#region Outer',
            '			#region Inner',
            '			#endregion',
            '		#endregion'
        ];
        const result = extractRegions(lines);
        assert.equal(result.length, 2, 'Should find 2 regions');
        // Inner region closes first
        const inner = result.find(r => r.name === 'Inner');
        const outer = result.find(r => r.name === 'Outer');
        assert.ok(inner, 'Should find Inner region');
        assert.ok(outer, 'Should find Outer region');
        assert.equal(inner.endLine, 3);
        assert.equal(outer.endLine, 4);
    });

    it('handles region with extra whitespace', () => {
        const lines = [
            '  #region   Import  ',
            '  #endregion'
        ];
        const result = extractRegions(lines);
        assert.equal(result.length, 1);
        assert.equal(result[0].name, 'Import');
    });
});

// ============================================================================
// Phase 3: Method Extraction
// ============================================================================

describe('Phase 3: Method Extraction', () => {
    it('extracts public method with return type', () => {
        const lines = [
            '',
            '		public Form GetForm(string id)',
            '		{',
            '			return context.Get<Form>(id);',
            '		}'
        ];
        const result = extractMethods(lines);
        assert.equal(result.length, 1);
        assert.equal(result[0].name, 'GetForm');
        assert.equal(result[0].returnType, 'Form');
        assert.equal(result[0].visibility, 'public');
        assert.equal(result[0].isAsync, false);
        assert.equal(result[0].isStatic, false);
        assert.equal(result[0].line, 2);
    });

    it('extracts async method', () => {
        const lines = [
            '		public async Task<Form> GetFormAsync(string id)'
        ];
        const result = extractMethods(lines);
        assert.equal(result.length, 1);
        assert.equal(result[0].name, 'GetFormAsync');
        assert.equal(result[0].returnType, 'Task<Form>');
        assert.equal(result[0].isAsync, true);
    });

    it('extracts static method', () => {
        const lines = [
            '		public static Form CreateBlankForm()'
        ];
        const result = extractMethods(lines);
        assert.equal(result.length, 1);
        assert.equal(result[0].name, 'CreateBlankForm');
        assert.equal(result[0].isStatic, true);
    });

    it('extracts virtual/override methods', () => {
        const lines = [
            '		public override void RemoveModule()',
            '		public virtual Form GetForm(string id)'
        ];
        const result = extractMethods(lines);
        assert.equal(result.length, 2);
        assert.equal(result[0].name, 'RemoveModule');
        assert.equal(result[0].isOverride, true);
        assert.equal(result[1].name, 'GetForm');
        assert.equal(result[1].isVirtual, true);
    });

    it('extracts method parameters', () => {
        const lines = [
            '		public SubmissionResult SaveEntry(Form form, FormEntry entry, bool validate = true)'
        ];
        const result = extractMethods(lines);
        assert.equal(result.length, 1);
        assert.deepEqual(result[0].parameters, [
            { name: 'form', type: 'Form', hasDefault: false },
            { name: 'entry', type: 'FormEntry', hasDefault: false },
            { name: 'validate', type: 'bool', hasDefault: true, defaultValue: 'true' }
        ]);
    });

    it('extracts generic parameters', () => {
        const lines = [
            '		public IEnumerable<Form> GetForms()'
        ];
        const result = extractMethods(lines);
        assert.equal(result.length, 1);
        assert.equal(result[0].returnType, 'IEnumerable<Form>');
    });

    it('extracts nullable parameters', () => {
        const lines = [
            '		public bool Assert(SecurityTask task, FormRef form = null)'
        ];
        const result = extractMethods(lines);
        assert.equal(result.length, 1);
        assert.deepEqual(result[0].parameters, [
            { name: 'task', type: 'SecurityTask', hasDefault: false },
            { name: 'form', type: 'FormRef', hasDefault: true, defaultValue: 'null' }
        ]);
    });

    it('extracts private methods', () => {
        const lines = [
            '		private Form GetFormInternal(string id)'
        ];
        const result = extractMethods(lines);
        assert.equal(result.length, 1);
        assert.equal(result[0].visibility, 'private');
    });

    it('extracts internal methods', () => {
        const lines = [
            '		internal Form GetFormForTesting(string id)'
        ];
        const result = extractMethods(lines);
        assert.equal(result.length, 1);
        assert.equal(result[0].visibility, 'internal');
    });

    it('ignores property getters/setters', () => {
        const lines = [
            '		public bool AllowEntryLimitExceeded { get { return GetEntryLimitExceededBehavior() != LimitExceededBehavior.Disallowed; } }'
        ];
        const result = extractMethods(lines);
        assert.equal(result.length, 0, 'Should not extract properties');
    });

    it('ignores field declarations', () => {
        const lines = [
            '		public static readonly Regex SearchTermsRegex = new Regex(...);'
        ];
        const result = extractMethods(lines);
        assert.equal(result.length, 0, 'Should not extract fields');
    });

    it('handles multi-line method signatures', () => {
        const lines = [
            '		public bool Assert(',
            '			SecurityTask task,',
            '			FormRef form,',
            '			bool throwException = true)'
        ];
        const result = extractMethods(lines);
        assert.equal(result.length, 1);
        assert.equal(result[0].name, 'Assert');
        assert.equal(result[0].parameters.length, 3);
    });
});

// ============================================================================
// Phase 4: Nested Type Extraction
// ============================================================================

describe('Phase 4: Nested Type Extraction', () => {
    it('extracts nested class', () => {
        const lines = [
            '',
            '		public class StoreFormResult',
            '		{',
            '			public bool Success { get; set; }',
            '		}'
        ];
        const result = extractNestedTypes(lines);
        assert.equal(result.length, 1);
        assert.deepEqual(result[0], {
            line: 2,
            name: 'StoreFormResult',
            kind: 'class',
            visibility: 'public'
        });
    });

    it('extracts nested enum', () => {
        const lines = [
            '	public enum EntryAction',
            '	{',
            '		None,',
            '		View',
            '	}'
        ];
        const result = extractNestedTypes(lines);
        assert.equal(result.length, 1);
        assert.equal(result[0].kind, 'enum');
        assert.equal(result[0].name, 'EntryAction');
    });

    it('extracts nested struct', () => {
        const lines = [
            '		public struct FieldInfo',
            '		{'
        ];
        const result = extractNestedTypes(lines);
        assert.equal(result.length, 1);
        assert.equal(result[0].kind, 'struct');
    });

    it('extracts internal types', () => {
        const lines = [
            '		internal class FormValidator'
        ];
        const result = extractNestedTypes(lines);
        assert.equal(result.length, 1);
        assert.equal(result[0].visibility, 'internal');
    });

    it('skips the main FormsService class', () => {
        const lines = [
            '	public class FormsService : ModuleService<IFormsService, FormsConfiguration>, IFormsService',
            '	{',
            '		public class NestedType',
            '		{'
        ];
        const result = extractNestedTypes(lines);
        assert.equal(result.length, 1, 'Should only find NestedType');
        assert.equal(result[0].name, 'NestedType');
    });
});

// ============================================================================
// Phase 5: Dependency Extraction
// ============================================================================

describe('Phase 5: Dependency Extraction', () => {
    it('extracts constructor dependencies', () => {
        const lines = [
            '		public FormsService(ICoreService coreService, IStorageContext context, IPaymentService paymentService)',
            '			: base(coreService, context, config)',
            '		{'
        ];
        const result = extractDependencies(lines);
        assert.ok(result.some(d => d.name === 'coreService' && d.type === 'ICoreService'));
        assert.ok(result.some(d => d.name === 'context' && d.type === 'IStorageContext'));
        assert.ok(result.some(d => d.name === 'paymentService' && d.type === 'IPaymentService'));
    });

    it('extracts multi-line constructor', () => {
        const lines = [
            '		public FormsService(',
            '			ICoreService coreService,',
            '			IStorageContext context,',
            '			ModuleConfigurationRef config)',
            '			: base(coreService)'
        ];
        const result = extractDependencies(lines);
        assert.equal(result.length, 3);
        assert.ok(result.some(d => d.name === 'config' && d.type === 'ModuleConfigurationRef'));
    });
});

// ============================================================================
// Phase 6: Method Categorization
// ============================================================================

describe('Phase 6: Method Categorization', () => {
    it('categorizes by CRUD verbs', () => {
        const methods = [
            { name: 'CreateFolder' },
            { name: 'CreateBlankForm' },
            { name: 'GetForm' },
            { name: 'GetEntry' },
            { name: 'UpdateFormFeatures' },
            { name: 'UpdateEntryStatus' },
            { name: 'DeleteForm' },
            { name: 'DeleteEntry' },
            { name: 'StoreForm' },
            { name: 'SaveEntry' }
        ];
        const result = categorizeByVerb(methods);

        assert.deepEqual(result.create, ['CreateFolder', 'CreateBlankForm']);
        assert.deepEqual(result.get, ['GetForm', 'GetEntry']);
        assert.deepEqual(result.update, ['UpdateFormFeatures', 'UpdateEntryStatus']);
        assert.deepEqual(result.delete, ['DeleteForm', 'DeleteEntry']);
        assert.deepEqual(result.store, ['StoreForm']);
        assert.deepEqual(result.save, ['SaveEntry']);
    });

    it('categorizes Assert methods', () => {
        const methods = [
            { name: 'Assert' },
            { name: 'AssertOwner' }
        ];
        const result = categorizeByVerb(methods);
        assert.deepEqual(result.assert, ['Assert', 'AssertOwner']);
    });

    it('categorizes Validate/Can methods', () => {
        const methods = [
            { name: 'ValidateForm' },
            { name: 'ValidateAccessToken' },
            { name: 'CanSubmit' },
            { name: 'CanEdit' }
        ];
        const result = categorizeByVerb(methods);
        assert.deepEqual(result.validate, ['ValidateForm', 'ValidateAccessToken']);
        assert.deepEqual(result.can, ['CanSubmit', 'CanEdit']);
    });

    it('categorizes link-related methods', () => {
        const methods = [
            { name: 'CreateSharedLink' },
            { name: 'CreateWorkflowLink' },
            { name: 'CreateEntryLink' }
        ];
        const result = categorizeByVerb(methods);
        // These could be in 'create' or a separate 'link' category
        assert.ok(result.create.includes('CreateSharedLink') || result.link?.includes('CreateSharedLink'));
    });

    it('handles uncategorized methods', () => {
        const methods = [
            { name: 'ProcessSubmission' },
            { name: 'HandleWebhook' }
        ];
        const result = categorizeByVerb(methods);
        assert.ok(result.other, 'Should have other category');
        assert.ok(result.other.includes('ProcessSubmission'));
    });
});

// ============================================================================
// Phase 7: Integration Test (Real File)
// ============================================================================

describe('Phase 7: Integration with Real FormsService.cs', () => {
    const HOME = process.env.HOME || process.env.USERPROFILE;
    const FORMS_SERVICE_PATH = join(HOME, 'source/repos/Cognito Forms/Cognito.Core/Services/Forms/FormsService.cs');

    const fileExists = existsSync(FORMS_SERVICE_PATH);

    it('real file exists', { skip: !fileExists }, () => {
        assert.ok(fileExists, 'FormsService.cs should exist');
    });

    it('parses real FormsService.cs', { skip: !fileExists }, () => {
        const content = readFileSync(FORMS_SERVICE_PATH, 'utf-8');
        const result = parseFormsService(content);

        // Based on the grep results:
        // - 303 public members
        // - 4 regions
        // - 8+ nested types
        assert.ok(result.methods.length > 200, `Should have >200 methods, got ${result.methods.length}`);
        assert.equal(result.regions.length, 4, `Should have 4 regions, got ${result.regions.length}`);
        assert.ok(result.nestedTypes.length >= 6, `Should have >=6 nested types, got ${result.nestedTypes.length}`);
    });

    it('extracts correct region names', { skip: !fileExists }, () => {
        const content = readFileSync(FORMS_SERVICE_PATH, 'utf-8');
        const result = parseFormsService(content);

        const regionNames = result.regions.map(r => r.name);
        assert.ok(regionNames.includes('Email Domains'), 'Should have Email Domains region');
        assert.ok(regionNames.includes('Import'), 'Should have Import region');
        assert.ok(regionNames.includes('Entry Views'), 'Should have Entry Views region');
        assert.ok(regionNames.includes('XmlCleanser'), 'Should have XmlCleanser region');
    });

    it('extracts known methods with correct line numbers', { skip: !fileExists }, () => {
        const content = readFileSync(FORMS_SERVICE_PATH, 'utf-8');
        const result = parseFormsService(content);

        // Based on grep output:
        // 838: public Form GetForm(string id)
        // 843: public async Task<Form> GetFormAsync(string id)
        const getForm = result.methods.find(m => m.name === 'GetForm' && m.returnType === 'Form');
        const getFormAsync = result.methods.find(m => m.name === 'GetFormAsync');

        assert.ok(getForm, 'Should find GetForm method');
        assert.equal(getForm.line, 838, 'GetForm should be on line 838');

        assert.ok(getFormAsync, 'Should find GetFormAsync method');
        assert.equal(getFormAsync.line, 843, 'GetFormAsync should be on line 843');
        assert.equal(getFormAsync.isAsync, true);
    });

    it('extracts known nested types', { skip: !fileExists }, () => {
        const content = readFileSync(FORMS_SERVICE_PATH, 'utf-8');
        const result = parseFormsService(content);

        const typeNames = result.nestedTypes.map(t => t.name);
        assert.ok(typeNames.includes('EntryAction'), 'Should find EntryAction enum');
        assert.ok(typeNames.includes('StoreFormResult'), 'Should find StoreFormResult class');
        assert.ok(typeNames.includes('FormStorageSummary'), 'Should find FormStorageSummary class');
    });

    it('extracts constructor dependencies', { skip: !fileExists }, () => {
        const content = readFileSync(FORMS_SERVICE_PATH, 'utf-8');
        const result = parseFormsService(content);

        assert.ok(result.dependencies.length > 0, 'Should extract dependencies');
        assert.ok(result.dependencies.some(d => d.type === 'ICoreService'), 'Should have ICoreService dependency');
        assert.ok(result.dependencies.some(d => d.type === 'IStorageContext'), 'Should have IStorageContext dependency');
    });

    it('categorizes methods by verb', { skip: !fileExists }, () => {
        const content = readFileSync(FORMS_SERVICE_PATH, 'utf-8');
        const result = parseFormsService(content);

        assert.ok(result.methodsByVerb.get.length > 0, 'Should have Get methods');
        assert.ok(result.methodsByVerb.create.length > 0, 'Should have Create methods');
        assert.ok(result.methodsByVerb.assert.length > 0, 'Should have Assert methods');
    });
});
