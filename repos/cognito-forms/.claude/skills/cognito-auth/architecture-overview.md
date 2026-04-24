# Auth System Architecture

Cognito Forms employs a layered security model that separates authentication (verifying a user's identity) from authorization (determining what a user is allowed to do).

## 1. Core Components

### Authentication

-   **`AuthController.cs`**: The primary controller for handling standard user authentication. It manages email/password login, user signup, and password reset flows.
-   **`IAuthManager`**: An interface implemented by `AuthManager` that orchestrates the actual logic of authenticating a user, creating sessions, and handling different authentication states.
-   **`SingleSignOnService.cs`**: A dedicated service for managing authentication via external identity providers using protocols like OpenID Connect. It handles the configuration of SSO providers and the validation of tokens during the login redirect flow.

### Authorization

-   **`CognitoAuthorizeAttribute.cs`**: A custom `AuthorizeAttribute` that acts as the gatekeeper for controller actions. It is used to declare what permission is required for an action, e.g., `[CognitoAuthorize(SecurityTask.ManageForm)]`.
-   **`SecurityTask.cs`**: A static class that defines all possible discrete permissions within the system (e.g., `ManageForm`, `ReviewEntries`, `ManageRoles`). Each `SecurityTask` is mapped to the list of `Role`s that are granted that permission.
-   **`FormPermissionService.cs`**: This service contains the core logic for checking if a user has the required permissions for a given form or folder. It implements the hierarchical permission check.
-   **`Role.cs`**: A simple lookup class that defines the available roles in the system: `Owner`, `Admin`, `Editor`, `Reviewer`, and `Guest`.
-   **`FormsProfile.cs`**: A critical data model linked to each user. It stores collections of `FormRole` and `FolderRole` objects, which explicitly grant a user a specific role for a specific form or folder, overriding their global organization role.

## 2. High-Level Flow

1.  A user attempts to access a protected resource.
2.  **Authentication**: The system first ensures the user has a valid session, established either via `AuthController` (password) or `SingleSignOnService` (SSO).
3.  **Authorization**: The `CognitoAuthorizeAttribute` on the controller action intercepts the request.
4.  The attribute invokes the authorization logic (found in `FormsService.Assert` which uses `FormPermissionService`).
5.  The service checks the user's `FormsProfile` to determine their effective role for the requested resource (form-specific, folder-specific, or organization-wide).
6.  It compares the user's effective role against the roles permitted by the required `SecurityTask`.
7.  If the permission is granted, the request proceeds. If not, an `UnauthorizedAccessException` is thrown.
