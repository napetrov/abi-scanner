# Case 16 — Inline → Non-inline (ODR / Symbol Appearance)


**Risk:** 🚨 SILENT BREAK | **Category:** C++ ABI | **Verdict:** ❌ ODR violation, partly missed

## What changes

| Version | Where is `fast_hash`? |
|---------|----------------------|
| v1 | Header-only inline — callers have their own copy |
| v2 | Moved to `.so` — now an exported symbol |

## What breaks at binary level

**Scenario A — Stale callers (compiled with v1 header):**
The caller has `fast_hash` inlined. The v2 `.so` also has `fast_hash`. At link time,
the linker sees two definitions — caller's inlined copy and the `.so` export. Normally
the inline version "wins" locally. But if the implementation diverges between v1
(inlined) and v2 (in `.so`), results differ. This is an **ODR violation**.

**Scenario B — Fresh callers (compiled with v2 header, linked against v1 `.so`):**
The caller expects `fast_hash` as an imported symbol. But v1 `.so` has **no**
`fast_hash` symbol at all. Link fails with "undefined symbol: fast_hash".

In both scenarios the breakage is subtle and depends on build order.

# Case 16 — Inline → Non-inline (ODR / Symbol Appearance)

## What changes

| Version | Where is `fast_hash`? |
|---------|----------------------|
| v1 | Header-only inline — callers have their own copy |
| v2 | Moved to `.so` — now an exported symbol |

## What breaks at binary level

**Scenario A — Stale callers (compiled with v1 header):**
The caller has `fast_hash` inlined. The v2 `.so` also has `fast_hash`. At link time,
the linker sees two definitions — caller's inlined copy and the `.so` export. Normally
the inline version "wins" locally. But if the implementation diverges between v1
(inlined) and v2 (in `.so`), results differ. This is an **ODR violation**.

**Scenario B — Fresh callers (compiled with v2 header, linked against v1 `.so`):**
The caller expects `fast_hash` as an imported symbol. But v1 `.so` has **no**
`fast_hash` symbol at all. Link fails with "undefined symbol: fast_hash".

In both scenarios the breakage is subtle and depends on build order.

## Real Failure Demo

**Severity: CRITICAL**

**Scenario B:** compile `app` using `v2.hpp` (non-inline declaration), link against `libv1.so` (no `fast_hash` symbol).

```bash
# Inspect symbol tables
g++ -shared -fPIC -g v1.cpp -o libv1.so
g++ -shared -fPIC -g v2.cpp -o libv2.so
nm --dynamic libv1.so | grep fast_hash || echo "v1: no fast_hash symbol (correct — was inline)"
# Output: v1: no fast_hash symbol (correct — was inline)
nm --dynamic libv2.so | grep fast_hash
# Output: ... T _Z9fast_hashi

# Scenario B: compile with v2.hpp (non-inline) but link v1.so
g++ -g app.cpp -I. -L. -lv1 -Wl,-rpath,. -o app 2>&1 || true
# Output:
# undefined reference to `fast_hash(int)'
# collect2: error: ld returned 1 exit status

# Fix: link against v2.so — then it works
g++ -shared -fPIC -g v2.cpp -o libv1.so
g++ -g app.cpp -I. -L. -lv1 -Wl,-rpath,. -o app
./app
# Output: fast_hash(42) = -182847734
```

**Why:** Moving `fast_hash` from a header inline to the `.so` removes it from the compiler-emitted inline copies; any binary compiled with the new non-inline header that links against the old `.so` gets an undefined symbol error at link or load time.

## Why abidiff misses it

`abidiff` compares two `.so` files. v1 `.so` has **no** `fast_hash` symbol (it was
inline). v2 `.so` **adds** `fast_hash`. abidiff reports this as a new export, not a
breaking change. It cannot know that callers were compiled with the old inline version.

## Why ABICC catches it

ABICC parses both header ASTs. It sees `fast_hash` was `inline` in v1 and non-`inline`
in v2. This is a semantic change: the inline assumption is gone. ABICC flags:
> "Function 'fast_hash' changed: inline removed".

## Real-world example

In **abseil-cpp**, several string utility functions were moved from headers into the
`.so` during the monorepo refactor (2021). Users who pinned to old `.so` files but
updated their headers got linker errors. Some projects shipped both a header-inline
and a `.so` symbol — causing ODR violations with LTO builds.

## Code diff

```diff
-// v1.hpp
-inline int fast_hash(int x) {
-    return static_cast<int>(static_cast<unsigned>(x) * 2654435761U);
-}

+// v2.hpp
+int fast_hash(int x);   // declaration only

+// v2.cpp
+int fast_hash(int x) {  // now in .so
+    return static_cast<int>(static_cast<unsigned>(x) * 2654435761U);
+}
```

## Reproduce steps

```bash
cd examples/case16_inline_to_non_inline

# Build .so files
g++ -shared -fPIC -std=c++17 -g v1.cpp -o libv1.so
g++ -shared -fPIC -std=c++17 -g v2.cpp -o libv2.so

# Check symbol table
nm --dynamic libv1.so | grep fast_hash || echo "v1: no fast_hash symbol (expected)"
nm --dynamic libv2.so | grep fast_hash            # v2: symbol present

# abidiff: shows fast_hash as NEW addition (not a break)
abidw --out-file v1.xml libv1.so
abidw --out-file v2.xml libv2.so
abidiff v1.xml v2.xml || true

# ABICC: catches inline→non-inline semantic change
abi-compliance-checker -lib fast_hash -v1 1.0 -v2 2.0 \
  -header v1.hpp -header v2.hpp
```
