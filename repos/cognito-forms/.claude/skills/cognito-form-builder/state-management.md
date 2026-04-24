# Form Builder State Management

The form builder's state is managed through a combination of a modern Vue-based global store and a legacy client-side model framework called ExoWeb.

## 1. The Global Application State: `globalStore`

The entire SPA's state is managed by a reactive object named `globalStore`, defined in `apps/spa/src/stores/global-store.ts`. This store is responsible for holding application-level data, including:

-   `user`: The currently logged-in user.
-   `organization`: The current organization's details and plan.
-   `forms`: A dictionary of all forms the user has access to.
-   `folders`: A dictionary of all folders.
-   `currentFormId` / `currentViewId`: The IDs of the form and view currently being accessed.

When the `FormBuilder.vue` component loads, it interacts with this `globalStore` to get high-level information about the form being edited.

## 2. The Form Definition: `FormDefinitionBuilder`

When a form is loaded, its structure and data model are defined by the `FormDefinitionBuilder` class found in `apps/client/src/framework/form-definition.ts`. This class is responsible for:

1.  Receiving a form `template` (the Vue template string) and `modelOptions` (the data structure) from the server.
2.  Compiling the template into a runnable Vue component.
3.  Creating a `FormsModel` instance, which represents the specific data and logic for that form.

## 3. The Legacy Builder State: `Cognito.Forms.model` (ExoWeb)

This is the heart of the state *within the builder UI itself*. The architecture is a bridge between the modern Vue app and the legacy builder script.

1.  **Serialization**: The C# backend serializes a `Cognito.Forms.Form` object into a large JSON string.
2.  **Initialization**: This JSON is passed to the client. The `initialize` function in `build.js` calls `Cognito.deserialize(...)` to turn this JSON into a client-side **ExoWeb Model Instance**.
3.  **Centralization**: This live model instance is then assigned to a global variable: `Cognito.Forms.model.currentForm`.

### Data Flow within the Builder

-   **UI to Model**: When a user interacts with the UI (ex: types a new label into a settings input), a jQuery event handler in `build.js` is triggered. This handler calls a setter method on the `ExoWeb` model object, like `currentElement.set_Name("New Label")`.
-   **Model to UI**: The ExoWeb framework provides data-binding. When a property on the `currentForm` model changes, other parts of the UI that are bound to that property automatically update. For example, the field's title on the canvas updates as you type in the settings pane.
-   **Saving**: When the user clicks "Save", the `Cognito.Forms.saveCurrentForm` function is called. This function serializes the `Cognito.Forms.model.currentForm` object back into JSON and sends it to the server API endpoint to be saved.