# Expression Function Library

This document lists the available functions that can be used in Cognito Forms expressions. The expression engine exposes a subset of standard .NET methods from common classes.

## Text Functions (String)

These functions are called on a Text field or a text literal.

-   **`Contains(substring)`**: Returns `true` if the text contains the specified substring.
    -   *Example*: `=Description.Contains("Urgent")`

-   **`StartsWith(substring)`**: Returns `true` if the text starts with the specified substring.
    -   *Example*: `=Email.StartsWith("support@")`

-   **`EndsWith(substring)`**: Returns `true` if the text ends with the specified substring.
    -   *Example*: `=FileName.EndsWith(".pdf")`

-   **`ToLower()`**: Converts the text to lowercase.
    -   *Example*: `=State.ToLower() = "fl"`

-   **`ToUpper()`**: Converts the text to uppercase.
    -   *Example*: `=CouponCode.ToUpper() = "FREEBIE"`

-   **`Length`**: A property that returns the number of characters in the text.
    -   *Example*: `=ZipCode.Length = 5`

## Date and Time Functions (DateTime)

These functions are used for date and time calculations.

-   **`DateTime.Today`**: Returns the current date with the time set to midnight.

-   **`DateTime.Now`**: Returns the current date and time.

-   **`AddDays(days)`**: Adds the specified number of days to a date.
    -   *Example*: `=StartDate.AddDays(14)`

-   **`AddMonths(months)`**: Adds the specified number of months to a date.
    -   *Example*: `=FirstPaymentDate.AddMonths(1)`

-   **`AddYears(years)`**: Adds the specified number of years to a date.
    -   *Example*: `=WarrantyStartDate.AddYears(1)`

-   **`DateDiff(date1, date2)`**: Returns the number of whole days between two dates.
    -   *Example*: `=DateDiff(StartDate, EndDate)`

-   **Properties**: Date fields have properties that can be accessed with a dot.
    -   `MyDate.Year`
    -   `MyDate.Month`
    -   `MyDate.Day`
    -   `MyDate.Hour`
    -   `MyDate.Minute`
    -   `MyDate.Second`

## Math Functions (Math)

These are static functions called via the `Math` class.

-   **`Min(value1, value2)`**: Returns the smaller of two numbers.
    -   *Example*: `=Math.Min(Amount1, Amount2)`

-   **`Max(value1, value2)`**: Returns the larger of two numbers.
    -   *Example*: `=Math.Max(Score1, Score2)`

-   **`Round(number, digits)`**: Rounds a number to the specified number of decimal places.
    -   *Example*: `=Math.Round(CalculatedValue, 2)`

-   **`Abs(number)`**: Returns the absolute value of a number.
    -   *Example*: `=Math.Abs(Balance)`

## Logical Functions

-   **`iif(condition, trueValue, falseValue)`**: Evaluates the condition. If it's true, returns `trueValue`; otherwise, returns `falseValue`.
    -   *Example*: `=iif(State = "WA", Price * 1.09, Price)`

## Collection Functions (Enumerable)

These functions are used on Repeating Section fields and multi-select (Checkboxes) Choice fields.

-   **`Count()`**: Returns the number of items in the collection.
    -   *Example*: `=Attendees.Count()`

-   **`Where(condition)`**: Filters a collection based on a condition. The condition is an expression where `it` refers to a single item in the collection.
    -   *Example*: `=Attendees.Where(it.Age >= 21)`

-   **`Sum(selector)`**: Calculates the sum of a numeric property for all items in a collection.
    -   *Example*: `=LineItems.Sum(it.Price * it.Quantity)`

-   **`Average(selector)`**: Calculates the average of a numeric property for all items in a collection.
    -   *Example*: `=TestScores.Average(it.Score)`

-   **`Min(selector)`**: Finds the minimum value of a property in a collection.
    -   *Example*: `=Laps.Min(it.Time)`

-   **`Max(selector)`**: Finds the maximum value of a property in a collection.
    -   *Example*: `=Bids.Max(it.Amount)`

-   **`Contains(value)`**: Returns `true` if the collection contains the specified value. Used for multi-select Choice fields.
    -   *Example*: `=Toppings.Contains("Pepperoni")`

-   **`Any()`**: Returns `true` if the collection has any items.
    -   *Example*: `=Attendees.Any()`

-   **`All(condition)`**: Returns `true` if all items in the collection satisfy the condition.
    -   *Example*: `=Tasks.All(it.Status = "Complete")`