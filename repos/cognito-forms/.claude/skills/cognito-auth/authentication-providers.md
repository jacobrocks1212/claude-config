# Authentication Providers

Cognito Forms supports two primary methods of user authentication: standard email/password and Single Sign-On (SSO) via external providers.

## 1. Standard Email/Password Authentication

This is the default authentication flow, managed primarily by the `AuthController`.

### The Flow

1.  **Initiation**: The user provides their email address. The client calls the `POST /auth/email` endpoint.
2.  **Authentication Check**: The `authManager.InitiateEmailAuthenticationAsync` method checks if the email corresponds to an existing user.
3.  **Password Prompt**: If the user exists and uses password authentication, the client is prompted to ask for the password.
4.  **Password Login**: The user submits their password to `POST /auth/email/password`. The `authManager.LoginWithEmailAndPasswordAsync` method validates the credentials.
5.  **Multi-Factor Authentication (MFA)**: If the user has MFA enabled, the API returns a `MultifactorResult`. The client prompts for the MFA code, which is then submitted to `POST /auth/multifactor-verification`.
6.  **Session Established**: Upon successful validation of all credentials, `sessionManager.EstablishSession` is called, which creates a session for the user and returns the final `AuthResult` with a success status and a redirect URL.

### New User Signup

-   If a user provides an email that does not exist, they are directed to the signup flow.
-   The `POST /auth/email/signup` endpoint, handled by `authManager.SignupWithEmailAsync`, creates a new user, hashes their password, and logs them in.

## 2. Single Sign-On (SSO)

SSO allows users to authenticate using an external identity provider. This is primarily managed by the `SingleSignOnService` and the `OpenIdConnectController`.

### Configuration

-   An organization administrator can configure a required authentication method for their organization.
-   The `SingleSignOnService.UpdateRequiredSso` method is used to set up a new SSO provider.
-   For custom providers, an `AuthenticationConfiguration` entity is created, storing details like the provider's discovery URL, client ID, and client secret.

### The Flow (OpenID Connect)

1.  **Redirect to Provider**: When a user from an SSO-enabled organization attempts to log in, the `CognitoAuthorizeAttribute` detects the SSO requirement and redirects the user to the external identity provider's login page.
2.  **External Authentication**: The user authenticates with the external provider (e.g., Azure AD, Okta).
3.  **Redirect Back to Cognito**: The provider redirects the user back to a callback endpoint in Cognito Forms, providing an `authorization_code`.
4.  **Code for Token Exchange**: The `IAuthenticationServiceProvider` (resolved by `SingleSignOnService`) takes the `authorization_code` and makes a back-channel request to the external provider to exchange it for an `id_token` and/or `access_token`.
5.  **User Info Validation**: The service validates the token and uses it to get the user's information (like email address) from the external provider.
6.  **User Matching**: The `externalIdentityService.ValidateExternalIdentity` method finds or creates a corresponding Cognito Forms user account that matches the email from the external identity.
7.  **Session Established**: A session is established for the matched user, and they are logged into the application.
