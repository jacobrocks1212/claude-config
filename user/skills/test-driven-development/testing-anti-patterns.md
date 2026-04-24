# Testing Anti-Patterns

**Load this reference when:** writing or changing tests, adding mocks, or tempted to add test-only methods to production code.

## Overview

Tests must verify real behavior, not mock behavior. Mocks are a means to isolate, not the thing being tested.

**Core principle:** Test what the code does, not what the mocks do.

**Following strict TDD prevents these anti-patterns.**

## The Iron Laws

```
1. NEVER test mock behavior
2. NEVER add test-only methods to production classes
3. NEVER mock without understanding dependencies
```

## Anti-Pattern 1: Testing Mock Behavior

**The violation:**
```typescript
// ❌ BAD: Testing that the mock exists
test('renders sidebar', () => {
  render(<Page />);
  expect(screen.getByTestId('sidebar-mock')).toBeInTheDocument();
});
```

**Why this is wrong:**
- You're verifying the mock works, not that the component works
- Test passes when mock is present, fails when it's not
- Tells you nothing about real behavior

**your human partner's correction:** "Are we testing the behavior of a mock?"

**The fix:**
```typescript
// ✅ GOOD: Test real component or don't mock it
test('renders sidebar', () => {
  render(<Page />);  // Don't mock sidebar
  expect(screen.getByRole('navigation')).toBeInTheDocument();
});

// OR if sidebar must be mocked for isolation:
// Don't assert on the mock - test Page's behavior with sidebar present
```

### Gate Function

```
BEFORE asserting on any mock element:
  Ask: "Am I testing real component behavior or just mock existence?"

  IF testing mock existence:
    STOP - Delete the assertion or unmock the component

  Test real behavior instead
```

## Anti-Pattern 2: Test-Only Methods in Production

**The violation:**
```typescript
// ❌ BAD: destroy() only used in tests
class Session {
  async destroy() {  // Looks like production API!
    await this._workspaceManager?.destroyWorkspace(this.id);
    // ... cleanup
  }
}

// In tests
afterEach(() => session.destroy());
```

**Why this is wrong:**
- Production class polluted with test-only code
- Dangerous if accidentally called in production
- Violates YAGNI and separation of concerns
- Confuses object lifecycle with entity lifecycle

**The fix:**
```typescript
// ✅ GOOD: Test utilities handle test cleanup
// Session has no destroy() - it's stateless in production

// In test-utils/
export async function cleanupSession(session: Session) {
  const workspace = session.getWorkspaceInfo();
  if (workspace) {
    await workspaceManager.destroyWorkspace(workspace.id);
  }
}

// In tests
afterEach(() => cleanupSession(session));
```

### Gate Function

```
BEFORE adding any method to production class:
  Ask: "Is this only used by tests?"

  IF yes:
    STOP - Don't add it
    Put it in test utilities instead

  Ask: "Does this class own this resource's lifecycle?"

  IF no:
    STOP - Wrong class for this method
```

## Anti-Pattern 3: Mocking Without Understanding

**The violation:**
```typescript
// ❌ BAD: Mock breaks test logic
test('detects duplicate server', () => {
  // Mock prevents config write that test depends on!
  vi.mock('ToolCatalog', () => ({
    discoverAndCacheTools: vi.fn().mockResolvedValue(undefined)
  }));

  await addServer(config);
  await addServer(config);  // Should throw - but won't!
});
```

**Why this is wrong:**
- Mocked method had side effect test depended on (writing config)
- Over-mocking to "be safe" breaks actual behavior
- Test passes for wrong reason or fails mysteriously

**The fix:**
```typescript
// ✅ GOOD: Mock at correct level
test('detects duplicate server', () => {
  // Mock the slow part, preserve behavior test needs
  vi.mock('MCPServerManager'); // Just mock slow server startup

  await addServer(config);  // Config written
  await addServer(config);  // Duplicate detected ✓
});
```

### Gate Function

