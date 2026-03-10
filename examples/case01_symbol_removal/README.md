# Case 01: Symbol Removal

**Risk:** 🔴 BREAKING | **Category:** Symbol API | **Verdict:** 🔴 BREAKING

## What breaks
Any downstream binary that calls `helper()` will fail to link (or crash at runtime
with `undefined symbol`) after upgrading to v2. Statically-linked consumers that
captured the old address will call garbage. Even if *you* no longer use `helper()`,
removing it from the public `.so` is an ABI contract violation.

## Why abidiff catches it
abidiff reports `1 Removed function` and sets exit-bit 3 (value 8), giving exit code
**12** (= 4 | 8): *ABI change detected + breaking change*.

## Code diff

| v1.c | v2.c |
|------|------|
| `int compute(int x) { return x * 2; }` | `int compute(int x) { return x * 2; }` |
| `int helper(int x)  { return x + 1; }` | *(removed)* |

## Reproduce manually
```bash
gcc -shared -fPIC -g v1.c -o libfoo_v1.so
gcc -shared -fPIC -g v2.c -o libfoo_v2.so
abidw --out-file v1.xml libfoo_v1.so
abidw --out-file v2.xml libfoo_v2.so
abidiff v1.xml v2.xml
echo "exit: $?"   # → 12
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
# compute(5) = 10
# helper(5)  = 6

# Step 2: swap in v2 (no recompile)
gcc -shared -fPIC -g v2.c -o libfoo.so
./app
# Output:
# ./app: symbol lookup error: ./app: undefined symbol: helper
```

**Why:** `helper` is called by the binary but removed from v2's dynamic symbol table; the dynamic linker refuses to load the program — immediate hard crash at startup.

## How to fix
Never remove a public symbol in a minor/patch release. Deprecate with
`__attribute__((deprecated("use compute() instead")))` and only remove on the next
**SONAME bump** (major version).

## Real-world example
Common in C libraries during "API cleanup" refactors — OpenSSL 1.1.0 removed several
low-level functions that were technically public, forcing all downstream packages to
patch at once.
