# Authorization Flow

Authorization in Cognito Forms determines what an authenticated user is allowed to do. The process is centered around the `[CognitoAuthorize]` attribute and a hierarchical permission model.

## 1. The Gatekeeper: `[CognitoAuthorize]`

Every secured action on a controller is decorated with the `CognitoAuthorize` attribute, which specifies the required permission.

```csharp
[HttpPost]
[CognitoAuthorize(SecurityTask.ManageEntries)]
public ActionResult UpdateEntry(string formId, string entryId, ...)
{
    // Method body only executes if authorization succeeds
}
```

## 2. The Permission Definition: `SecurityTask`

The `SecurityTask` class (in `Cognito.Core/Infrastructure/Forms/SecurityTask.cs`) defines all possible actions in the system as static properties. Each task is mapped to the roles that are permitted to perform it.

```csharp
public class SecurityTask
{
    // Only Owner and Admin can manage forms.
    public static readonly SecurityTask ManageForm = new SecurityTask("Manage Form", new[] { Role.Owner, Role.Admin });

    // Owner, Admin, and Editor can manage entries.
    public static readonly SecurityTask ManageEntries = new SecurityTask("Manage Entries", new[] { Role.Owner, Role.Admin, Role.Editor });

    // Owner, Admin, Editor, and Reviewer can view entries.
    public static readonly SecurityTask ReviewEntries = new SecurityTask("Review Entries", new[] { Role.Owner, Role.Admin, Role.Editor, Role.Reviewer });
}
```

## 3. The Authorization Check: `Assert` Method

When a request is made, the `CognitoAuthorizeAttribute` calls the `FormsService.Assert()` method, which performs the permission check. The logic follows a specific hierarchy to determine the user's "effective role" for the target resource.

### The Permission Hierarchy

The system checks for permissions in the following order:

1.  **Form-Specific Role**: It first checks the user's `FormsProfile` for a `FormRole` entry that explicitly grants them a role for the specific form they are trying to access. If one is found, that role is used, and the check stops.

2.  **Folder-Specific Role**: If no form-specific role is found, it checks if the form belongs to a folder. If it does, it then checks the user's `FormsProfile` for a `FolderRole` for that folder. If one is found, that role is used, and the check stops.

3.  **Organization-Wide Role**: If neither a form nor a folder-specific role is found, the system falls back to the user's global role for the entire organization (e.g., `Admin`, `Editor`), which is stored on their `MemberProfile`.

4.  **Guest Role**: If the user has no specific roles and is a guest, they are assigned the `Guest` role.

### Example Flow

-   A user with an **Editor** role in the organization tries to access an action that requires `SecurityTask.ManageForm`.
-   The `Assert` method checks permissions:
    1.  Does the user have a specific role for this form? No.
    2.  Does the form belong to a folder where the user has a specific role? No.
    3.  What is the user's organization role? **Editor**.
-   The `SecurityTask.ManageForm` requires either `Owner` or `Admin`.
-   Since `Editor` is not in the allowed list, the `Assert` method throws an `UnauthorizedAccessException`, and the request is denied.

## 4. Workflow Role Assignments

In addition to the primary permission model, a separate system exists for workflow-specific permissions. The `WorkflowRoleAssignment` collection on a `FormsProfile` grants a user a specific workflow `Role` (defined on the form itself) for a specific form. This is used to control who can perform workflow actions (like `Approve` or `Reject`) on an entry, which is a separate concern from their ability to manage the form or its entries.
