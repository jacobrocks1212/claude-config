# The Indexing Process

The indexing system uses two distinct processes to keep the search index up-to-date: a real-time process for data changes and a background process for structural changes.

## 1. Real-Time Indexing (On Entry Submission)

This process handles the immediate indexing of new or updated entries as they are submitted.

-   **Trigger**: This process is triggered within the `FormsService.SubmitEntry` method, immediately after an entry has been successfully saved to the primary database.
-   **Method**: `SubmitEntry` calls `EntryIndexService.UpdateLookups(oldForm, form)`.
-   **Action**: The `UpdateLookups` method performs a targeted update. It identifies the submitted entry and any other entries that were affected by linked lookup updates and sends just those specific entries to the `IndexRepository` to be updated in the index. This ensures that new data is searchable almost instantly.

## 2. Invalidation and Background Rebuilding (On Form Change)

This process handles situations where a change to a form's structure makes the existing index for all of its entries incorrect.

-   **Trigger**: This process is triggered by any action that modifies the fields or structure of a form, most commonly `FormsService.SaveForm`.
-   **Step 1: Invalidation**: The `SaveForm` method calls `EntryIndexService.InvalidateIndex(form, true)`. This does not delete the index data itself, but rather marks it as stale, often by updating a version or hash associated with the index for that form.
-   **Step 2: Rebuild Trigger**: Immediately after invalidating the index, the code calls `EntryIndexService.TryStartIndexBuild(form, ...)`.
-   **Step 3: Background Task**: The `TryStartIndexBuild` method queues a background job (via the `Cognito.QueueJob` system). This job will, at a later time, find all entries for the invalidated form, run them through the `IndexBuilder`, and overwrite the old index data with the new, correctly structured documents. This ensures that large re-indexing operations do not block the user or the web server.

## 3. Deletion

-   **Trigger**: When a form is deleted, the `FormsService.DeleteForm` method is called.
-   **Action**: This method calls `EntryIndexService.OnDeleteForm(formRef)`. This service is responsible for sending commands to the `IndexRepository` to delete all documents from the index that are associated with the deleted form.

## Summary of Lifecycle

| Action | Triggering Method | Indexing Method | Description |
| :--- | :--- | :--- | :--- |
| **Entry Submitted/Updated** | `FormsService.SubmitEntry` | `UpdateLookups` | A real-time, targeted update for only the affected entries. |
| **Form Structure Changed** | `FormsService.SaveForm` | `InvalidateIndex` then `TryStartIndexBuild` | The index is marked as stale, and a background job is queued to rebuild it entirely. |
| **Form Deleted** | `FormsService.DeleteForm` | `OnDeleteForm` | All documents related to the form are permanently removed from the index. |
