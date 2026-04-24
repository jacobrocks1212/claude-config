---
name: rust-best-practices
description: A comprehensive guide to modern Rust best practices covering style, error handling, performance, concurrency, project organization, dependency management, documentation, testing, security, and CI.
---

# Rust Best Practices Guide

## General Coding Conventions and Style

- **Use Standard Naming Conventions:** Type names use `UpperCamelCase`, functions/variables use `snake_case`, constants use `SCREAMING_SNAKE_CASE`. Use `Uuid` not `UUID`.

- **Code Formatting with rustfmt:** Use 4 spaces for indentation, keep line width under 100 chars. Run `cargo fmt -- --check` in CI.

- **Idiomatic Expressions:** Favor expressions over intermediate variables. Leverage iterators and ownership. Use `///` doc comments for public items.

- **Consistent Project Structure:** Use Cargo's idiomatic layout. Keep most code in library crates with minimal `main.rs`. Use workspaces for multi-crate projects.

## Error Handling Best Practices

- **Prefer `Result` for Recoverable Errors:** Functions that can fail should return `Result`. Use `?` to propagate errors.

- **Guidelines on `panic!` vs `Result`:** Only `panic!` for unrecoverable errors or invariant violations. Library code should never panic on expected conditions.

- **Use Error Types and Context:**
  - Libraries: Use `thiserror` for custom error types
  - Applications: Use `anyhow` for convenience with `.context()` for rich error messages

```rust
use thiserror::Error;

#[derive(Error, Debug)]
pub enum ConfigError {
    #[error("I/O error while reading config: {0}")]
    Io(#[from] std::io::Error),
    #[error("Invalid number in config: {0}")]
    Parse(#[from] std::num::ParseIntError),
}
```

## Performance Optimization

- **Zero-Cost Abstractions:** Trust Rust's optimizations. Iterators compile to the same code as hand-written loops.

- **Memory Management:** Prefer stack allocation and contiguous structures (`Vec` over `LinkedList`). Use `&T` instead of cloning. Use `Arc<Mutex<T>>` for thread-safe sharing.

- **Inlining:** Use `#[inline]` on hot small functions. Use `#[cold]` on error paths. Always benchmark after changes.

- **Benchmarking:** Use Criterion for benchmarks. Profile with `perf`, `cargo flamegraph`, or similar tools.

## Concurrency and Async

- **Fearless Concurrency:** `Send` = safe to transfer between threads, `Sync` = safe to share references. Prefer message passing over shared state.

- **Threads and Synchronization:** Use `std::thread::spawn`, `Mutex<T>`, `RwLock<T>`. Prefer channels (`mpsc`) for communication.

- **Async Programming:** Use Tokio (de facto standard) or async-std. Never block inside async functions—use `spawn_blocking` for blocking work.

```rust
// Proper async channel usage
use tokio::sync::mpsc;

let (tx, mut rx) = mpsc::channel(32);
tokio::spawn(async move {
    while let Some(msg) = rx.recv().await {
        // process
    }
});
```

## Project Structure

- **Crates and Packages:** Separate concerns with multiple crates. Keep most code in library crates.

- **Modules and Visibility:** Use `mod` for organization. Default private, explicit `pub`. Use `pub(crate)` for internal helpers.

- **File Organization:** Follow Cargo conventions. Use either `mod.rs` or flat file approach consistently.

## Dependency Management

- **Cargo.toml Best Practices:** Pin versions, respect semver. Check in `Cargo.lock` for binaries. Run `cargo update` regularly.

- **Use Features for Optional Dependencies:** Mark deps as `optional = true` and group under named features.

- **Avoid Dependency Bloat:** Use `cargo tree` to audit. Disable unused default features.

- **Workspaces:** Use for multi-crate projects to share `Cargo.lock` and build settings.

## Documentation and Testing

- **Write Rustdoc:** Every public item needs `///` docs. Include examples in doc comments (they become tests).

- **Document Panics, Errors, Safety:** Use `# Panics`, `# Errors`, `# Safety` sections.

- **Testing Strategies:** Unit tests in `#[cfg(test)] mod tests`. Integration tests in `tests/` directory.

```rust
/// Parses a percentage string (e.g. "42%") into a number (0-100).
///
/// # Errors
/// Returns an error if not in format "<number>%" or if out of range.
///
/// # Examples
/// ```
/// let val = parse_percentage("75%").unwrap();
/// assert_eq!(val, 75);
/// ```
pub fn parse_percentage(input: &str) -> Result<u8, String> {
    // implementation
}
```

## Security and Safety

- **Avoid `unsafe` Where Possible:** Mark as `unsafe` only when necessary. Encapsulate behind safe abstractions.

- **Follow Unsafe Code Guidelines:** Document safety requirements. Minimize `unsafe` block size. Use Miri for testing.

- **Clippy Lints:** Run `cargo clippy` regularly. Treat warnings as errors in CI: `cargo clippy -- -D warnings`.

- **Security Audits:** Use `cargo audit` for vulnerability scanning. Keep dependencies updated.

## CI Practices

**Minimum CI Pipeline:**
```yaml
- cargo build --all --verbose
- cargo clippy --all-targets --all-features -- -D warnings
- cargo test --all --verbose
- cargo fmt -- --check
- cargo audit
```

- Test on MSRV and stable Rust
- Run `cargo doc` to verify documentation builds
- Consider fuzzing with `cargo fuzz` for critical code

## Quick Reference

| Task | Command |
|------|---------|
| Format code | `cargo fmt` |
| Lint | `cargo clippy -- -D warnings` |
| Test all | `cargo test` |
| Audit deps | `cargo audit` |
| Update deps | `cargo update` |
| Check formatting | `cargo fmt -- --check` |
| Build release | `cargo build --release` |
| View dep tree | `cargo tree` |
