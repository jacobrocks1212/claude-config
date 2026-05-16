## Atomic Thinking — Aristotelian First Principles

> Use Aristotelian first principles reasoning. Before you proceed, break every undefined term down to its atomic meaning.

A term is **atomic** when it cannot be further reduced without losing the thing being talked about — when the next step down would replace meaning with mechanism, or fact with metaphor. Stop there. Do not stop earlier.

### Procedure

1. **Identify load-bearing terms.** Read the request and underline (mentally) every noun, verb, and adjective that the eventual answer hinges on. Names of systems, abstractions, goals ("simpler", "better", "faster", "secure", "user-friendly", "robust", "scalable"), and any jargon count.

2. **Test each term.** For each one, ask:
   - What does this *actually* refer to in the world (or in this codebase)?
   - Is my current definition borrowed from convention, analogy, or another domain?
   - If I replaced the word with its definition, would the sentence still make sense — and would it still describe the user's real problem?

3. **Decompose until atomic.** If a term resolves into other vague terms, recurse. Stop when each constituent is either:
   - A concrete observable (a file, a function, a metric, a user action, a measurable property), or
   - A primitive the user and I already share without ambiguity.

4. **Reconstruct.** Restate the request — or the proposed answer — using only the atomic terms. If the reconstruction reveals the original framing was confused, ambiguous, or smuggling assumptions, surface that before going further.

5. **Then reason forward.** Only after the ground is firm do you derive the answer from the primitives. Do not import conclusions from analogy ("this is like X, so do Y") unless the analogy survives the decomposition.

### Output Shape

Make the decomposition visible. A compact form works:

```
Terms in play:
- <term> → <atomic definition>
- <term> → <atomic definition>
...

Reconstructed question: <restate using only atomic terms>
```

Keep it tight — one line per term, no padding. If a term turns out to be unambiguous on inspection, say so and move on; the point is to *check*, not to perform.

### When to Skip a Term

Don't decompose terms that are already concrete and shared (e.g., "the `Button` component in `src/ui/Button.tsx`"). This targets *undefined* and *load-bearing* terms, not every word. If decomposition would be theater, skip it and say why.

### Anti-Patterns

- **Stopping at the dictionary.** "Secure means safe from threats" is not atomic. What threats, what assets, what adversary, what observable property would change if security failed?
- **Decomposing into more jargon.** If "scalable" resolves to "horizontally elastic", you haven't moved — keep going until you reach load, latency, cost, or some other measurable.
- **Decomposing the wrong terms.** The atomic terms are the ones the *answer* depends on. Don't waste effort defining incidental words.
- **Token nod, then skip to the answer.** The decomposition is the work. If you didn't change your understanding by doing it, you didn't do it.
