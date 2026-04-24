# Entry Submission Payment Flow

This document details the step-by-step logical flow of how a payment is processed when a form entry is submitted. The primary method orchestrating this is `FormsService.SubmitEntry`.

1.  **Initial Validation**: `SubmitEntry` performs initial validation on the incoming entry to ensure it is not null and the associated form exists.

2.  **Build Order Object**: An `Order` object is constructed based on the entry data. This involves calculating amounts from fields marked for payment and creating `LineItem` objects.

3.  **Check for Payment**: The logic checks if the form requires payment (`form.PaymentEnabled`) and if the calculated `order.OrderAmount` is greater than zero.

4.  **Initiate Payment Service**: If a payment is required, `FormsService` calls `PaymentService.PayOrder(...)`.

5.  **Create `Payment` Record**: Inside `PayOrder`, a new `Payment` entity is created. This object represents this specific transaction attempt and is initially set to a status like `Unpaid`.

6.  **Get Payment Processor**: The `PaymentService` inspects the `PaymentAccount` associated with the form to determine which payment provider to use (e.g., Stripe, Square, PayPal). It retrieves the specific `IPaymentProcessor` implementation for that provider.

7.  **Delegate to Processor**: The `PaymentService` calls the `SubmitPayment` method on the selected processor (e.g., `StripePaymentProcessor.SubmitPayment(...)`), passing it the `Order`, `Payment`, and `PaymentAccount` details.

8.  **Processor Executes API Call**: The specific processor class (`StripePaymentProcessor`, etc.) is responsible for:
    a.  Constructing the provider-specific API request (e.g., creating a `PaymentIntentCreateOptions` for Stripe).
    b.  Adding customer information, amounts, currency, and the payment token/nonce.
    c.  Making the actual HTTP API call to the external payment gateway (e.g., api.stripe.com).

9.  **Handle Processor Response**: The processor receives the response from the gateway.
    a.  **Success**: If the payment is successful, it populates a `SubmitPaymentResponse` object with the confirmation number, payment status (`Paid`), and other details.
    b.  **Failure**: If the payment is declined, it populates the response with the error code, error message, and a `Declined` status.
    c.  **Authentication Required**: For providers like Stripe that support 3D Secure, if further authentication is required, the processor returns a specific status and the `client_secret` needed for the frontend to complete the authentication step.

10. **Update `Payment` Record**: Back in `PaymentService`, the `Payment` entity created in Step 5 is updated with the results from the `SubmitPaymentResponse` (e.g., status is changed to `Paid` or `Declined`, confirmation number is set).

11. **Store `Payment` and `Order`**: The updated `Payment` and `Order` objects are saved to the database via `StorageContext`.

12. **Return to `FormsService`**: Control returns to `FormsService.SubmitEntry`.

13. **Finalize Submission**: `SubmitEntry` proceeds with the rest of its post-processing logic (like running Linked Lookups and Auto-Create), now that the payment step is complete. The final `SubmissionResult` is then returned.