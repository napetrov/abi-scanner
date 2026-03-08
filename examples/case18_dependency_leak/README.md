# Case 18 — Dependency ABI Leak

## What changes

`libfoo` itself is **source-identical** between v1 and v2.
The breaking change is in `ThirdPartyHandle`, a type from a third-party library
that `libfoo` **exposes in its public header**.

| Version | `ThirdPartyHandle` layout |
|---------|--------------------------|
| v1 | `{ int x; }` → sizeof = 4 bytes |
| v2 | `{ int x; int y; }` → sizeof = 8 bytes |

## What breaks at binary level

A caller compiled with v1 headers allocates `ThirdPartyHandle h = {42}` — 4 bytes.
It passes `&h` to `process()`. The v2 `.so` was compiled with the new layout and
may access `h->y` (at offset 4) — reading garbage or unmapped memory.

Even if `libfoo` itself doesn't access `y`, the caller's `sizeof(ThirdPartyHandle)`
mismatch means array indexing is wrong:
```c
ThirdPartyHandle arr[10];  // caller: 40 bytes total
                            // library: expects 80 bytes (10 × 8)
```

**libfoo.so is byte-for-byte identical** in both scenarios. Only the headers changed.
`nm`, `readelf`, and naive `abidiff` see no difference in the `.so`.

# Case 18 — Dependency ABI Leak

## What changes

`libfoo` itself is **source-identical** between v1 and v2.
The breaking change is in `ThirdPartyHandle`, a type from a third-party library
that `libfoo` **exposes in its public header**.

| Version | `ThirdPartyHandle` layout |
|---------|--------------------------|
| v1 | `{ int x; }` → sizeof = 4 bytes |
| v2 | `{ int x; int y; }` → sizeof = 8 bytes |

## What breaks at binary level

A caller compiled with v1 headers allocates `ThirdPartyHandle h = {42}` — 4 bytes.
It passes `&h` to `process()`. The v2 `.so` was compiled with the new layout and
may access `h->y` (at offset 4) — reading garbage or unmapped memory.

Even if `libfoo` itself doesn't access `y`, the caller's `sizeof(ThirdPartyHandle)`
mismatch means array indexing is wrong:
```c
ThirdPartyHandle arr[10];  // caller: 40 bytes total
                            // library: expects 80 bytes (10 × 8)
```

**libfoo.so is byte-for-byte identical** in both scenarios. Only the headers changed.
`nm`, `readelf`, and naive `abidiff` see no difference in the `.so`.

## Real Failure Demo

**Severity: CRITICAL**

**Scenario:** compile `app` against v1 headers (`ThirdPartyHandle` = 4 bytes), swap in v2 `.so` that reads `h.y` from uninitialized memory.

```bash
# Step 1: build with v1
gcc -shared -fPIC -g libfoo_v1.c -I. -o libfoo.so
gcc -g app.c -I. -L. -lfoo -Wl,-rpath,. -o app
./app
# Output:
# Sending h={x=42} (4 bytes) to process()
# process: x=42
# get_value() = 42 (expected 42)
# OK — v1 baseline

# Step 2: swap in v2 (no recompile)
gcc -shared -fPIC -g libfoo_v2.c -I. -o libfoo.so
./app
# Output:
# Sending h={x=42} (4 bytes) to process()
# process: x=42 y=32764          ← reads garbage past app's 4-byte struct
# get_value() = 32806 (expected 42)
# WRONG: v2 library read h.y from uninitialized memory past the struct!
```

**Why:** App allocates only 4 bytes for `ThirdPartyHandle` (v1 layout); v2's `process()` and `get_value()` read `h.y` at offset 4 — returning whatever garbage bytes follow on the stack, silently producing wrong results.

## Why abidiff may catch it (with DWARF)

If `libfoo` is compiled with `-g`, DWARF records `ThirdPartyHandle`'s layout.
`abidiff` comparing v1 and v2 `.so` files would detect the type size change — but
**only if the third-party type is transitively included in the DWARF** of `libfoo.so`.
Many distributions strip debug info, making this invisible to abidiff.

## Why ABICC catches it

ABICC processes all headers transitively, including `thirdparty.h`. It computes AST
diffs across the entire header graph. When `ThirdPartyHandle` changes size, ABICC
reports it as a type layout change that affects the ABI of `libfoo`'s exported functions.

## Real-world example

**Intel oneDAL** includes `tbb::task_arena` (a TBB type) in some public headers.
When Intel TBB changed `task_arena`'s internal layout in TBB 2021.3, oneDAL's ABI
broke for users who had TBB 2021.2 installed. The `.so` files hadn't changed.

**Protocol Buffers (protobuf)**: Several gRPC components include `grpc::Status` which
internally holds `std::string`. When libstdc++ changed `std::string` ABI (GCC 5.x,
CXX11 ABI), all libraries exposing `grpc::Status` in their public headers broke
silently. This is why Abseil and gRPC now use opaque handle types.

## Best practice

> **Never expose implementation-detail types in your public API headers.**

Use the **Pimpl idiom** or **opaque handles**:

```c
/* BAD: ThirdPartyHandle leaks into public API */
void process(ThirdPartyHandle* h);

/* GOOD: opaque handle — caller never sees ThirdPartyHandle */
typedef struct foo_handle foo_handle_t;
foo_handle_t* foo_create(int x);
void          foo_process(foo_handle_t* h);
void          foo_destroy(foo_handle_t* h);
```

See also the **Dependency ABI Leaks** section in `examples/README.md`.

## Code diff

```diff
-/* thirdparty.h v1 */
-typedef struct { int x; } ThirdPartyHandle;

+/* thirdparty.h v2 */
+typedef struct { int x; int y; } ThirdPartyHandle;  /* struct grew */

 /* foo.h — unchanged source */
 void process(ThirdPartyHandle* h);
```

## Reproduce steps

```bash
cd examples/case18_dependency_leak

# Build libfoo v1 and v2 (source identical, different thirdparty headers)
gcc -shared -fPIC -g libfoo_v1.c -I. -o libfoo_v1.so
gcc -shared -fPIC -g libfoo_v2.c -I. -o libfoo_v2.so

# Compare the .so files — they look identical at symbol level
nm --dynamic libfoo_v1.so
nm --dynamic libfoo_v2.so
diff <(nm --dynamic libfoo_v1.so) <(nm --dynamic libfoo_v2.so) || true

# abidiff WITH DWARF may catch ThirdPartyHandle layout change
abidw --out-file foo_v1.xml libfoo_v1.so
abidw --out-file foo_v2.xml libfoo_v2.so
abidiff foo_v1.xml foo_v2.xml || true

# ABICC catches via transitive header AST diff
abi-compliance-checker -lib libfoo -v1 1.0 -v2 2.0 \
  -header foo_v1.h -header foo_v2.h \
  -include-path . \
  -gcc-options "-I."
```
