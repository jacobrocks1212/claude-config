---
name: atomic-thinking
description: Invoke Aristotelian first-principles reasoning. Before proceeding with the task, decompose every undefined or load-bearing term down to its atomic meaning, then reason up from those primitives instead of from analogies, conventions, or borrowed framings.
---

# Atomic Thinking — Aristotelian First Principles

When this skill is invoked, switch into first-principles mode for the request that follows (or the request already on the table). Do not proceed to a solution, recommendation, or implementation until the decomposition step is complete.

## The Policy

> Use Aristotelian first principles reasoning. Before you proceed, break every undefined term down to its atomic meaning.

A term is **atomic** when it cannot be further reduced without losing the thing being talked about — when the next step down would replace meaning with mechanism, or fact with metaphor. Stop there. Do not stop earlier.

## Procedure

1. **Identify load-bearing terms.** Read the request and underline (mentally) every noun, verb, and adjective that the eventual answer hinges on. Names of systems, abstractions, goals ("simpler", "better", "faster", "secure", "user-friendly"), and any jargon count.

2. **Test each term.** For each one, ask:
   - What does this *actually* refer to in the world (or in this codebase)?
   - Is my current definition borrowed from convention, analogy, or another domain?
   - If I replaced the word with its definition, would the sentence still make sense — and would it still describe the user's real problem?

3. **Decompose until atomic.** If a term resolves into other vague terms, recurse. Stop when each constituent is either:
   - A concrete observable (a file, a function, a metric, a user action, a measurable property), or
   - A primitive the user and I already share without ambiguity.

4. **Reconstruct.** Restate the request — or the proposed answer — using only the atomic terms. If the reconstruction reveals the original framing was confused, ambiguous, or smuggling assumptions, surface that before going further.

5. **Then reason forward.** Only after the ground is firm do you derive the answer from the primitives. Do not import conclusions from analogy ("this is like X, so do Y") unless the analogy survives the decomposition.

## Output Shape

Make the decomposition visible to the user. A compact form works:

```
Terms in play:
- <term> → <atomic definition>
- <term> → <atomic definition>
...

Reconstructed question: <restate the request using only atomic terms>

Answer: <reason forward from there>
```

Keep the decomposition tight — one line per term, no padding. If a term turns out to be unambiguous on inspection, you can say so and move on; the point is to *check*, not to perform.

## When to Skip a Term

Don't decompose terms that are already concrete and shared (e.g., "the `Button` component in `src/ui/Button.tsx`"). The skill targets *undefined* and *load-bearing* terms, not every word. If decomposition would be theater, skip it and say why.

## Anti-Patterns

- **Stopping at the dictionary.** "Secure means safe from threats" is not atomic. What threats, what assets, what adversary, what observable property would change if security failed?
- **Decomposing into more jargon.** If "scalable" resolves to "horizontally elastic", you haven't moved — keep going until you reach load, latency, cost, or some other measurable.
- **Decomposing the wrong terms.** The atomic terms are the ones the *answer* depends on. Don't waste effort defining incidental words.
- **Skipping straight to the answer with a token nod to first principles.** The decomposition is the work. If you didn't change your understanding by doing it, you didn't do it.
