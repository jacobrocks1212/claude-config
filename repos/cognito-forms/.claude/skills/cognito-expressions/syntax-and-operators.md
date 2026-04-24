# Expression Syntax and Operators

This document describes the syntax, data types, and operators available in the Cognito Forms expression engine.

## Basic Syntax

-   All expressions **must** begin with an equals sign (`=`).
-   Field names can be referenced directly. If a field name contains spaces, it must be enclosed in square brackets (e.g., `=[First Name]`).
-   String literals must be enclosed in double quotes (`"`).
-   The `.` (dot) operator is used to access properties of fields (e.g., `Name.First`).

## Data Types

The expression engine supports the following primary data types:

-   **Text (String)**: A sequence of characters. Ex: `"Hello World"`
-   **Number (Decimal/Integer)**: Numeric values. Ex: `100`, `12.50`
-   **Yes/No (Boolean)**: `true` or `false`.
-   **Date/Time**: A date, time, or datetime value. Ex: `DateTime.Today`, `"2025-10-20"`
-   **Collections**: An ordered list of items, typically from a repeating section or a multi-select choice field.

## Referencing Fields

You can refer to any field on your form by its name. For fields inside a section, use dot notation.

-   `=FirstName`
-   `=Price * Quantity`
-   `=Address.City`
-   `=RepeatingSection.Sum(ItemPrice)`

## Operators

The engine supports a standard set of arithmetic, comparison, and logical operators.

### Arithmetic Operators

| Operator | Description      | Example                     |
| :------- | :--------------- | :-------------------------- |
| `+`      | Addition         | `=Price + 5`                |
| `-`      | Subtraction      | `=Quantity - 1`             |
| `*`      | Multiplication   | `=Price * Quantity`         |
| `/`      | Division         | `=Total / 2`                |
| `%`      | Modulo           | `=NumberOfItems % 2`        |

### Comparison Operators

| Operator | Description          | Example                           |
| :------- | :------------------- | :-------------------------------- |
| `=`      | Equals               | `=State = "FL"`                   |
| `!=`     | Not Equals           | `=Status != "Complete"`           |
| `<`      | Less Than            | `=Amount < 100`                   |
| `<=`     | Less Than or Equal   | `=Quantity <= 5`                  |
| `>`      | Greater Than         | `=Price > 0`                      |
| `>=`     | Greater Than or Equal| `=Age >= 21`                      |

### Logical Operators

Logical operators are used to combine multiple conditions.

| Operator | Description                                | Example                               |
| :------- | :----------------------------------------- | :------------------------------------ |
| `and`    | Returns `true` if both conditions are true.  | `=State = "FL" and Amount > 100`      |
| `or`     | Returns `true` if either condition is true. | `=Status = "Shipped" or Status = "Complete"` |
| `not`    | Inverts the result of a condition.         | `=not (State = "CA")`                 |

### Operator Precedence

The order of operations is standard:
1.  Parentheses `()`
2.  Multiplication (`*`), Division (`/`), Modulo (`%`)
3.  Addition (`+`), Subtraction (`-`)
4.  Comparison (`=`, `!=`, `>`, etc.)
5.  Logical NOT (`not`)
6.  Logical AND (`and`)
7.  Logical OR (`or`)

Use parentheses `()` to explicitly control the order of evaluation.

```csharp
// Without parentheses, multiplication happens first
= Price + 5 * 2  // If Price is 10, result is 20

// With parentheses, addition happens first
= (Price + 5) * 2 // If Price is 10, result is 30
```