---
name: rust-errors
description: Rust to TypeScript error handling patterns for Tauri apps. Use when defining Rust errors that will be passed to TypeScript, handling Tauri command errors, or creating discriminated union error types.
---

# Rust to TypeScript Error Handling

## Discriminated Union Pattern for Errors

When passing errors from Rust to TypeScript through Tauri commands, use internally-tagged enums to create discriminated unions that TypeScript can handle naturally.

### Rust Error Definition

```rust
use serde::{Deserialize, Serialize};
use thiserror::Error;

#[derive(Error, Debug, Serialize, Deserialize)]
#[serde(tag = "name")]
pub enum TranscriptionError {
    #[error("Audio read error: {message}")]
    AudioReadError { message: String },

    #[error("GPU error: {message}")]
    GpuError { message: String },

    #[error("Model load error: {message}")]
    ModelLoadError { message: String },

    #[error("Transcription error: {message}")]
    TranscriptionError { message: String },
}
```

### Key Rust Patterns

1. **Use internally tagged enums**: `#[serde(tag = "name")]` creates a discriminator field
2. **Follow naming conventions**: Enum variants should be PascalCase
3. **Include structured data**: Each variant can have fields like `message: String`
4. **Single-variant enums are okay**: Use when you want consistent error structure

```rust
// Single-variant enum for consistency
#[derive(Error, Debug, Serialize, Deserialize)]
#[serde(tag = "name")]
enum ArchiveExtractionError {
    #[error("Archive extraction failed: {message}")]
    ArchiveExtractionError { message: String },
}
```

### TypeScript Error Handling

```typescript
import { type } from 'arktype';

// Define the error type to match Rust serialization
const TranscriptionErrorType = type({
	name: "'AudioReadError' | 'GpuError' | 'ModelLoadError' | 'TranscriptionError'",
	message: 'string',
});

// Use in error handling
const result = await tryAsync({
	try: () => invoke('transcribe_audio_whisper', params),
	catch: (unknownError) => {
		const result = TranscriptionErrorType(unknownError);
		if (result instanceof type.errors) {
			// Handle unexpected error shape
			return WhisperingErr({
				title: 'Unexpected Error',
				description: extractErrorMessage(unknownError),
				action: { type: 'more-details', error: unknownError },
			});
		}

		const error = result;
		// Now we have properly typed discriminated union
		switch (error.name) {
			case 'ModelLoadError':
				return WhisperingErr({
					title: 'Model Loading Error',
					description: error.message,
					action: {
						type: 'more-details',
						error: new Error(error.message),
					},
				});

			case 'GpuError':
				return WhisperingErr({
					title: 'GPU Error',
					description: error.message,
					action: {
						type: 'link',
						label: 'Configure settings',
						href: '/settings/transcription',
					},
				});

			// Handle other cases...
		}
	},
});
```

### Serialization Format

The Rust enum serializes to this TypeScript-friendly format:

```json
// AudioReadError variant
{ "name": "AudioReadError", "message": "Failed to decode audio file" }

// GpuError variant
{ "name": "GpuError", "message": "GPU acceleration failed" }
```

### Best Practices

1. **Consistent error structure**: All errors have the same shape with `name` and `message`
2. **TypeScript type safety**: Use runtime validation with arktype to ensure type safety
3. **Exhaustive handling**: Switch statements provide compile-time exhaustiveness checking
4. **Don't use `content` attribute**: Avoid `#[serde(tag = "name", content = "data")]` as it creates nested structures
5. **Keep enums private when possible**: Only make public if used across modules

---

### AlgoBooth House Convention (project-specific — do NOT use `tag = "name"` there)

> **AlgoBooth (`~/repos/AlgoBooth`) uses `tag = "kind"`, not `tag = "name"`.** The generic
> examples above use `tag = "name"` which is the generic skill default, but the AlgoBooth
> codebase has established `tag = "kind"` as its discriminant — used consistently in
> `agent/keychain.rs`, `agent/provider.rs`, `agent/mcp_client.rs`, and `agent/streaming.rs`.
>
> In AlgoBooth, use this shape instead:
>
> ```rust
> #[derive(Debug, thiserror::Error, serde::Serialize)]
> #[serde(tag = "kind", content = "message", rename_all = "snake_case")]
> pub enum CommandError {
>     // Tuple/unit variants (with content = "message"):
>     #[error("IO error: {0}")]
>     Io(String),
>
>     // Struct variants with real fields (omit content=):
>     #[error("Sample not found: pack={pack}, index={index}")]
>     SampleNotFound { pack: String, index: u32 },
> }
> ```
>
> TypeScript discriminates on `kind` (snake_case), not `name`:
>
> ```typescript
> switch (error.kind) {
>     case 'io': /* ... */ break;
>     case 'sample_not_found': /* error.pack, error.index */ break;
> }
> ```
>
> The `CommandError` enum migration is documented in
> `docs/bugs/tauri-commands-string-errors/SPEC.md`. This convention was ratified 2026-06-05
> to align with the four existing `agent/` error enums and avoid re-deriving the conflict on
> future migrations.
>
> **Derive caveat (discovered 2026-06-05 — load-bearing).** The `#[serde(tag = "kind",
> content = "message")]` *derive* CANNOT produce the locked wire shape when an enum MIXES
> message-bearing variants (`{ kind, message }`) with struct variants whose fields must be
> FLATTENED alongside the tag (`{ kind: "sample_not_found", pack, index }`, no `message`
> wrapper). Adjacent tagging nests struct fields under `content` (`{ kind, message: { pack } }`)
> and internal tagging (`tag` only) can't serialize a newtype variant holding a plain `String`.
> When you need BOTH shapes from one enum, hand-write `impl serde::Serialize` (a `match` that
> emits `{ kind, message }` for message variants and a flattened map for struct variants) and
> keep `#[derive(thiserror::Error)]` for `Display`/`#[from]`. See
> `src-tauri/src/commands/error.rs` for the reference implementation.

### Anti-Patterns to Avoid

```rust
// DON'T: External tagging (default behavior)
#[derive(Serialize)]
pub enum BadError {
    ModelLoadError { message: String }
}
// Produces: { "ModelLoadError": { "message": "..." } }

// DON'T: Adjacent tagging with content
#[derive(Serialize)]
#[serde(tag = "type", content = "data")]
pub enum BadError {
    ModelLoadError { message: String }
}
// Produces: { "type": "ModelLoadError", "data": { "message": "..." } }

// DON'T: Manual Serialize implementation when derive works
impl Serialize for MyError {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        // Unnecessary complexity
    }
}
```

This pattern ensures clean, type-safe error handling across the Rust-TypeScript boundary with minimal boilerplate and maximum type safety.
