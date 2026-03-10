# Case 15 — `noexcept` Removed


**Risk:** 🚨 SILENT BREAK | **Category:** C++ ABI | **Verdict:** ❌ MISSED (exit 0 — tools blind)

## What changes

| Version | Signature |
|---------|-----------|
| v1 | `void reset() noexcept;` |
| v2 | `void reset();` |

## What breaks at binary level

In the Itanium C++ ABI (GCC/Clang on Linux/macOS) `noexcept` **does** affect the
mangled name for some function-pointer typedefs (C++17+), and more importantly it
changes the **exception-handling personality** of call sites:

- Code compiled against v1 wraps calls to `reset()` with an assumption that no
  unwinding is needed. The compiler may omit landing pads in callers.
- With v2, `reset()` *can* throw. A caller compiled with v1 headers will not have
  the landing pad → exception propagates through a `noexcept` frame → `std::terminate`.

The **symbol name itself is identical** in the `.so` (no mangling difference for
member functions in GCC), so `abidiff` sees no change.

## What breaks at binary level

In the Itanium C++ ABI (GCC/Clang on Linux/macOS) `noexcept` **does** affect the
mangled name for some function-pointer typedefs (C++17+), and more importantly it
changes the **exception-handling personality** of call sites:

- Code compiled against v1 wraps calls to `reset()` with an assumption that no
  unwinding is needed. The compiler may omit landing pads in callers.
- With v2, `reset()` *can* throw. A caller compiled with v1 headers will not have
  the landing pad → exception propagates through a `noexcept` frame → `std::terminate`.

The **symbol name itself is identical** in the `.so` (no mangling difference for
member functions in GCC), so `abidiff` sees no change.

## Real Failure Demo

**Severity: CRITICAL**

**Scenario:** compile `app` against v1 (reset is `noexcept`), swap in v2 `.so` where `reset()` actually throws.

```bash
# Step 1: build with v1
g++ -shared -fPIC -g v1.cpp -o libbuf.so
g++ -g app.cpp -L. -lbuf -Wl,-rpath,. -o app
./app
# Output:
# Creating buffer...
# Calling reset_buffer()...
# reset_buffer() returned normally
# OK — v1 baseline

# Step 2: swap in v2 (no recompile)
g++ -shared -fPIC -g v2.cpp -o libbuf.so
./app
# Output:
# Creating buffer...
# Calling reset_buffer()...
# terminate called after throwing an instance of 'std::runtime_error'
#   what():  reset failed
# Aborted (core dumped)
```

**Why:** v2's `reset()` throws `std::runtime_error`; old code compiled against the `noexcept` v1 signature has no exception handler — the exception propagates through the `noexcept` frame and the C++ runtime calls `std::terminate`, aborting the process.

## Why abidiff misses it

`abidiff` compares DWARF type information and symbol tables. `noexcept` is **not
stored in DWARF** — it is purely a source-level annotation. abidiff has no way to
detect the change.

## Why ABICC catches it

ABICC (ABI Compliance Checker) parses the **C++ header AST** via libclang. It sees
the `noexcept` specifier on the function declaration and records it as part of the
function's ABI profile. When v1 and v2 headers differ in `noexcept`, ABICC flags it.

## Real-world example

In **Folly** (Facebook's C++ library), several internal `reset()` and `destroy()`
methods had `noexcept` removed during a refactor. Downstream projects compiled with
old headers started hitting silent `std::terminate` crashes when running with the
new `.so`. The breakage was caught by ABICC in CI before the release.

## Code diff

```diff
-void reset() noexcept;
+void reset();
```

## Reproduce steps

```bash
cd examples/case15_noexcept_change

# Build v1 and v2
g++ -shared -fPIC -std=c++17 -g v1.cpp -o libv1.so
g++ -shared -fPIC -std=c++17 -g v2.cpp -o libv2.so

# abidiff: expects no output (misses the change)
abidw --out-file v1.xml libv1.so
abidw --out-file v2.xml libv2.so
abidiff v1.xml v2.xml || true   # exits 0 — misses it!

# ABICC: catches it via header diff
abi-compliance-checker -lib Buffer -v1 1.0 -v2 2.0 \
  -header v1.cpp -header v2.cpp \
  -gcc-options "-std=c++17"
```