```
BEFORE mocking any method:
  STOP - Don't mock yet

  1. Ask: "What side effects does the real method have?"
  2. Ask: "Does this test depend on any of those side effects?"
  3. Ask: "Do I fully understand what this test needs?"

  IF depends on side effects:
    Mock at lower level (the actual slow/external operation)
    OR use test doubles that preserve necessary behavior
    NOT the high-level method the test depends on

  IF unsure what test depends on:
    Run test with real implementation FIRST
    Observe what actually needs to happen
    THEN add minimal mocking at the right level

  Red flags:
    - "I'll mock this to be safe"
    - "This might be slow, better mock it"
    - Mocking without understanding the dependency chain
```

## Anti-Pattern 4: Incomplete Mocks

**The violation:**
```typescript
// ❌ BAD: Partial mock - only fields you think you need
const mockResponse = {
  status: 'success',
  data: { userId: '123', name: 'Alice' }
  // Missing: metadata that downstream code uses
};

// Later: breaks when code accesses response.metadata.requestId
```

**Why this is wrong:**
- **Partial mocks hide structural assumptions** - You only mocked fields you know about
- **Downstream code may depend on fields you didn't include** - Silent failures
- **Tests pass but integration fails** - Mock incomplete, real API complete
- **False confidence** - Test proves nothing about real behavior

**The Iron Rule:** Mock the COMPLETE data structure as it exists in reality, not just fields your immediate test uses.

**The fix:**
```typescript
// ✅ GOOD: Mirror real API completeness
const mockResponse = {
  status: 'success',
  data: { userId: '123', name: 'Alice' },
  metadata: { requestId: 'req-789', timestamp: 1234567890 }
  // All fields real API returns
};
```

### Gate Function

```
BEFORE creating mock responses:
  Check: "What fields does the real API response contain?"

  Actions:
    1. Examine actual API response from docs/examples
    2. Include ALL fields system might consume downstream
    3. Verify mock matches real response schema completely

  Critical:
    If you're creating a mock, you must understand the ENTIRE structure
    Partial mocks fail silently when code depends on omitted fields

  If uncertain: Include all documented fields
```

## Anti-Pattern 5: Homogeneous Fixtures That Don't Exercise Divergent Representations

**The violation:**
```typescript
// ❌ BAD: Both representations carry identical values in every test
const mockItem = {
  full: { begin: 0.25, end: 0.5 },   // unclipped extent
  clipped: { begin: 0.25, end: 0.5 } // same — "clipped" is never actually clipped
};

test('onset uses full begin', () => {
  expect(serialize(mockItem).onset).toBe(0.25); // ✓ passes
});

// No test that varies clipped vs full — duration bug goes undetected
```

**Why this is wrong:**
- When code reads from two representations of the same underlying value (unclipped vs clipped, raw vs normalized, unbounded vs bounded), tests that set them equal exercise only one branch of the code's actual logic
- A bug that reads from the wrong representation is invisible as long as both representations agree
- Having one correct test (e.g. "onset uses the unclipped field") gives false confidence that field selection is handled — but every other property derived from the same pair is equally at risk

**The fix:**
```typescript
// ✅ GOOD: At least one test where the two representations differ
const clippedItem = {
  full: { begin: 0.25, end: 0.5 },   // 250ms event
  clipped: { begin: 0.26, end: 0.28 } // 20ms sliver from a narrow query window
};

test('onset uses full begin even when clipped', () => {
  expect(serialize(clippedItem).onset).toBe(0.25);
});

test('duration uses full extent even when clipped', () => {
  expect(serialize(clippedItem).duration).toBeCloseTo(0.25); // full, not 0.02
});
```

**The rule:** If production code selects between two representations for any property, every property derived from that pair needs its own divergent-fixture test — the coverage must be symmetric across all properties.

### Gate Function

```
WHEN a function reads from two representations of the same data
(e.g. raw/normalized, unclipped/clipped, unbounded/bounded, source/derived):

  BEFORE writing fixtures:
    Ask: "Do my fixtures ever make these two representations differ?"

    IF always equal:
      STOP - Add at least one test where they differ for EVERY property
             the code derives from either representation

    Ask: "Do I have a test for property X that uses the unclipped value?"

    IF yes:
      Verify there is also a test for EVERY OTHER property that confirms
      it too uses the correct representation — don't let one test cover many fields
```

