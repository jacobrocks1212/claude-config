---
name: cognito-queue-jobs
description: Expert guidance on the background job and queue processing system in Cognito Forms, including Cognito.QueueJob, Cognito.QueueService, and Cognito.QueueWorker.
version: 1.0.0
---
# Cognito Forms - Queue & Background Jobs Skill

This skill provides expert knowledge on the asynchronous background job processing system. Use this when working on features that involve long-running tasks, queuing, or interacting with the `Cognito.QueueJob`, `Cognito.QueueService`, or `Cognito.QueueWorker` projects.

## Core Concepts
- **Job Enqueueing**: How jobs are added to the queue via `Cognito.QueueService`.
- **Job Processing**: How `Cognito.QueueWorker` picks up and executes jobs.
- **Job Definition**: The structure of a job within the `Cognito.QueueJob` project.
- **Error Handling & Retries**: The pattern for handling failures and retrying jobs.

## When to Reference Additional Files
- For a high-level diagram and explanation of how the services interact, read **`architecture-overview.md`**.
- To understand the step-by-step process from a job being queued to its completion or failure, read **`job-processing-lifecycle.md`**.
