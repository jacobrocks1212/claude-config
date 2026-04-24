# Linked Lookup Card Image Bug

## PR Summary

**Bug Title:** Lookup card avatars don't render for entries synced via linked lookups

**Repro Steps:**
- Create two forms (Form A and Form B) with a linked lookup relationship
- Configure Form B with a lookup field displayed as cards with avatars enabled
- Submit an entry on Form A that triggers a linked lookup sync to Form B
- Open the synced entry on Form B
- Observe that the avatar/icon for the synced lookup value is missing

**Additional Info:**
- Avatars render correctly when selecting entries directly from the dropdown
- Only affects entries added via linked lookup sync (server-side)
- Also affects entries that are filtered out of the entry set but remain selected
- Root cause: synthetic indexes (created for selected entries not in entry set) were missing `AdditionalValues` containing image data

**Implementation:**
- Server now sends image configuration paths (`imageFieldPath`, `nameFieldPath`, `emailFieldPath`) in `$lookupFieldInfo` metadata
- Client computes image values when creating synthetic indexes, matching server-side logic
- Supports both file uploads (`F-{fileId}`) and person field avatars (`{initials}|{hash}`)
- Modified files: `lookup-manager.ts`, `ModelBuilder.cs`, `Lookup.unit.ts`

**Expected Outcome:**
- Avatars render correctly for all lookup card entries, including those synced via linked lookups
- File upload images display the uploaded image thumbnail
- Person field lookups display initials avatar with correct colors (matching direct selection behavior)
- No visual difference between directly selected entries and linked-lookup-synced entries

---

## Issue Summary

**Reported:** 2026-02-17 by Nicholas Gasque
**Branch:** `p/ll-card-image`
**Status:** Implemented

When a lookup field displayed as cards is updated via linked lookup sync, the avatar/icon images are not properly refreshed. Some icons disappear, others appear incorrectly.

### Reproduction Scenario

1. Entry 4 has a "Currently Assigned to" lookup field displayed as cards with avatars
2. The field was updated via linked lookup sync (not direct user interaction)
3. **Before update:** Jim was selected but had NO "JJ" icon. Steve was unselected but had yellow "SS" icon visible
4. **After update:** Steve was selected and entry saved. The "JJ" icon for Jim appeared, and the "SS" icon disappeared

---

## Root Cause

When synthetic indexes are created for missing entries (entries selected but not in the current entry set), they were created **without `AdditionalValues`**, which contains the Image data needed for avatar rendering.

**Location:** `apps/client/src/framework/model/extensions/lookup-field/lookup-manager.ts`

Synthetic indexes are created when:
- An entry is selected in the lookup field
- BUT the entry is NOT in the entry set (filtered out, permissions, linked lookup sync)

---

## Decision

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-02-17 | Investigation complete | Root cause identified in synthetic index creation |
| 2026-02-17 | Deep investigation of 5 options | Analyzed feasibility, implementation details, and tradeoffs |
| 2026-02-17 | **Selected Option 1** | 100% coverage, follows existing patterns (summaryFormat/descriptionFormat), reuses existing avatar utilities |

### Why Option 1?

- **100% coverage** - Works for all scenarios including server-side sync before page load
- **Clear precedent** - Follows same pattern as `summaryFormat`/`descriptionFormat` props
- **Reuses existing code** - `hashAvatarSeed()` in `@cognitoforms/utils/avatar` matches server's DJB2 hash
- **No API calls** - Computes image value client-side from entry data already available

---

## Implementation

### Image Configuration (Server to Client)

The server now sends three paths in `$lookupFieldInfo` metadata:

| Path | Purpose |
|------|---------|
| `imageFieldPath` | Primary image field (file upload or person name field) |
| `nameFieldPath` | Name field for extracting initials (person fields) |
| `emailFieldPath` | Email field for computing avatar hash seed |

### Image Value Formats

- **File uploads:** `"F-{fileId}"` (e.g., `"F-12345678"`)
- **Person/Name fields:** `"{initials}|{emailHash}"` (e.g., `"JD|42839"`)

### Files Modified

#### Client-Side

**`apps/client/src/framework/model/extensions/lookup-field/lookup-manager.ts`**

1. **Updated `LookupIndexInfo` type** - Added optional properties:
   ```typescript
   imageFieldPath?: string;
   nameFieldPath?: string;
   emailFieldPath?: string;
   ```

2. **Added props to `LookupManager` class**:
   ```typescript
   @Prop() imageFieldPath: string;
   @Prop() nameFieldPath: string;
   @Prop() emailFieldPath: string;
   ```

