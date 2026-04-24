# ExoWeb: Pitfalls and Workarounds

Working with ExoWeb requires awareness of its specific quirks and limitations. This document outlines common issues and how to handle them.

## Pitfall: Directly Accessing Properties

Directly accessing or modifying properties bypasses ExoWeb's change tracking mechanism, which breaks data binding, validation, and client-server synchronization.

**Anti-Pattern:**
```javascript
var user = new User();
user.FirstName = "John"; // WRONG - Bypasses framework
var name = user.FirstName; // WRONG - Direct access
```

**Correct Pattern:**
Use the generated getter and setter methods. ExoWeb automatically creates `get_` and `set_` methods for each property.

```javascript
var user = new User();
user.set_FirstName("John"); // CORRECT
var name = user.get_FirstName(); // CORRECT
```

**Why This Matters:**
- Change tracking won't detect the modification
- Calculated properties that depend on it won't update
- Validation rules won't trigger
- Client-server sync will fail to capture the change

## Pitfall: Forgetting `isList: true` for Collections

When defining a one-to-many relationship, you must include `isList: true`. Forgetting it can lead to runtime errors or incorrect behavior when trying to manipulate the collection.

**Anti-Pattern:**
```javascript
var User = new ExoWeb.Model.Type.extend({
    name: "User",
    properties: {
        "Orders": { type: "Order[]" } // Missing isList: true
    }
});
```

**Correct Pattern:**
```javascript
var User = new ExoWeb.Model.Type.extend({
    name: "User",
    properties: {
        "Orders": {
            type: "Order[]",
            isList: true // CORRECT - Required for collections
        }
    }
});
```

**Symptoms of Missing `isList`:**
- Unable to call `.add()` or `.remove()` on the collection
- Collection length is undefined or incorrect
- Runtime errors when attempting to iterate over the collection

## Pitfall: Incorrect `this` Context in Rules/Calculations

JavaScript's `this` can be tricky. In calculated properties and custom rules, `this` should refer to the model instance. Using arrow functions can sometimes capture the wrong `this` context.

**Anti-Pattern:**
```javascript
// Arrow function might capture the wrong 'this' depending on the surrounding scope
"FullName": {
    type: "String",
    calculated: () => this.get_FirstName() + " " + this.get_LastName()
}
```

**Correct Pattern:**
Use a standard `function` expression to ensure ExoWeb can correctly bind `this`.

```javascript
"FullName": {
    type: "String",
    calculated: function() {
        return this.get_FirstName() + " " + this.get_LastName();
    }
}
```

**Why This Matters:**
- Arrow functions lexically bind `this`, which means they use `this` from the surrounding scope
- ExoWeb expects to set `this` to the model instance when calling calculated functions
- Using arrow functions can result in `this` being `undefined` or pointing to the wrong object

## Pitfall: Not Handling Null/Undefined in Calculations

Calculated properties must handle cases where dependent properties are null or undefined.

**Anti-Pattern:**
```javascript
"FullName": {
    type: "String",
    calculated: function() {
        // Will fail if FirstName or LastName is null/undefined
        return this.get_FirstName() + " " + this.get_LastName();
    }
}
```

**Correct Pattern:**
```javascript
"FullName": {
    type: "String",
    calculated: function() {
        var firstName = this.get_FirstName() || "";
        var lastName = this.get_LastName() || "";
        return (firstName + " " + lastName).trim();
    }
}
```

## Pitfall: Modifying Collections Without Using ExoWeb APIs

Collections must be modified using ExoWeb's methods to ensure change tracking.

**Anti-Pattern:**
```javascript
var user = new User();
var orders = user.get_Orders();

// WRONG - Direct array manipulation
orders.push(newOrder);
orders.splice(0, 1);
```

**Correct Pattern:**
```javascript
var user = new User();
var orders = user.get_Orders();

// CORRECT - Use ExoWeb collection methods
orders.add(newOrder);
orders.remove(existingOrder);
orders.clear(); // Remove all items
```

## Debugging Tip: Using `meta`

Every ExoWeb object has a `meta` property that provides access to its type information, rules, and state. This is invaluable for debugging.

```javascript
var user = new User();
user.set_Email("invalid-email");

// Check for validation errors
var emailProp = user.meta.property("Email");
if (!emailProp.get_isValid()) {
    console.log("Email validation errors:", emailProp.get_errors());
}

// Inspect the type definition
console.log("Type name:", user.meta.type.get_name()); // "User"

// List all properties
console.log("Properties:", user.meta.type.get_properties());

// Check if a property has changed
console.log("Email changed?", emailProp.get_isChanged());

// Get original value before changes
if (emailProp.get_isChanged()) {
    console.log("Original email:", emailProp.get_originalValue());
    console.log("Current email:", user.get_Email());
}
```

## Debugging Tip: Inspecting Change Tracking

ExoWeb maintains detailed change tracking information.

```javascript
var user = new User();
user.set_FirstName("John");
user.set_LastName("Doe");

// Check if the object has any changes
console.log("Has changes?", user.meta.get_isChanged());

// Get all changed properties
var changedProps = user.meta.get_properties().filter(function(prop) {
    return prop.get_isChanged();
});

console.log("Changed properties:", changedProps.map(function(p) {
    return p.get_name();
}));

// Reset changes (revert to original values)
user.meta.revert();
console.log("After revert:", user.get_FirstName()); // Will be original value
```

## Debugging Tip: Validation State

Understanding validation state is crucial for debugging form issues.

```javascript
var user = new User();
user.set_Email(""); // Assuming Email is required

// Check overall validation state
console.log("Is valid?", user.meta.get_isValid());

// Get all validation errors for the object
var allErrors = [];
user.meta.get_properties().forEach(function(prop) {
    if (!prop.get_isValid()) {
        allErrors.push({
            property: prop.get_name(),
            errors: prop.get_errors()
        });
    }
});

console.log("All validation errors:", allErrors);
```

## Workaround: Extending a Type After Definition

Sometimes you need to add properties or rules to a type defined elsewhere. You can access the type's `meta` property to modify it.

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
```

This is a common pattern in `build.js` where base models are extended with additional client-specific logic.

## Workaround: Conditional Rules

Sometimes you need rules that only apply under certain conditions.

```javascript
var User = new ExoWeb.Model.Type.extend({
    name: "User",
    properties: {
        "Age": { type: "Number" },
        "HasDriversLicense": { type: "Boolean" },
        "LicenseNumber": { type: "String" }
    }
});

// License number is only required if user has a driver's license
User.meta.property("LicenseNumber").rule({
    name: "ConditionalLicenseNumber",
    execute: function(obj) {
        if (obj.get_HasDriversLicense() && !obj.get_LicenseNumber()) {
            return "License number is required when you have a driver's license.";
        }
        return null;
    },
    onChangeOf: ["HasDriversLicense", "LicenseNumber"]
});
```

## Performance Tip: Avoid Expensive Calculations

Calculated properties run every time a dependency changes. Avoid expensive operations.

**Anti-Pattern:**
```javascript
"ExpensiveCalculation": {
    type: "String",
    calculated: function() {
        // This runs on EVERY change to dependencies
        return this.get_Orders().map(function(order) {
            return complexExpensiveOperation(order);
        }).join(", ");
    }
}
```

**Better Pattern:**
Consider caching or computing values server-side and sending them as regular properties, only using calculated properties for simple, fast operations.

```javascript
"OrderCount": {
    type: "Number",
    calculated: function() {
        // Simple, fast operation
        return this.get_Orders().length;
    }
}
```
