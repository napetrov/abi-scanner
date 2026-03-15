# Case 02: Parameter Type Change

**Risk:** 🔴 BREAKING | **Category:** Symbol API | **Verdict:** 🔴 ABI CHANGE (exit 4)

> **Note on abidiff 2.4.0:** libabigail classifies parameter type changes as
> "indirect sub-type changes" with exit code **4** (ABI change detected, not
> flagged as *symbol-removal* breaking). The change is still real ABI drift and
> should be treated as BREAKING by policy.

## What breaks
Callers compiled against v1 pass `int a` in a 32-bit register; v2 expects `double a`
in an FP register (x86-64 SysV ABI). The argument is misread, producing wrong results
or a crash. Re-compilation against v2 is mandatory.

## Why abidiff catches it
Reports `parameter 1 of type 'int' changed: type name changed from 'int' to 'double'`
with exit **4**.

## Code diff

| v1.c | v2.c |
|------|------|
| `double process(int a, int b)` | `double process(double a, int b)` |

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

**Scenario:** compile `app` against v1, swap in v2 `.so` without recompile.

```bash
# Step 1: build with v1
gcc -shared -fPIC -g v1.c -o libfoo.so
gcc -g app.c -L. -lfoo -Wl,-rpath,. -o app
./app
# Output:
# Expected: 7.000000
# Got:      7.000000

# Step 2: swap in v2 (no recompile)
gcc -shared -fPIC -g v2.c -o libfoo.so
./app
# Output:
# WRONG RESULT — ABI mismatch (int vs double argument passing)
# Expected: 7.000000
# Got:      3.000000
```

**Why:** With v1 the caller passes `int 3` in a general-purpose register; v2 expects a `double` in an XMM register, so it reads an uninitialized XMM value — silently producing the wrong result with no error or signal.

## How to fix
Introduce a new function with the desired signature alongside the old one. Keep the
old symbol with its original signature for at least one deprecation cycle.

## Real-world example
Common in numerical libraries (BLAS, LAPACK) when precision is upgraded — `float` →
`double` parameter changes require wrapper shims for backward compatibility.
