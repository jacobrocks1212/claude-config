# Payment Provider Guides

This document provides specific details for each of the three main payment processor implementations.

## 1. Stripe (`StripePaymentProcessor.cs`)

-   **Primary Logic**: The `SubmitPayment` method orchestrates the entire process.
-   **API Interaction**: It uses the official `Stripe.net` library.
-   **Payment Flow**:
    1.  It determines if it's confirming a pre-existing `PaymentIntent` (used for 3D Secure authentication) or creating a new one.
    2.  For new payments, it creates a `PaymentIntentCreateOptions` object, populating it with amount, currency, description, and customer details.
    3.  It sets `ConfirmationMethod = "manual"` for payments requiring client-side authentication, or `"automatic"` for off-session payments with a saved card.
    4.  It calls the `PaymentIntentService.Create()` or `PaymentIntentService.Confirm()` method from the Stripe library.
    5.  If the resulting `PaymentIntent.Status` is `succeeded`, the payment is considered successful.
    6.  If the status is `requires_action`, it returns a specific error code (`authentication_required`) and the `client_secret` to the frontend so the user can complete 3D Secure authentication.
-   **Customer Handling**: It can create new `Customer` objects in Stripe or use existing ones (`payment.CustomerCard.CustomerId`) for saved-card payments.
-   **Error Handling**: It catches `StripeException` and translates Stripe's error codes and messages into a `SubmitPaymentResponse`.

## 2. PayPal (`PayPalPaymentProcessor.cs`)

-   **Primary Logic**: The `SubmitPayment` method handles the final capture of an order that was already created and approved on the client side.
-   **API Interaction**: It uses a custom `IPayPalClient` to make direct HTTP requests to the PayPal API.
-   **Payment Flow**:
    1.  It receives a PayPal `Order ID` via the `payment.AuthorizationToken.Token`.
    2.  Before capturing, it first performs an **Update Order** API call. It sends a list of `PayPalUpdateOperation` objects to update the amount, description, and a custom `invoice_id` on the PayPal order to match the final Cognito Forms order.
    3.  It then calls `payPalClient.CapturePayment()` using the PayPal Order ID.
    4.  It inspects the `Status` of the capture in the response. A status of `COMPLETED` means success. `DECLINED` or `DENIED` indicates failure.
-   **Data Mapping**: It contains logic to map PayPal's card brand strings (e.g., "AMEX") to the internal `PaymentMethod` enum.
-   **Reconciliation**: The `GetTransaction` method can fetch order details from PayPal using the transaction ID to reconcile status.

## 3. Square (`SquarePaymentProcessor.cs`)

-   **Primary Logic**: The `SubmitPayment` method creates and processes a new payment through the Square API.
-   **API Interaction**: It uses a custom `ISquareClient` for making API calls.
-   **Payment Flow**:
    1.  It builds a `SquareCreatePaymentRequest` object.
    2.  It populates the request with amount, currency, billing address, and an `IdempotencyKey` (using the Cognito Payment ID) to prevent duplicate charges.
    3.  It determines the payment source: if a saved card is used (`payment.CustomerCard`), it sets the `CustomerId` and `CustomerCardId`; otherwise, it uses the `CardNonce` from the `AuthorizationToken`.
    4.  It calls `squareClient.SubmitSquarePayment()`.
    5.  If the response contains errors, it translates them into a `SubmitPaymentResponse`.
    6.  If successful, it returns the `ConfirmationNumber` (the Square payment ID) and other transaction details.
-   **Customer Handling**: Like the Stripe processor, it can create new Customer profiles in Square via `CreateSquareCustomer` when a payment is made, or use existing customer IDs.
-   **Legacy Support**: The class contains separate logic (`ReconcileOldTransactions`, `RefundOldTransaction`) for handling older Square transactions made through a previous version of their API.