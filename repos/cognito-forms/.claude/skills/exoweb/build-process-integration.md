# ExoWeb: build.js Integration

## What build.js Is

`build.js` (`Cognito.Services/Views/Shared/build.js`) is a **client-side browser JavaScript file** served by ASP.NET as part of the form builder UI. It is NOT a Node.js build script — changes take effect when the browser loads the file (no build step required for this file).

## Role of ExoWeb in build.js

ExoWeb is a **runtime client-side framework** that provides:
- Data binding (`sys:if`, `sys:attach`) for the form builder UI
- Change tracking and event logging for live editing
- Model metadata with automatic dependency tracking
- Client-server synchronization via change replay

## Key ExoWeb APIs Used in build.js

```javascript
// Adding properties to existing types
form.meta.addProperty({ name: "MyProperty", type: Object });

// Creating calculated properties with dependency tracking
form.meta.addProperty({ name: "DisplayName", type: String }).calculated({
    calculate: function () {
        return this.get_Name();
    },
    onChangeOf: ["Name"]
});

// Condition types for validation
new ExoWeb.Model.ConditionType.Error("UniqueCode", "MyRule", ["Property"], ...);

// Observer for change tracking
ExoWeb.Observer.setValue(entity, "PropertyName", newValue);

// Updating arrays with change tracking
ExoWeb.updateArray(targetArray, newItems);
```

## How to Modify build.js Safely

1. **Use the `/build-js` skill** to get a navigable index of the file before making changes
2. **Search for existing patterns** before adding new code — the file is large and may already have what you need
3. **Use `form.meta.addProperty`** to add computed properties for Vue bindings
4. **Add `set_HasChanges(true)`** in change handlers to mark the form dirty
5. **Use `Cognito.getEnumWithName()`** when setting enum properties from string values

## Static File — No Build Step

Since build.js is served directly by IIS/ASP.NET:
- Changes are live on next browser load (clear cache if needed)
- Only `.cs` file changes require `dotnet build`
- No `node build.js` command exists — do not try to run this file with Node
