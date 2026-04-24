# Indexing System Architecture

The entry indexing system provides a fast, queryable data store for form entries, separate from the primary database. It is designed to power the search, filtering, and sorting capabilities of the Entries page. The architecture is built on Azure Cosmos DB and is orchestrated by a dedicated service.

## 1. Core Components

-   **`IEntryIndexService` (`EntryIndexService.cs`)**: This is the central orchestrator for all indexing operations. It provides a high-level API for adding, updating, and deleting entries from the index, as well as managing the index's lifecycle (e.g., invalidation and rebuilding). It is consumed by `FormsService` and the `ODataController`.

-   **`IIndexRepository` (`IndexRepository.cs`)**: This is the data access layer for the indexing system. It abstracts the direct communication with the underlying Azure Cosmos DB container. Its methods (`Query`, `TransactedUpdates`, etc.) are responsible for constructing and executing SQL-like queries against Cosmos DB and performing batch operations.

-   **`IndexBuilder.cs`**: This helper class is responsible for transforming a `FormEntry` object into a denormalized `CompositeEntryIndex` document suitable for indexing. It takes the complex, nested data of a form entry and flattens it into a structure that can be easily queried.

-   **`ODataController.cs`**: This API controller serves as the primary query endpoint for the Entries page. It receives OData-style web requests (e.g., with `$filter`, `$orderby` query parameters), translates them into a query specification, and uses `IEntryIndexService` to retrieve the data.

## 2. High-Level Data Flow

1.  **Data Source**: The primary source of truth is the main application database where `FormEntry` entities are stored.

2.  **Indexing Trigger**: When an entry is created/updated (`FormsService.SubmitEntry`) or a form's structure is changed (`FormsService.SaveForm`), an event is triggered.

3.  **Orchestration**: `EntryIndexService` handles this event. It determines what action needs to be taken (e.g., update a single entry, or rebuild the entire index for a form).

4.  **Document Creation**: `IndexBuilder` is used to create the `CompositeEntryIndex` document that will be sent to Cosmos DB.

5.  **Data Persistence**: `IndexRepository` takes the index document and performs the necessary CRUD operation against the Cosmos DB container.

6.  **Querying**: The Entries page UI makes a request to the `ODataController`. The controller parses the OData query, calls `EntryIndexService` to fetch the data, and the service uses `IndexRepository` to execute the efficient query against Cosmos DB, returning the results without hitting the primary transactional database.
