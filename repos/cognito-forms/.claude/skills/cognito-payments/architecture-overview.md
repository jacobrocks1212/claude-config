# Payment System Architecture

The payment system is designed around a central service that acts as a facade, delegating to specific processor implementations. This allows the core business logic in `FormsService` to remain decoupled from the details of any single payment provider.

## 1. Core Components

### `IPaymentService` and `PaymentService.cs`
-   **Contract and Orchestrator**: `IPaymentService` (in `Cognito.Core/Services/Payment/IPaymentService.cs`) defines the main contract for all payment-related operations, such as `MakePayment`, `RefundOrder`, and `GetPaymentAccount`.
-   `PaymentService` (in `Cognito.Core/Services/Payment/PaymentService.cs`) is the concrete implementation. It does not contain provider-specific logic itself. Instead, it determines the correct provider to use and delegates the work to a specific processor.

### `IPaymentProcessor` (Strategy Pattern)
-   **Processor Contract**: This interface defines the common methods that every payment processor must implement, such as `SubmitPayment` and `RefundPayment`.
-   **Concrete Processors**: The codebase contains implementations of `IPaymentProcessor`:
    -   `StripePaymentProcessor.cs`
    -   `PayPalPaymentProcessor.cs`
    -   `SquarePaymentProcessor.cs`
    -   `ManualPaymentProcessor.cs`
-   The `PaymentService` uses a factory method (`GetPaymentProcessor`) to select the correct processor at runtime based on the `ProcessorName` property of the `PaymentAccount`.

### Data Models
-   **`PaymentAccount`**: Represents a configured payment provider for an organization (e.g., a specific Stripe or Square account). It holds the provider type, API keys (in `Gateway`), and status.
-   **`Order`**: Represents a single transaction, including line items, fees, totals, and payment status. It is the primary object passed to the payment services.
-   **`LineItem`**: Represents a single billable item within an `Order`.
-   **`Payment`**: Represents an individual payment attempt or transaction against an `Order`.

## 2. High-Level Data Flow

1.  A user action (like submitting a form) initiates a payment process within a higher-level service like `FormsService`.
2.  `FormsService` builds an `Order` object from the form entry data.
3.  `FormsService` calls a method on `IPaymentService` (e.g., `PayOrder`), passing in the `Order` and a `PaymentAccountRef`.
4.  `PaymentService` receives the request.
5.  It inspects the `PaymentAccount` to determine the provider (Stripe, PayPal, etc.).
6.  It retrieves the corresponding `IPaymentProcessor` implementation.
7.  It calls the `SubmitPayment` method on that specific processor, passing along the necessary data.
8.  The concrete processor class (`StripePaymentProcessor`, etc.) then makes the actual API calls to the external payment gateway using the credentials stored in the `PaymentAccount`.
9.  The result is returned up the chain.