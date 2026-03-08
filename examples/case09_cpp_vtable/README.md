# Case 09: C++ Vtable Change

**Category:** C++ ABI | **Verdict:** 🟡 ABI CHANGE (exit 4)

> **Note on abidiff 2.4.0:** Returns exit **4** even though this is a hard vtable
> incompatibility. abidiff's text output explicitly notes:
> `"note that this is an ABI incompatible change to the vtable of class Widget"`.

## What breaks
The vtable is a hidden array of function pointers embedded in every `Widget` object.
Old code calls `widget->resize()` via vtable slot 1. After v2 inserts `recolor()` at
slot 1, that same call dispatches to `recolor()` instead — silent wrong behavior or
a crash.

## Why abidiff catches it
Reports `the vtable offset of method virtual int Widget::resize() changed from 1 to 2`
and labels it "ABI incompatible change to the vtable."

## Code diff

| v1.cpp | v2.cpp |
|--------|--------|
| `virtual int draw();` | `virtual int draw();` |
| `virtual int resize();` | `virtual int recolor();`  ← **inserted** |
| | `virtual int resize();` |

## Reproduce manually
```bash
g++ -shared -fPIC -g v1.cpp -o libwidget_v1.so
g++ -shared -fPIC -g v2.cpp -o libwidget_v2.so
abidw --out-file v1.xml libwidget_v1.so
abidw --out-file v2.xml libwidget_v2.so
abidiff v1.xml v2.xml
echo "exit: $?"   # → 4
```

## Real Failure Demo

**Severity: CRITICAL**

**Scenario:** compile `app` against v1 vtable layout, swap in v2 `.so` which has `recolor()` inserted at slot 1.

```bash
# Step 1: build with v1
g++ -shared -fPIC -g v1.cpp -o libwidget.so
g++ -g app.cpp -L. -lwidget -Wl,-rpath,. -o app
./app
# Output:
# draw()   = 10 (expected 10)
# resize() = 20 (expected 20)
# OK — resize() correct

# Step 2: swap in v2 (no recompile)
g++ -shared -fPIC -g v2.cpp -o libwidget.so
./app
# Output:
# draw()   = 10 (expected 10)
# resize() = 99 (expected 20)
# WRONG: resize() returned 99 — vtable slot 1 now points to recolor()!
#        v2 vtable: [draw=slot0, recolor=slot1, resize=slot2]
#        App called slot1 expecting resize(20), got recolor(99)
```

**Why:** The app's vtable call `slot[1]` is compiled in and cannot change without recompilation; v2 placed `recolor()` at slot 1, so every `widget->resize()` call silently dispatches to `recolor()` — wrong return value, potentially wrong side-effects.

## How to fix
Only append new virtual methods — never insert them in the middle of the vtable.
Alternatively, use the non-virtual interface (NVI) pattern: make only a few virtual
hooks, add non-virtual public methods that call them.

## Real-world example
Qt's strict "no vtable reordering" rule is documented in their ABI compatibility
policy. Binary-compatible Qt releases never insert virtual methods.
