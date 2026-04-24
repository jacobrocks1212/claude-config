# ExoWeb: Common Patterns

This document provides code examples for the most common patterns used with the ExoWeb framework in this project.

## Defining a Type

A `Type` is the basic building block, analogous to a class. Types are defined using `ExoWeb.Model.Type.extend`.

```javascript
// Example from a build script
var User = new ExoWeb.Model.Type.extend({
    name: "User",
    properties: {
        "FirstName": { type: "String" },
        "LastName": { type: "String" },
        "Email": { type: "String" },
        "IsActive": { type: "Boolean" }
    }
});
```

- **`name`**: The name of the type
- **`properties`**: A dictionary of properties, where the key is the property name
- **`type`**: The data type of the property (e.g., "String", "Number", "Boolean", "Date")

## Adding Validation Rules

Validation rules are added to properties to enforce data integrity.

### Required Rule

The most common rule is ensuring a field is not empty.

```javascript
var User = new ExoWeb.Model.Type.extend({
    name: "User",
    properties: {
        "FirstName": { type: "String" },
        "LastName": { type: "String" },
        "Email": { type: "String" }
    }
});

// Add a required rule to the Email property
User.meta.property("Email").rule(ExoWeb.Model.Rule.required());
```

### Regular Expression Rule

Use `regex` for pattern matching, such as for email formats.

```javascript
// Add a regex rule for email validation
var emailRegex = /^[\w-]+(\.[\w-]+)*@([a-zA-Z0-9-]+(\.[a-zA-Z0-9-]+)*?\.[a-zA-Z]{2,6}|(\d{1,3}\.){3}\d{1,3})(:\d{4})?$/;

User.meta.property("Email").rule(ExoWeb.Model.Rule.regex(
    "Invalid email format.",
    emailRegex
));
```

### Range Rule

Validates that a numeric value falls within a specific range.

```javascript
var Product = new ExoWeb.Model.Type.extend({
    name: "Product",
    properties: {
        "Price": { type: "Number" },
        "Quantity": { type: "Number" }
    }
});

// Price must be between 0 and 10000
Product.meta.property("Price").rule(ExoWeb.Model.Rule.range(
    "Price must be between $0 and $10,000.",
    0,
    10000
));
```

## Defining Calculated Properties

ExoWeb can define properties whose values are calculated from other properties. These automatically update when dependencies change.

```javascript
var User = new ExoWeb.Model.Type.extend({
    name: "User",
    properties: {
        "FirstName": { type: "String" },
        "LastName": { type: "String" },
        "FullName": {
            type: "String",
            calculated: function() {
                // 'this' refers to an instance of the User type
                return this.get_FirstName() + " " + this.get_LastName();
            }
        }
    }
});
```

- **`calculated`**: A function that returns the computed value
- **Getters**: Notice the use of `this.get_FirstName()` and `this.get_LastName()`. ExoWeb uses a getter/setter pattern. You **must** use these methods to ensure the framework's data binding and change tracking function correctly
- **Automatic Updates**: When FirstName or LastName changes, FullName automatically recalculates

## Working with Properties: Getters and Setters

ExoWeb generates getter and setter methods for each property to enable change tracking.

### Setting Property Values

```javascript
var user = new User();

// WRONG - Bypasses ExoWeb's change tracking
user.FirstName = "John";

// CORRECT - Uses ExoWeb's setter
user.set_FirstName("John");
user.set_LastName("Doe");
user.set_Email("john.doe@example.com");
```

### Getting Property Values

```javascript
// WRONG - Direct access
var name = user.FirstName;

// CORRECT - Uses ExoWeb's getter
var firstName = user.get_FirstName();
var lastName = user.get_LastName();
var fullName = user.get_FullName(); // Works for calculated properties too
```

## Defining Relationships

Types can be related to each other.

### One-to-One or Many-to-One Relationship

```javascript
var Order = new ExoWeb.Model.Type.extend({
    name: "Order",
    properties: {
        "OrderDate": { type: "Date" },
        "Customer": { type: "User" } // Reference to another ExoWeb type
    }
});
```

### One-to-Many Relationship (Collections)

```javascript
var User = new ExoWeb.Model.Type.extend({
    name: "User",
    properties: {
        "Name": { type: "String" },
        "Orders": {
            type: "Order[]", // Array notation indicates collection
            isList: true     // REQUIRED for collections
        }
    }
});
```

- **Single Reference**: `Customer: { type: "User" }` defines a one-to-one or many-to-one relationship
- **Collection**: `Orders: { type: "Order[]", isList: true }` defines a one-to-many relationship
- **Important**: Both the `[]` suffix AND `isList: true` are required for collections

### Working with Collections

```javascript
var user = new User();
user.set_Name("John Doe");

// Get the collection
var orders = user.get_Orders();

// Add an item to the collection
var newOrder = new Order();
newOrder.set_OrderDate(new Date());
orders.add(newOrder);

// Remove an item
orders.remove(newOrder);

// Check collection length
var orderCount = orders.length;
```

## Custom Validation Rules

You can create custom validation rules for complex business logic.

```javascript
var User = new ExoWeb.Model.Type.extend({
    name: "User",
    properties: {
        "Age": { type: "Number" },
        "ParentConsent": { type: "Boolean" }
    }
});

// Custom rule: Users under 18 must have parent consent
User.meta.property("ParentConsent").rule({
    name: "MinorConsentRequired",
    execute: function(obj) {
        var age = obj.get_Age();
        var consent = obj.get_ParentConsent();

        if (age < 18 && !consent) {
            return "Users under 18 must have parent consent.";
        }

        return null; // null means validation passes
    },
    onChangeOf: ["Age", "ParentConsent"] // Re-validate when these properties change
});
```

## Extending a Type After Definition

Sometimes you need to add properties or rules to a type defined elsewhere.

```javascript
// Assuming 'User' type is already defined
var userType = ExoWeb.Model.Model.get_type("User");

// Add a new property
userType.meta.addProperty({
    name: "PhoneNumber",
    type: "String"
});

// Add a new rule to an existing property
userType.meta.property("PhoneNumber").rule(ExoWeb.Model.Rule.required());

// Add a calculated property
userType.meta.addProperty({
    name: "DisplayName",
    type: "String",
    calculated: function() {
        var firstName = this.get_FirstName();
        var email = this.get_Email();
        return firstName ? firstName : email;
    }
});
```

This is a common pattern in `build.js` where base models are extended with additional client-specific logic.
