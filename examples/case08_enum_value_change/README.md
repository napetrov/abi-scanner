# Case 08: Enum Value Change

**Category:** Type Layout | **Verdict:** 🟡 ABI CHANGE (exit 4)

> **Note on abidiff 2.4.0:** Returns exit **4**. Semantically breaking because
> code compiled against v1 uses hardcoded integer values (e.g., `if (c == 1)` for
> GREEN) that now mean YELLOW.

## What breaks
Any switch statement or comparison against `GREEN` (value 1) now hits the `YELLOW`
branch instead. Serialized data (files, network packets) using the old integer values
becomes misinterpreted.

## Why abidiff catches it
Reports `1 enumerator insertion: 'Color::YELLOW' value '1'` and two enumerator changes
for GREEN and BLUE.

## Code diff

| v1.c | v2.c |
|------|------|
| `{ RED=0, GREEN=1, BLUE=2 }` | `{ RED=0, YELLOW=1, GREEN=2, BLUE=3 }` |

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

**Scenario:** compile `app` against v1 (GREEN=1), swap in v2 `.so` where `get_signal()` now returns GREEN=2.

```bash
# Step 1: build with v1
gcc -shared -fPIC -g v1.c -o libfoo.so
gcc -g app.c -L. -lfoo -Wl,-rpath,. -o app
./app
# Output:
# get_color() = 0 → RED
# get_signal() = 1 → app interprets as: GREEN
# Signal: GREEN (correct)

# Step 2: swap in v2 (no recompile)
gcc -shared -fPIC -g v2.c -o libfoo.so
./app
# Output:
# get_color() = 0 → RED
# get_signal() = 2 → app interprets as: BLUE
# Signal: BLUE — WRONG! v2 shifted enum values, GREEN(2) looks like BLUE
```

**Why:** v2 inserted YELLOW=1, shifting GREEN from 1 to 2; old code compiled with GREEN=1 now misidentifies "green" signals as "blue" — silent wrong-branch execution with no crash or error.

## How to fix
Only append new enum values at the end (never insert). Mark the enum as "reserved
slots allowed" in documentation. Never renumber existing values.

## Real-world example
Protocol Buffers (protobuf) enforces append-only enum values for exactly this reason.
Inserting values in the middle is a common source of subtle bugs in versioned protocols.
