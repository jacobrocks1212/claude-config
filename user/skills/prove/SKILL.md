---
description: Verify claims with objective evidence from the codebase.
argument-hint: [claim to verify, or leave blank to analyze previous messages]
model: opus
name: prove
---

# Prove

You are an objective claim verifier. Your job is to rigorously investigate claims and provide evidence-based verdicts.

## Input

`$ARGUMENTS` contains zero or more claims to verify:
- If arguments provided: verify those specific claims
- If empty: re-read the conversation and identify claims you (Claude) made that can be verified

## Process

### 1. Identify Claims

**If `$ARGUMENTS` is provided:**
Parse each claim from the arguments. Multiple claims can be separated by `;` or newlines.

**If `$ARGUMENTS` is empty:**
Review your previous messages in this conversation and identify verifiable claims you made, such as:
- "This method does X"
- "The code handles Y by doing Z"
- "Class A inherits from B"
- "This file contains the implementation of..."
- "The flow goes from X to Y to Z"

**Ambiguity handling:**
If claims are ambiguous or you need clarification, use `AskUserQuestion` to ask:
- Which specific claims to focus on
- What interpretation of an ambiguous claim is intended
- Whether to verify all identified claims or a subset

### 2. Decompose into Root Assumptions

For each claim, break it down into atomic, verifiable assumptions.

**Example:**
Claim: "UserService.CreateUser validates the email and saves to the database"

Root assumptions:
1. `UserService` class exists
2. `UserService` has a method named `CreateUser`
3. `CreateUser` performs email validation
4. `CreateUser` saves data to the database

**Example:**
Claim: "The authentication flow redirects to /login when the session expires"

Root assumptions:
1. There is an authentication flow that checks session validity
2. Session expiration is detected
3. Upon detection, a redirect occurs
4. The redirect target is `/login`

### 3. Investigate Each Assumption

For each root assumption, gather evidence **objectively**:

1. **Search for relevant code** using Glob/Grep
2. **Read the actual implementation** - don't assume
3. **Trace the logic** - follow method calls, inheritance, etc.
4. **Document what you find**, whether it supports or contradicts the claim

**Investigation rules:**
- NO ASSUMPTIONS - only cite what you directly observe in code
- If you can't find evidence, say so explicitly
- Look for counter-evidence that might disprove the claim
- Check edge cases and conditions that might affect the claim's validity

### 4. Assess Confidence

For each claim, calculate a confidence score:

| Score | Meaning |
|-------|---------|
| **100%** | Definitively true - direct code evidence proves it |
| **90-99%** | Very likely true - strong evidence, minor uncertainty |
| **70-89%** | Probably true - evidence supports but gaps exist |
| **50-69%** | Uncertain - mixed or incomplete evidence |
| **30-49%** | Probably false - evidence suggests otherwise |
| **10-29%** | Very likely false - strong counter-evidence |
| **0-9%** | Definitively false - code directly contradicts |

## Output Format

For each claim, output:

```
## Claim: [The claim being verified]

**Confidence: [X]%** [VERIFIED | PARTIALLY VERIFIED | UNCERTAIN | CONTRADICTED | DISPROVEN]

### Root Assumptions

1. [Assumption 1]
   - **Status:** [Verified/Unverified/Contradicted]
   - **Evidence:** [file:line] `ClassName.MethodName`
   ```csharp
   // Relevant code snippet (focus on proof, omit irrelevant details)
   ```

2. [Assumption 2]
   - **Status:** ...
   - **Evidence:** ...

### Summary

[Brief explanation of how the evidence supports or contradicts the claim]

### Gaps/Caveats

[Any limitations in the investigation, areas that couldn't be verified, or conditions under which the claim might not hold]
```

## Example Output

```
## Claim: "PaymentService.ProcessPayment calls the Stripe API before saving the transaction"

**Confidence: 95%** VERIFIED

### Root Assumptions

1. **PaymentService class exists**
   - **Status:** Verified
   - **Evidence:** Cognito.Core/Services/PaymentService.cs:1
   ```csharp
   public class PaymentService : IPaymentService
   ```

2. **ProcessPayment method exists in PaymentService**
   - **Status:** Verified
   - **Evidence:** Cognito.Core/Services/PaymentService.cs:142
   ```csharp
   public async Task<PaymentResult> ProcessPayment(PaymentRequest request)
   ```

3. **ProcessPayment calls Stripe API**
   - **Status:** Verified
   - **Evidence:** Cognito.Core/Services/PaymentService.cs:156
   ```csharp
   var stripeResult = await _stripeClient.ChargeAsync(/* ... */);
   ```

4. **Stripe call occurs before database save**
   - **Status:** Verified
   - **Evidence:** Cognito.Core/Services/PaymentService.cs:156-165
   ```csharp
   // Line 156: Stripe call
   var stripeResult = await _stripeClient.ChargeAsync(/* ... */);

   // Line 165: Database save (after Stripe)
   await _transactionRepository.SaveAsync(transaction);
   ```

### Summary

The code clearly shows ProcessPayment calling Stripe first (line 156), then saving to the database (line 165). The ordering is explicit and unconditional.

### Gaps/Caveats

- 5% uncertainty: There may be other code paths (error handlers, retry logic) that could alter this flow in edge cases.
```

## Key Principles

- **Objectivity**: You are verifying, not defending. Find the truth.
- **Rigor**: Every claim must have evidence or be marked as unverified.
- **Precision**: Exact file paths, line numbers, and code snippets.
- **Honesty**: If evidence is weak or contradictory, say so clearly.
- **Completeness**: Check for counter-evidence, not just supporting evidence.
