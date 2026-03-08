# Case 11: Global Variable Type Change

**Category:** Type Layout | **Verdict:** 🟡 ABI CHANGE (exit 4)

> **Note on abidiff 2.4.0:** Returns exit **4**. Semantically breaking — the symbol
> size changes from 4 to 8 bytes; consumers that read it as `int` get only half the
> data on big-endian or the wrong bits on little-endian for large values.

## What breaks
Any binary that accesses `lib_version` as a 4-byte `int` now reads only half the
variable. On little-endian (x86), the low word happens to be correct for small values,
masking the bug — until `lib_version` exceeds `INT_MAX`.

## Why abidiff catches it
Reports `size of symbol changed from 4 to 8` and `type of variable changed: int → long int`.

## Code diff

| v1.c | v2.c |
|------|------|
| `int  lib_version = 1;` | `long lib_version = 1;` |

## Reproduce manually
```bash
gcc -shared -fPIC -g v1.c -o libfoo_v1.so
gcc -shared -fPIC -g v2.c -o libfoo_v2.so
abidw --out-file v1.xml libfoo_v1.so
abidw --out-file v2.xml libfoo_v2.so
abidiff v1.xml v2.xml
echo "exit: $?"   # → 4
```

## Real Failure Demo

**Severity: CRITICAL**

**Scenario:** compile `app` against v1 (`lib_version` is `int`), swap in v2 `.so` where `lib_version` is `long 5000000000`.

```bash
# Step 1: build with v1
gcc -shared -fPIC -g v1.c -o libfoo.so
gcc -g app.c -L. -lfoo -Wl,-rpath,. -o app
./app
# Output:
# lib_version = 1
# OK — v1 baseline

# Step 2: swap in v2 (no recompile)
gcc -shared -fPIC -g v2.c -o libfoo.so
./app
# Output:
# ./app: Symbol `lib_version' has different size in shared object, consider re-linking
# lib_version = 705032704
# WRONG READ: v2 lib_version=5000000000L, int reads low 32 bits → 705032704
```

**Why:** The app reads only 4 bytes from the 8-byte `long` symbol; on little-endian x86-64 it gets the low 32 bits (705032704 = 0x29A00000), silently returning a completely wrong version number — the dynamic linker even warns about the size mismatch.

## How to fix
Use a fixed-width type from the start (`int32_t`, `int64_t`, or `uint32_t`). If you
must change a global's type, introduce a new symbol with a new name and deprecate the
old one.

## Real-world example
The `errno` global in glibc is deliberately typed as `int` and will never change;
glibc uses `__thread int errno` internally but the public type is ABI-frozen.
