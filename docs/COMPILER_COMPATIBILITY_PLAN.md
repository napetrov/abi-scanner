# Compiler & CLI Compatibility Testing Plan

Testing compiler updates (like `icc` to `icx`, or `2025.x` updates) involves more than just shared library ABI. This document outlines the roadmap for comprehensive compiler compatibility tracking.

## 1. Runtime ABI Compatibility
*Currently implemented via `abi-scanner`.*
- **Scope:** Tracks exported symbols in runtime libraries (`libimf.so`, `libsvml.so`, `libiomp5.so`).
- **Tooling:** `abidw` to generate baselines, `abidiff` to compare.
- **Goal:** Catch missing symbols that would cause `symbol not found` errors during dynamic linking/loading.

## 2. CodeGen (Object) ABI Compatibility
- **Scope:** Tracks how the compiler lays out structs, mangles names, and passes arguments (Calling Conventions).
- **Tooling:** Compile a standardized, heavily-templated C++ test suite (e.g., portions of Boost or a custom reference project) into `.o` or `.so` files using *both* old and new compilers. Run `abidiff` on the resulting object files. Note: the standardized reference test suite must be compiled with debug symbols (e.g., `-g` or `-g3`) so `abidiff` can reconstruct type/layout info; running without `-g` will yield empty or misleading comparisons.
- **Goal:** Catch silent breakages where the new compiler expects a different memory layout for `std::string` or custom classes than the old compiler.

## 3. Source-Level (AST) API Compatibility
- **Scope:** Ensures old source code still compiles without new errors or unexpected deprecation warnings.
- **Tooling:** `libclang` (Python bindings) or `clang-query`.
- **Goal:** Parse AST to identify if macros, intrinsics, or Intel-specific pragmas (`#pragma ivdep`, `#pragma omp simd`) are dropped, ignored, or trigger new errors.

## 4. CLI Flag Compatibility
- **Scope:** Tracks changes in command-line arguments (e.g., `-fp-model`, `-xHOST`, `-O3`).
- **Tooling:** 
  1. Automated diff of `icx --help --help-hidden`.
  2. Dry-run execution: Pass a dictionary of known legacy flags to `icx -###` (driver dry-run mode) and parse the stderr for `warning: ignoring unknown option`.
- **Goal:** Prevent build system failures (e.g., CMake or Makefile scripts failing because a flag was removed).

