## Example Output

From a feature spec (`docs/features/user-notifications/PHASES.md`):

```markdown
# Implementation Phases — User Notifications

> Phases for [`SPEC.md`](./SPEC.md)

### Phase 1: Notification Data Model

**Scope:** Define the notification entity and persistence layer.

**Deliverables:**
- [ ] Notification model with type, message, recipient, read status
- [ ] Repository interface and implementation
- [ ] Unit tests for CRUD operations

**Prerequisites:** None

**Files likely modified:**
- `src/models/Notification.ts` - Define notification entity
- `src/repositories/NotificationRepository.ts` - Implement persistence
- `tests/notification.test.ts` - Unit tests

**Testing Strategy:**
Test repository in isolation with mock storage. Verify CRUD operations and query filters.

**Integration Notes for Next Phase:**
- Repository returns DTOs, not raw storage objects
- Read status is per-user, not global
- Soft delete via `deletedAt` timestamp — query filters must exclude these
```
