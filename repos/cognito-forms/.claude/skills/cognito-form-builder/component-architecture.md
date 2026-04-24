# Form Builder Component Architecture

The form builder uses a hybrid architecture that combines a modern Vue.js component host with a legacy, data-driven UI rendered via jQuery and a framework called ExoWeb.

## 1. The Host: `FormBuilder.vue`

The primary entry point for the builder is the `FormBuilder.vue` component (`apps/spa/src/views/admin/FormBuilder.vue`). However, this component acts mostly as a host. Its template is very minimal:

```html
<div id="c-admin" class="form-builder cognito">
    <div id="c-forms-build" class="form-builder__container c-app-container">
        <div id="buildContent" ref="buildContent" class="form-builder__content"></div>
    </div>
</div>
```

Its main responsibility is to dynamically load a series of legacy JavaScript files (like `build.js`) and templates, and then kick off the initialization process by calling `initBuildPage()`.

## 2. The Core UI Structure (`build.htm`)

The actual HTML skeleton for the builder is defined in `Cognito.Services/Views/Shared/build.htm`. This file defines the three main panels of the builder interface:

-   **Settings / Inspector Pane (`#c-forms-settings`)**: The right-hand sidebar. It contains templates for all possible field settings (e.g., Label, Placeholder Text, Required, etc.). These are dynamically shown or hidden based on the currently selected field.
-   **Main Canvas / Layout Pane (`#c-forms-layout`)**: The central area where the form itself is rendered. This area is made interactive and sortable by the `Sortable` JavaScript library.
-   **Add Field Palette (`#c-forms-palette`)**: The left-hand sidebar that contains all available fields that can be dragged onto the canvas.

## 3. The Logic: `build.js` and `Cognito.Forms`

The file `Cognito.Services/Views/Shared/build.js` contains the core client-side logic that powers the builder.

-   **`Cognito.Forms.initBuilder()`**: This is the main initialization function. It takes the form model and uses jQuery to bind all the necessary event handlers for dragging, dropping, selecting, and editing fields.
-   **`elementTypes` Object**: A large object within `build.js` defines the metadata for every field type (Textbox, Name, Choice, Section, etc.). This object is used to populate the **Add Field Palette**.
-   **Dynamic Settings**: When a field on the canvas is clicked, the `selectElement` function is called. This function sets the `currentElement` global variable. The HTML in the **Settings Inspector** uses a legacy data-binding syntax (`sys:if`, `sys:attach="dataview"`) to react to the change and show only the settings relevant to the `currentElement`'s type.

## Summary of Interaction

1.  `FormBuilder.vue` loads and calls `initBuildPage`.
2.  `initBuildPage` deserializes the form data and calls `Cognito.Forms.initBuilder()`.
3.  `initBuilder` populates the **Palette** from the `elementTypes` object.
4.  It renders the fields from the form model onto the **Canvas**.
5.  It attaches `Sortable` for drag-and-drop functionality.
6.  When a user clicks a field on the canvas, the **Settings Inspector** dynamically updates to show the relevant options for that field type.