## Anti-Pattern 6: Synthetic Input That Masks a Missing Producer

**The violation:**
```typescript
// ❌ BAD: Test constructs input with 'correlationId' pre-populated.
// The production pipeline is supposed to stamp this field,
// but the test skips the stamping step entirely.
const syntheticMessage = {
  id: 42,
  payload: { value: 'hello' },
  correlationId: 'abc-123', // <- producer should have added this; test hardcodes it
};

test('consumer filters by correlationId', () => {
  const result = consumer.handle(syntheticMessage, 'abc-123');
  expect(result).toBe(true); // ✓ passes — but producer never sets correlationId in prod!
});
```

**Why this is wrong:**
- The test proves the consumer's logic is correct given a properly-stamped message
- It says nothing about whether the upstream producer actually stamps the field
- If the producer is broken and always leaves `correlationId` empty or at its zero value, production silently fails on every message — while the test stays green forever
- This gap is invisible because the happy path was verified, just with inputs the real code path never produces

**The fix:**
```typescript
// ✅ GOOD: Two sibling tests — one for the consumer's contract, one for the producer's

// 1. Consumer contract: synthetic input is fine here — isolates consumer logic
test('consumer filters by correlationId', () => {
  const msg = { id: 42, payload: { value: 'hello' }, correlationId: 'abc-123' };
  expect(consumer.handle(msg, 'abc-123')).toBe(true);
  expect(consumer.handle(msg, 'other')).toBe(false);
});

// 2. Producer contract: exercise the real forwarding path and assert the field is stamped
test('forwarding layer stamps correlationId on outgoing messages', () => {
  const rawInput = { id: 42, payload: { value: 'hello' } }; // no correlationId yet
  const forwarded = forwarder.forward(rawInput, { correlationId: 'abc-123' });
  expect(forwarded.correlationId).toBe('abc-123'); // producer must stamp it
});
```

**The rule:** For every test that constructs synthetic input already containing a field the production pipeline is supposed to populate, add a sibling test that exercises the producer (or the full pipeline end-to-end) and asserts the field is actually populated. The synthetic-input test covers the consumer's contract; the producer test covers the stamping contract. You need both.

### Gate Function

```
WHEN writing a test that constructs synthetic input:
  For each field in the synthetic input:
    Ask: "Is this a field that production code upstream of this test is supposed to set?"

    IF yes:
      STOP - The test is incomplete on its own
      Add a sibling test that:
        1. Exercises the upstream producer (or real pipeline)
        2. Starts with input that does NOT have the field pre-set
        3. Asserts the field is set correctly after the producer runs

  The synthetic-input test and the producer test are complementary — delete neither.
```

## Anti-Pattern 7: Existence-Only Assertion When Correctness Is Checkable

**The violation:**
```typescript
// ❌ BAD: Asserts only that something came out — not what came out
test('pipeline produces output', () => {
  const result = pipeline.process(input);
  expect(result.events.length).toBeGreaterThan(0); // ✓ passes — but is the value right?
});

test('handler emits event', () => {
  handler.run(request);
  expect(emitter.emit).toHaveBeenCalled(); // ✓ passes — but with what payload?
});
```

**Why this is wrong:**
- The test proves the pipeline ran but says nothing about whether it ran correctly
- Bugs in the output value (wrong amount, wrong timing, wrong shape, wrong field) survive every passing run
- A pure-function analyzer for the property often already exists — the test just didn't use it
- Existence assertions give false confidence: green CI while the value is silently wrong

**The fix:**
```typescript
// ✅ GOOD: Render → analyze → assert the specific derived value

// Helper (write once, reuse across the regression matrix):
function extractAmount(events: OutputEvent[]): number {
  return events.reduce((sum, e) => sum + e.value.amount, 0);
}

test('pipeline computes correct total', () => {
  const result = pipeline.process(input);
  expect(result.events.length).toBeGreaterThan(0);  // existence still fine as a guard
  expect(extractAmount(result.events)).toBeCloseTo(expectedAmount, 2); // ← correctness
});

test('handler emits event with correct payload', () => {
  handler.run(request);
  expect(emitter.emit).toHaveBeenCalledWith(
    'change',
    expect.objectContaining({ value: { amount: 42, currency: 'USD' } })
  );
});
```