3. **Updated synthetic index creation** - Now includes `AdditionalValues` with computed image:
   ```typescript
   const imageValue = this.computeImageValue(entry);
   const syntheticIndex = getIndex(this.entryViewService.model, this.indexType, {
       Id: `${this.entrySet.view}|fake|${entry.Id}`,
       Summary: entry.toString(this.summaryFormat),
       Description: this.descriptionFormat ? '- ' + entry.toString(this.descriptionFormat) : '',
       AdditionalValues: imageValue ? [{ FieldId: 'Image', Value: imageValue }] : undefined
   } as any);
   ```

4. **Added `computeImageValue()` method** - Computes image value matching server logic:
   - Checks for file uploads (`F-` prefix)
   - For person fields, extracts initials using `extractInitials()` and computes hash using `hashAvatarSeed()`

5. **Added `extractInitials()` method** - Matches server-side `IndexBuilder.GetImageFallback()`:
   - Filters `|` character from first name initial
   - Filters `-` and `|` characters from last name initial (prevents `F-` prefix collision)

6. **Updated `getLookupManager()` factory** - Wires new props from `lookupInfo`

#### Server-Side

**`Cognito.Services/Infrastructure/Vue/ModelBuilder.cs`**

Added image configuration computation before `$lookupFieldInfo` metadata:

```csharp
// Compute image configuration paths for synthetic index avatar rendering
string imageFieldPath = null;
string nameFieldPath = null;
string emailFieldPath = null;

if (field.Lookup.HasImage)
{
    var lookupView = formsService.GetLookupView(field.Lookup);
    if (lookupView != null)
    {
        var lookupSourceForm = formsService.GetForm(lookupView.SourceForm.Id);
        var peopleSettings = lookupSourceForm?.PeopleFormSettings;

        if (peopleSettings != null && lookupView.MatchesPersonField(peopleSettings))
        {
            // Person field lookup - use people form settings for avatar
            imageFieldPath = peopleSettings.Avatar ?? peopleSettings.Name;
            nameFieldPath = peopleSettings.Name;
            emailFieldPath = peopleSettings.Email;
        }
        else if (!string.IsNullOrEmpty(field.Lookup.ChoiceImage))
        {
            // Custom image field configured
            imageFieldPath = field.Lookup.ChoiceImage;
            nameFieldPath = field.Lookup.ChoiceImage;
        }
    }
}
```

Added to `$lookupFieldInfo` anonymous object:
```csharp
imageFieldPath,
nameFieldPath,
emailFieldPath
```

#### Tests

**`apps/client/test/unit/fields/Lookup.unit.ts`**

Added two new tests:
1. **File image test** - Verifies synthetic indexes include `AdditionalValues` with file image (`F-xxx`)
2. **Initials avatar test** - Verifies synthetic indexes compute initials+hash for person fields

---

## Verification

### Manual Testing

1. Create form with Person lookup field displayed as cards (with image configured)
2. Set up linked lookup between two forms
3. Submit entry on Form A that triggers linked lookup sync to Form B
4. Open Form B entry - verify avatar renders for the synced lookup value
5. Test scenarios:
   - File upload image (should show image)
   - Person field with full name (should show initials avatar)
   - Person field with partial name (should show single initial)
   - Person field with special characters in name

### Regression Check

- Existing lookup tests still pass
- Non-synthetic indexes still render avatars correctly
- Lookups without image configured still work
- Card display without image configured still work

---

## Related Files

### Client-Side
- `apps/client/src/framework/model/extensions/lookup-field/lookup-manager.ts` - Synthetic index creation, image computation
- `apps/client/src/components/Lookup.ts` - Avatar rendering from `AdditionalValues`
- `libs/utils/avatar.ts` - `hashAvatarSeed()` function (DJB2 hash matching server)

### Server-Side
- `Cognito.Services/Infrastructure/Vue/ModelBuilder.cs` - `$lookupFieldInfo` metadata with image paths
- `Cognito.Core/Helpers/IndexBuilder.cs` - Server-side `GetImageFallback()` (reference for client implementation)
- `Cognito.Core/Model/Forms/PeopleFormSettings.cs` - Person field configuration
- `Cognito.Core/Model/Forms/LookupView.cs` - `ChoiceImageId`, `HasImage`, `MatchesPersonField()`

### Tests
- `apps/client/test/unit/fields/Lookup.unit.ts` - Lookup component tests including synthetic index image tests

---

## Alternative Options Considered

| Option | Coverage | Effort | Why Not Selected |
|--------|----------|--------|------------------|
| **2: Pooled index lookup** | 70-95% | 2-4 hours | Doesn't cover server-side sync before page load |
| **3: Cache AdditionalValues** | 75-85% | 2-3 days | Fails for entries never in the set |
| **4: Fetch from server** | ~100% | 2-3 days | Extra API round-trip, UX flicker |
| **5: Server entry data** | ~100% | 1-2 days | Mixes presentation with data serialization |
