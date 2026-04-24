---
name: tauri-patterns
description: Tauri 2.0 desktop application patterns for Rust backend and TypeScript/Vue frontend. Use when building Tauri apps, IPC communication, window management, system tray, file system access, and native integrations.
triggers:
  - "src-tauri"
  - "tauri.conf.json"
  - "#[tauri::command]"
  - "@tauri-apps/api"
  - "invoke("
  - "emit("
  - "listen("
  - "tauri::State"
  - "WebviewWindow"
---

# Tauri Development Patterns

## When to Use This Skill
- Building Tauri desktop applications
- IPC between Rust backend and frontend
- Native system integrations (file system, notifications, tray)
- Window management and multi-window apps
- Plugin development and integration

## Project Structure
```
project/
├── src/                    # Frontend (Vue/React/etc)
├── src-tauri/
│   ├── Cargo.toml
│   ├── tauri.conf.json     # Tauri configuration
│   ├── capabilities/       # Permission capabilities
│   └── src/
│       ├── main.rs         # Entry point
│       ├── lib.rs          # Library exports
│       └── commands/       # IPC command handlers
```

## IPC Commands

### Rust Side - Defining Commands
```rust
// src-tauri/src/commands/mod.rs
use tauri::State;
use serde::{Deserialize, Serialize};

#[derive(Debug, Serialize, Deserialize)]
pub struct Project {
    pub id: String,
    pub name: String,
}

#[derive(Debug, Serialize)]
pub struct AppError {
    pub message: String,
    pub code: String,
}

// Simple command
#[tauri::command]
pub fn greet(name: &str) -> String {
    format!("Hello, {}!", name)
}

// Async command with Result
#[tauri::command]
pub async fn load_project(id: String) -> Result<Project, AppError> {
    // Async operations here
    Ok(Project { id, name: "My Project".into() })
}

// Command with state
#[tauri::command]
pub fn get_count(state: State<'_, AppState>) -> i32 {
    state.count.load(Ordering::SeqCst)
}

// Command with window access
#[tauri::command]
pub fn get_window_label(window: tauri::Window) -> String {
    window.label().to_string()
}
```

### Rust Side - Registering Commands
```rust
// src-tauri/src/lib.rs
mod commands;

use commands::*;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .invoke_handler(tauri::generate_handler![
            greet,
            load_project,
            get_count,
        ])
        .manage(AppState::default())
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
```

### TypeScript Side - Invoking Commands
```typescript
import { invoke } from '@tauri-apps/api/core';

// Simple invoke
const greeting = await invoke<string>('greet', { name: 'World' });

// With error handling
interface Project {
  id: string;
  name: string;
}

interface AppError {
  message: string;
  code: string;
}

async function loadProject(id: string): Promise<Project> {
  try {
    return await invoke<Project>('load_project', { id });
  } catch (error) {
    const appError = error as AppError;
    throw new Error(`${appError.code}: ${appError.message}`);
  }
}
```

## Events (Bidirectional Communication)

### Rust to Frontend
```rust
use tauri::Emitter;

// Emit to all windows
app_handle.emit("progress", ProgressPayload { percent: 50 })?;

// Emit to specific window
window.emit("file-changed", path)?;
```

### Frontend Listening
```typescript
import { listen, type UnlistenFn } from '@tauri-apps/api/event';

let unlisten: UnlistenFn;

onMounted(async () => {
  unlisten = await listen<{ percent: number }>('progress', (event) => {
    progress.value = event.payload.percent;
  });
});

onUnmounted(() => {
  unlisten?.();
});
```

### Frontend to Rust Events
```typescript
import { emit } from '@tauri-apps/api/event';

await emit('user-action', { action: 'save' });
```

## State Management (Rust)
```rust
use std::sync::atomic::{AtomicI32, Ordering};
use std::sync::Mutex;

pub struct AppState {
    pub count: AtomicI32,
    pub config: Mutex<Config>,
}

impl Default for AppState {
    fn default() -> Self {
        Self {
            count: AtomicI32::new(0),
            config: Mutex::new(Config::default()),
        }
    }
}

// In command
#[tauri::command]
pub fn increment(state: State<'_, AppState>) -> i32 {
    state.count.fetch_add(1, Ordering::SeqCst) + 1
}
```

## Window Management
```typescript
import { WebviewWindow } from '@tauri-apps/api/webviewWindow';
import { getCurrentWindow } from '@tauri-apps/api/window';

// Create new window
const webview = new WebviewWindow('settings', {
  url: '/settings',
  title: 'Settings',
  width: 600,
  height: 400,
});

// Current window operations
const mainWindow = getCurrentWindow();
await mainWindow.setTitle('New Title');
await mainWindow.minimize();
await mainWindow.center();
```

## File System (with plugin)
```typescript
import { readTextFile, writeTextFile } from '@tauri-apps/plugin-fs';
import { open, save } from '@tauri-apps/plugin-dialog';

// Open file dialog
const selected = await open({
  filters: [{ name: 'JSON', extensions: ['json'] }]
});

if (selected) {
  const content = await readTextFile(selected);
  const data = JSON.parse(content);
}

// Save file dialog
const savePath = await save({
  defaultPath: 'project.json',
});

if (savePath) {
  await writeTextFile(savePath, JSON.stringify(data));
}
```

## Capabilities (Tauri 2.0 Permissions)
```json
// src-tauri/capabilities/default.json
{
  "identifier": "default",
  "windows": ["main"],
  "permissions": [
    "core:default",
    "shell:allow-open",
    "fs:allow-read",
    "fs:allow-write",
    "dialog:allow-open",
    "dialog:allow-save"
  ]
}
```

## Error Handling Pattern
```rust
use thiserror::Error;
use serde::Serialize;

#[derive(Debug, Error, Serialize)]
pub enum CommandError {
    #[error("File not found: {0}")]
    FileNotFound(String),

    #[error("Permission denied")]
    PermissionDenied,

    #[error("Internal error: {0}")]
    Internal(String),
}

// Commands return Result<T, CommandError>
#[tauri::command]
pub async fn dangerous_operation() -> Result<(), CommandError> {
    // ...
}
```

## Critical Rules

1. **Always handle IPC errors on frontend** - Rust panics crash the app
2. **Use capabilities for permissions** - Principle of least privilege
3. **Clean up event listeners** - Prevent memory leaks
4. **Use async commands for I/O** - Don't block the main thread
5. **Serialize errors properly** - Implement Serialize for error types

## Common Plugins
- `@tauri-apps/plugin-shell` - Run external commands
- `@tauri-apps/plugin-fs` - File system access
- `@tauri-apps/plugin-dialog` - Native dialogs
- `@tauri-apps/plugin-notification` - System notifications
- `@tauri-apps/plugin-store` - Persistent key-value storage