**The rule:** For any pipeline whose output can be analytically characterized (numeric properties, derived statistics, structural invariants, parsed re-representations), at least one test must assert the specific derived value — not just that *some* output exists. If a pure-function analyzer for that property doesn't exist, write one as a sibling helper. The cost of "run → analyze → assert" is one helper module; the cost of weak existence assertions is bugs that ship to manual testing.

### Gate Function

```
WHEN writing a test for a pipeline, handler, or transformation:
  For each assertion of the form "output is non-empty" or "function was called":
    Ask: "Can I analytically characterize what the correct output value should be?"

    IF yes:
      STOP — add at least one assertion on the derived value, not just existence
      If no analyzer helper exists: write one as a sibling utility

    Ask: "Is there a pure function already available that extracts/validates this property?"

    IF yes:
      Use it — skipping it is the anti-pattern

  Red flags:
    - Every assertion is .length > 0, .toHaveBeenCalled(), or .toBeDefined()
    - Test suite is entirely green but a wrong value in the output would not fail any test
    - "We'll catch value bugs in manual testing / QA"
```

## Anti-Pattern 8: Integration Tests as Afterthought

**The violation:**
```
✅ Implementation complete
❌ No tests written
"Ready for testing"
```

**Why this is wrong:**
- Testing is part of implementation, not optional follow-up
- TDD would have caught this
- Can't claim complete without tests

**The fix:**
```
TDD cycle:
1. Write failing test
2. Implement to pass
3. Refactor
4. THEN claim complete
```

## When Mocks Become Too Complex

**Warning signs:**
- Mock setup longer than test logic
- Mocking everything to make test pass
- Mocks missing methods real components have
- Test breaks when mock changes

**your human partner's question:** "Do we need to be using a mock here?"

**Consider:** Integration tests with real components often simpler than complex mocks

## TDD Prevents These Anti-Patterns

**Why TDD helps:**
1. **Write test first** → Forces you to think about what you're actually testing
2. **Watch it fail** → Confirms test tests real behavior, not mocks
3. **Minimal implementation** → No test-only methods creep in
4. **Real dependencies** → You see what the test actually needs before mocking

**If you're testing mock behavior, you violated TDD** - you added mocks without watching test fail against real code first.

## Quick Reference

| Anti-Pattern | Fix |
|--------------|-----|
| Assert on mock elements | Test real component or unmock it |
| Test-only methods in production | Move to test utilities |
| Mock without understanding | Understand dependencies first, mock minimally |
| Incomplete mocks | Mirror real API completely |
| Homogeneous fixtures for divergent representations | Add at least one test where both representations differ, for every derived property |
| Synthetic input masks missing producer | Add a sibling producer test that starts without the field and asserts it is stamped |
| Existence-only assertion when correctness is checkable | Assert the specific derived value; write an analyzer helper if one doesn't exist |
| Tests as afterthought | TDD - tests first |
| Over-complex mocks | Consider integration tests |

## Red Flags

- Assertion checks for `*-mock` test IDs
- Methods only called in test files
- Mock setup is >50% of test
- Test fails when you remove mock
- Can't explain why mock is needed
- Mocking "just to be safe"
- Every fixture for a function with two representations of the same data sets them to identical values
- One "correct field selection" test covers property X but no sibling test covers property Y derived from the same pair
- Synthetic input pre-populates a field that the production pipeline is supposed to stamp, with no sibling test verifying the producer actually stamps it
- Every assertion in a pipeline test is `.length > 0`, `.toHaveBeenCalled()`, or `.toBeDefined()` — no test asserts the actual value
- A pure-function analyzer for the output property exists but no test uses it
- "Value correctness will be caught in manual testing / QA"

## The Bottom Line

**Mocks are tools to isolate, not things to test.**

If TDD reveals you're testing mock behavior, you've gone wrong.

Fix: Test real behavior or question why you're mocking at all.
