# Initial Sync Expected Behavior

## Overview

Initial sync is a **one-time** operation that runs when a linked lookup field is first saved on a form. It synchronizes `SOURCE` form entries to match the current state of `TARGET` form entries, ensuring both sides of the relationship start in sync.

## Core Principles

1.  **`SOURCE` Entries are Updated**
    * Initial sync **only modifies** `SOURCE` entries (the form where the newly linked field was added).
    * `SOURCE` entry values are **overridden** to match what `TARGET` entries reference.
    * This is a **one-way sync**: `SOURCE` &larr; `TARGET`.

2.  **`TARGET` Entries are Never Modified**
    * `TARGET` entries remain completely **unchanged**.
    * No modifications, no audit records.
    * `TARGET` entries are used as the "**source of truth**" for what `SOURCE` entries should reference.

3.  **Audit Records Created Only for Changes**
    * Audit records are created **only on `SOURCE` entries that change**.
    * If a `SOURCE` entry **already matches** the `TARGET` value, no audit record is created.
    * Audit action name includes *"Initial Sync"* to distinguish from regular syncs.

4.  **Special Behavior**
    * Does not enforce process/entry sync operation limits.
    * Does not run default values or rerun calculations.
    * Does enforce the 100-entry selection limit (`SYNCED_ENTRIES_LIMIT`).
    * Handles conflicts when multiple `TARGET` entries reference the same `SOURCE` entry (keeps most recent).

---

## Example Scenario: Alice & Bob

### Setup

**Forms:**
* `Camper` form with `CampPrograms` field (multi-select lookup &rarr; `CampProgram`)
* `CampProgram` form with `RegisteredCampers` field (multi-select lookup &rarr; `Camper`)

The form builder decides to link `Camper.CampPrograms` &harr; `CampProgram.RegisteredCampers`.

### Before Initial Sync

**`SOURCE` entries (`Camper`s):**
* `Alice`: `CampPrograms` = `[Archery]`
* `Bob`: `CampPrograms` = `[Swimming]`

**`TARGET` entries (`CampProgram`s):**
* `Archery`: `RegisteredCampers` = `[Alice, Bob]`
* `Swimming`: `RegisteredCampers` = `[]`

### After Initial Sync (performed on `Camper` form)

**`SOURCE` entries (`Camper`s) - UPDATED:**
* `Alice`: `CampPrograms` = `[Archery]` ✅ No change (already matched) &rarr; 0 audit records
* `Bob`: `CampPrograms` = `[Archery]` ✅ Changed from `[Swimming]` &rarr; 1 audit record
    * Audit: `"Update CampPrograms via CampProgram (Initial Sync)"`

**`TARGET` entries (`CampProgram`s) - UNCHANGED:**
* `Archery`: `RegisteredCampers` = `[Alice, Bob]` ✅ No change &rarr; 0 audit records
* `Swimming`: `RegisteredCampers` = `[]` ✅ No change &rarr; 0 audit records

---

## Key Takeaways

1.  `SOURCE` = the form being synced (where the newly linked field was added).
2.  `TARGET` = the form being referenced (the **source of truth** for the sync).
3.  Audit records **only on `SOURCE` entries that change**.
4.  `TARGET` entries are **completely untouched**.
5.  Initial sync is a **one-time "catch-up" operation** to establish consistency.

This ensures that when you link two existing forms with data, the form you're working on (`SOURCE`) gets updated to reflect the current state of the other form (`TARGET`), without disrupting any existing data on the `TARGET` side.