# Case 04: No Change

**Category:** Symbol API | **Verdict:** ✅ NO_CHANGE (exit 0)

## What breaks
Nothing. Recompiling with the same source produces a bit-for-bit equivalent ABI.
This case confirms the baseline toolchain works correctly.

## Why abidiff catches it
abidiff exits **0** — no differences in the ABI XML representation.

## Code (identical both versions)
```c
int stable_api(int x) { return x; }
```

## Reproduce manually
```bash
gcc -shared -fPIC -g v1.c -o libfoo_v1.so
gcc -shared -fPIC -g v1.c -o libfoo_v2.so   # same source
abidw --out-file v1.xml libfoo_v1.so
abidw --out-file v2.xml libfoo_v2.so
abidiff v1.xml v2.xml
echo "exit: $?"   # → 0
```

## Real Failure Demo

**Severity: INFORMATIONAL (baseline — no failure)**

**Scenario:** compile `app` against v1, run with the same v1 `.so` (no v2 in this case).

```bash
# Build and run
gcc -shared -fPIC -g v1.c -o libfoo.so
gcc -g app.c -L. -lfoo -Wl,-rpath,. -o app
./app
# Output:
# stable_api(42) = 42 (expected 42)
# OK — baseline: works correctly
```

**Why:** No ABI change means no misbehavior — this case is the reference "green" baseline showing that identical source produces identical runtime behavior.

## How to fix
N/A — this is the ideal state for patch releases.

## Real-world example
CI pipelines that run abidiff on every PR use this as the baseline to catch
regressions: any non-zero exit from abidiff triggers a review gate.
