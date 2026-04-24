# Linked Lookup Checkbox Doesn't Appear Without Page Refresh

## Issue Summary

**Reported:** 2026-02-17
**Branch:** `p/ll-no-refresh`
**Status:** Fixed (2026-02-18)

When configuring a lookup field that has valid linkable fields on the target form, the "Link with another field" checkbox doesn't appear until the page is refreshed.

## Root Cause

`raiseChanged()` only notifies dependents that a property changed — it does NOT invalidate the cached calculated value. So `allLinkableFields` would return a stale empty array even after the API response populated the `fields` list.

## Solution

The fix uses direct `onChangeOf: ['fields']` on the `allLinkableFields` calculated property, so it properly recalculates when the fields list is populated.

**File:** `Cognito.Web.Client/apps/spa/src/composables/linked-lookup.ts`

## Key Insight

In ExoModel, `raiseChanged()` only notifies listeners — it does NOT invalidate cached calculated values. To force recalculation, you need to change an actual dependency tracked via `onChangeOf`.
