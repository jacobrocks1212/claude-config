# PR Review — previous iteration output (fixture)

This fixture stands in for a prior review's rendered markdown. It carries an
INFLATED, self-referential lifespan marker to exercise the RC-1b feedback-loop
guard: the scrape must NOT read these emitted `raised_in:` / `total_iterations:`
numbers back into a new lifespan. The `## Iteration 3` round header is the only
legitimate iteration signal (a structural review-round header, h2 so it is not
mis-read as a finding title).

## Iteration 3

## Blocking Findings

### Missing null guard in public method

**File:** `A.cs:5`

Callers can pass a null reference causing an NRE.

- lifespan: { "raised_in": 777, "total_iterations": 778 }

### Duplicates existing OrganizationHelper.Validate

**File:** `B.cs:20`

Logic duplicates an existing well-tested helper.

- lifespan: raised_in: 777, total_iterations: 778
