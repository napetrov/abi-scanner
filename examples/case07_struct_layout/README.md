# Case 07: Struct Layout Change

**Category:** Type Layout | **Verdict:** 🟡 ABI CHANGE (exit 4)

> **Note on abidiff 2.4.0:** Struct layout changes return exit **4** (not 12),
> but the change is **semantically breaking** — all callers allocate the old size
> and pass wrong-length data.

## What breaks
Code compiled against v1 allocates `sizeof(Point) = 8` bytes. v2's `Point` is 12
bytes. Stack/heap allocations are undersized; the `z` field reads/writes outside the
allocated region. Any binary passing `Point` by value is broken without recompilation.

## Why abidiff catches it
Reports `type size changed from 64 to 96 (in bits)` and `1 data member insertion`.

## Code diff

| v1.c | v2.c |
|------|------|
| `struct Point { int x; int y; };` | `struct Point { int x; int y; int z; };` |

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

**Scenario:** compile `app` against v1 (struct Point = 8 bytes), swap in v2 `.so` which calls `init_point()` writing 12 bytes.

```bash
# Step 1: build with v1
gcc -shared -fPIC -g v1.c -o libfoo.so
gcc -g app.c -L. -lfoo -Wl,-rpath,. -o app
./app
# Output:
# Before init_point: p={?,?} canary=0xDEADBEEF
# After  init_point: p={1,2} canary=0xDEADBEEF
# Canary intact (stack layout may have padded the gap — run with ASAN to confirm)
# get_x(&p) = 1 (expected 1)

# Step 2: swap in v2 (no recompile)
gcc -shared -fPIC -g v2.c -o libfoo.so
./app
# Output:
# *** stack smashing detected ***: terminated
# Aborted (core dumped)
```

**Why:** v2's `init_point()` writes a third field `z=3` at offset 8, past the 8-byte v1 allocation on the stack — corrupting the stack frame and triggering the compiler's stack-smashing protector.

## How to fix
Never add fields to public structs. Use the opaque-pointer (PIMPL) idiom: expose
`struct Point*` and allocate/free through library functions, so the struct layout
is hidden from callers.

## Real-world example
The Linux kernel uses opaque `struct task_struct*` for exactly this reason. Public
kernel API headers expose only opaque handles; layout is internal.
