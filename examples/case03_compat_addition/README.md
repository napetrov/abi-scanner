# Case 03: Compatible Addition (New Export)

**Category:** Symbol API | **Verdict:** 🟢 COMPATIBLE (exit 4)

## What breaks
Nothing breaks in existing binaries — they never referenced `get_build()`. The exit
code is still **4** because abidiff reports an ABI *change* (addition); it is
compatible by convention.

## Why abidiff catches it
Reports `1 Added function: get_build()` with exit **4**. The absence of exit-bit 3
(value 8) means no breaking change.

## Code diff

| v1.c | v2.c |
|------|------|
| `int get_version(void) { return 1; }` | `int get_version(void) { return 1; }` |
| *(nothing)* | `int get_build(void) { return 42; }` |

## Reproduce manually
```bash
gcc -shared -fPIC -g v1.c -o libfoo_v1.so
gcc -shared -fPIC -g v2.c -o libfoo_v2.so
abidw --out-file v1.xml libfoo_v1.so
abidw --out-file v2.xml libfoo_v2.so
abidiff v1.xml v2.xml
echo "exit: $?"   # → 4 (compatible addition)
```

## Real Failure Demo

**Severity: INFORMATIONAL**

**Scenario:** compile `app` against v1, swap in v2 `.so` without recompile.

```bash
# Step 1: build with v1
gcc -shared -fPIC -g v1.c -o libfoo.so
gcc -g app.c -L. -lfoo -Wl,-rpath,. -o app
./app
# Output:
# version = 1 (expected 1)
# OK — no breakage, compatible addition

# Step 2: swap in v2 (no recompile)
gcc -shared -fPIC -g v2.c -o libfoo.so
./app
# Output:
# version = 1 (expected 1)
# OK — no breakage, compatible addition
```

**Why:** Adding a new exported symbol does not remove or change any existing symbol; binaries compiled against v1 continue to work identically with v2 — this is the textbook definition of a compatible ABI change.

## How to fix
No fix needed — this is the correct way to extend a library API. Just keep the SONAME
unchanged for compatible additions and bump it on breaking changes.

## Real-world example
glibc regularly adds new symbols (e.g., `reallocarray`, `explicit_bzero`) to minor
releases without bumping the SONAME, relying on this compatible-addition guarantee.
