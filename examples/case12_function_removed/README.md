# Case 12: Function Disappears (Moved to Inline)

**Category:** Symbol API | **Verdict:** 🔴 BREAKING (exit 12)

## What breaks
Any binary dynamically linked against v1 will fail to load with
`undefined symbol: fast_add` when upgraded to v2. Even if the function is still
available as an inline in a header, the `.so` no longer exports the symbol,
so pre-built binaries have nowhere to resolve it.

## Why abidiff catches it
Reports `1 Removed function: fast_add` with exit **12** (breaking removal).

## Code diff

| v1.c | v2.c |
|------|------|
| `int fast_add(int a, int b) { return a+b; }` | *(function removed from .so)* |
| | `int other_func(int x) { return x; }` |

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

**Scenario:** compile `app` against v1 (has `fast_add` and `other_func`), swap in v2 `.so` which removed `fast_add`.

```bash
# Step 1: build with v1
gcc -shared -fPIC -g v1.c -o libfoo.so
gcc -g app.c -L. -lfoo -Wl,-rpath,. -o app
./app
# Output:
# fast_add(3,4)  = 7
# other_func(5)  = 15

# Step 2: swap in v2 (no recompile)
gcc -shared -fPIC -g v2.c -o libfoo.so
./app
# Output:
# ./app: symbol lookup error: ./app: undefined symbol: fast_add
```

**Why:** `fast_add` was moved to a header-only inline in v2 and removed from the `.so`'s dynamic symbol table; any pre-built binary that calls it gets an immediate load-time symbol lookup failure.

## How to fix
Keep the exported wrapper in the `.so` even if the implementation moves to an inline.
The wrapper can simply call the inline: `int fast_add(int a, int b) { return _fast_add_impl(a,b); }`.
Only remove it on a SONAME-bumping major release.

## Real-world example
Several C++ standard library implementors have moved functions to inlines for
performance and then had to keep exported stubs for ABI compatibility — libstdc++'s
`std::string` refactor in GCC 5 is the canonical cautionary tale.
