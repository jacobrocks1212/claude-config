# Expression Execution and Context

This document explains when expressions are evaluated and what data is available to them during execution.

## Execution Triggers

Expressions in Cognito Forms are not just calculated once; they are live and re-evaluate automatically whenever their underlying data changes. This is handled by the ExoModel framework's change tracking system.

An expression will re-calculate whenever one of its **dependent properties** is modified. The expression parser automatically detects these dependencies.

**Example:**

-   **Expression**: `=iif(State = "WA", Price * 1.09, Price)`
-   **Dependencies**: `State`, `Price`

This expression will automatically re-run if the value of either the `State` field or the `Price` field changes.

## The Data Context

All expressions are executed within the context of a single form entry. The properties of that entry are directly available to the expression.

### Referencing Fields

You can access the value of any field on the form simply by using its name. The parser automatically resolves this to a property on the current entry's data model.

-   `=Amount` is equivalent to `entry.Amount`.
-   `=Address.City` is equivalent to `entry.Address.City`.

### The `it` Keyword

When working with collection functions like `Where`, `Sum`, etc., the special keyword `it` is used to refer to a single item within the collection during an iteration.

```csharp
// For a repeating section called 'LineItems' with a 'Price' field:
=LineItems.Sum(it.Price)
```

In this example, `it` refers to a single `LineItem` instance within the `LineItems` collection as the `Sum` function iterates over them.

### Global Context and Functions

In addition to the entry's data, expressions have access to a global context that includes:

-   **Static Classes**: `DateTime`, `Math`, `String`, `Convert`.
-   **Global Functions**: A library of functions like `DateDiff()`, `Sum()`, etc.

This allows you to write expressions like `=Math.Min(FieldA, FieldB)` or `=DateTime.Today.AddDays(5)`. The parser knows that `Math` and `DateTime` are static classes and resolves the method calls accordingly.