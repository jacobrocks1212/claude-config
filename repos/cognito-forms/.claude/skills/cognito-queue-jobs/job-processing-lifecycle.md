# Job Processing Lifecycle

This document describes the step-by-step lifecycle of a single job, from creation to completion or failure.

### 1. Creation & Enqueueing

A job begins when a producer service needs to execute a task asynchronously.

1.  A C# object representing the job is created (e.g., `SendEmailJob`).
2.  This object is wrapped in a `QueueMessageEnvelope`, which contains the job data and metadata.
3.  The envelope is serialized to JSON and sent as a message to a specific Azure Storage Queue (e.g., `emails-queue`).

### 2. Dequeueing

The `Cognito.QueueJob` worker process is constantly monitoring the queues using Azure WebJobs SDK triggers.

1.  The SDK polls the queue and retrieves a new message.
2.  The message is passed to the appropriate `[QueueTrigger]` function in `Program.cs`.

### 3. Pre-processing and Retry Check

Before any business logic is executed, the custom `CognitoQueueProcessor` intercepts the message.

1.  It inspects the `DequeueCount` property of the message.
2.  If `DequeueCount` exceeds the configured `MaxDequeueCount` (e.g., 5), the message is considered **poison**. The processor immediately moves it to the corresponding `-poison` queue (e.g., `emails-queue-poison`) and stops all further processing for this message.

### 4. Deserialization and Handler Resolution

If the message is not poison, the worker proceeds:

1.  The JSON content of the message is deserialized from the `QueueMessageEnvelope` back into its specific C# job object.
2.  The `HandleMessage` function uses an Autofac DI container to find and resolve the specific handler class registered for that job type (e.g., it finds the `SendEmailHandler` which implements `IMessageHandler<SendEmailJob>`).

### 5. Execution

The `Handle` method of the resolved handler is invoked, and the business logic for the job is executed.

### 6. Success Path

-   If the `Handle` method completes successfully and returns `true`, the `CognitoQueueProcessor` is notified.
-   It calls `DeleteMessageAsync`, permanently removing the message from the queue. The lifecycle for this job is complete.

### 7. Failure & Retry Path

-   If the `Handle` method throws an exception or returns `false`, the processor catches the failure.
-   It calculates a retry delay using an **exponential backoff** strategy (the delay gets longer with each failure).
-   It calls `ReleaseMessageAsync`, which places the message back on the queue but makes it invisible for the duration of the calculated delay.
-   When the delay expires, the message becomes visible again, and the worker will pick it up, starting the process over from Step 2. The `DequeueCount` will now be higher, bringing it closer to the poison threshold.