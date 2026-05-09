## Example Output

From beat-highlighting spec (`docs/features/beat-highlighting/PHASES.md`):

```markdown
# Implementation Phases — Beat Highlighting

> Phases for [`SPEC.md`](./SPEC.md)

### Phase 1: Sidecar Source Location Extraction

**Scope:** Extend sidecar to include source location metadata in hap serialization.

**Deliverables:**
- [ ] Extended `SerializedHap` with `location?: { start: number; end: number }`
- [ ] Updated transpiler configuration to emit mini locations
- [ ] Unit tests for location extraction (various patterns)

**Prerequisites:** None

**Files likely modified:**
- `strudel-sidecar/src/StrudelRuntime.ts` - Add transpiler options
- `strudel-sidecar/src/CyclistBridge.ts` - Extract location during serialization
- `src/core/abstractions/types.ts` - Extend SerializedHap type

**Testing Strategy:**
Test sidecar in isolation via JSON-IPC protocol. Verify various pattern types emit correct offsets.

**Integration Notes for Next Phase:**
- Transpiler must be passed as 2nd arg to `evaluate()`, options as 3rd
- `context.locations` is an array; use `[0]` for innermost location
- Pure patterns (`pure(x)`) have no location - this is expected
```
