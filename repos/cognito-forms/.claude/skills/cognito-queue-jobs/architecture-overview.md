# Queue System Architecture

The Cognito Forms queueing system is a .NET-based worker process built on the Azure WebJobs SDK. It is designed to handle asynchronous background tasks reliably. The architecture consists of three main conceptual parts.

## 1. The Producer (Any Application Service)

There is no single "enqueuer" service. Any part of the main application can act as a job producer. The process is:

1.  An application service (e.g., in `Cognito.Services`) needs to perform a long-running task.
2.  It instantiates a job-specific C# object (the job's data contract).
3.  This object is wrapped in a `QueueMessageEnvelope`, serialized to JSON, and sent as a message to a specific Azure Storage Queue.

## 2. The Queues (Azure Storage Queues)

The system uses multiple Azure Storage Queues to segregate different types of work. The primary queues identified in the code are:

-   `default-queue`: For general background tasks.
-   `scheduled-queue`: For jobs that need to run at a specific time.
-   `webhooks-queue`: For processing outgoing webhooks.
-   `emails-queue`: For sending emails.
-   `document-compare-queue`: For document processing tasks.

Each queue can also have an associated `-delayed` and `-poison` queue for handling retries and failures.

## 3. The Consumer (`Cognito.QueueJob` Project)

This project is the heart of the worker process. It is a console application that can be hosted in various ways (including by the `Cognito.QueueService` Windows Service).

-   **Host & Triggers**: The `Program.cs` file uses the Azure WebJobs SDK. It defines `[QueueTrigger]` functions for each of the Azure queues. The SDK handles the low-level work of polling the queues for new messages.

-   **Processing Logic**: When a message is received, it is passed to a central `ProcessQueueMessage` method. This method deserializes the message and uses an Autofac Dependency Injection container to resolve the correct handler for the job. Each job type has a corresponding class that implements `IMessageHandler<T>` where `T` is the job's specific data type.

-   **Retry & Failure Handling**: The `CognitoQueueProcessor` class implements sophisticated failure handling:
    -   **Retry Strategy**: If a job handler fails, the processor releases the message back to the queue with an **exponential backoff** delay. The delay increases with each subsequent failure, preventing a failing job from overwhelming the system.
    -   **Poison Queue**: If a message fails more than a configured number of times (`MaxDequeueCount`), the processor considers it a "poison message". It is automatically moved to a corresponding `-poison` queue for manual inspection and debugging, preventing it from blocking the main queue.