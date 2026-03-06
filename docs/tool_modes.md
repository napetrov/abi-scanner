# ABI Tool Modes Reference

This document explains the three complementary modes used for ABI analysis in
`abi-scanner`, when to use each, their requirements, and their limitations.

---

## Decision Flowchart

```
[Project policy] PUBLIC HEADERS are mandatory for analysis
│
├─ headers missing  → fail fast / fetch devel/include package first
│
└─ headers available
    │
    Was the .so compiled with -g (debug symbols) AND built with GCC?
    │
    ├─ NO (production/stripped .so, or icpx/clang build)
    │
    │   Use MODE 1 + MODE 2 (combined verdict)
    │   abidiff+headers for ELF-level + ABICC+headers for AST-level
    │   If either reports a break → treat as breaking
    │
    └─ YES (CI/staging GCC debug build)

        Use MODE 1 + MODE 3 (combined verdict)
        abidiff+headers + ABICC+dump for deepest type precision

                                              Review combined verdict
                                              Any break from any mode
                                              → flag release as ABI-breaking
```

---

## Mode 1: abidiff (libabigail)

### Overview

`abidiff` from the **libabigail** project compares two shared library (`.so`) files
directly. It reads the ELF symbol table for exported symbols and optionally reads
DWARF debug sections for type layout information.

### How it works

```
libv1.so ──► abidw --headers-dir include/ ──► v1.xml ──┐
                                                         ├──► abidiff ──► ABI report
libv2.so ──► abidw --headers-dir include/ ──► v2.xml ──┘
```

`abidw` serializes the ABI into XML; `--headers-dir` adds header context so abidiff
can resolve type names and catch layout changes even without full DWARF.

### Requirements

| Requirement | Mandatory? | Notes |
|-------------|-----------|-------|
| Two `.so` files | ✅ yes | Core input |
| Public headers (`--headers-dir`) | ✅ yes (our pipeline) | Greatly improves type resolution; we **always** pass headers |
| DWARF debug info (`-g`) | ❌ optional | Without it, type layout changes rely on headers alone |
| Compiler | ❌ no | Not needed |

### What it catches

- ✅ Symbol removal (function/variable removed from `.so`) → exit code 12
- ✅ Symbol type change in symbol table (ELF-level)
- ✅ Type layout changes — struct/class field addition, removal, reorder **with DWARF**
- ✅ vtable changes **with DWARF** (virtual method addition/removal/reorder)
- ✅ Return type changes **with DWARF**
- ✅ Parameter type changes **with DWARF**
- ✅ Global variable type/size changes **with DWARF**
- ✅ Enum value changes **with DWARF**
- ✅ Visibility changes (symbol hidden vs. default)

### What it misses

- ❌ `noexcept` specifier changes (no DWARF representation)
- ❌ `inline` → non-inline ODR changes (inline functions absent from `.so`)
- ❌ C++ `[[nodiscard]]`, `[[deprecated]]`, `explicit` attribute changes
- ❌ Template instantiation layout changes **without DWARF**
- ❌ Dependency ABI leaks (transitive header type changes) **without DWARF**
- ❌ C++ concepts / requires constraints
- ❌ Default argument changes

### Limitations

1. **Stripped production libraries** — most production `.so` files have DWARF
   stripped. abidiff degrades to symbol-table-only comparison, missing all type
   layout changes.
2. **C++ name mangling opacity** — abidiff can decode some mangled names but
   complex template signatures may produce confusing output.
3. **No header context** — abidiff cannot distinguish a deliberate API removal
   from an internal symbol cleanup.

### Exit codes

| Code | Meaning |
|------|---------|
| 0 | No ABI change |
| 4 | ABI change (type/layout diff, compatible addition) |
| 12 | Breaking change (symbol removed) |

### Usage

```bash
# Requires libabigail-tools
sudo apt-get install abigail-tools

# Always pass headers — improves type resolution significantly
abidw --headers-dir include/ --out-file v1.xml libv1.so
abidw --headers-dir include/ --out-file v2.xml libv2.so
abidiff v1.xml v2.xml
echo "Exit code: $?"
```

---

## Mode 2: ABICC Headers-Only

### Overview

**ABI Compliance Checker** (`abi-compliance-checker`, ABICC) with **headers only**
— no `abi-dumper`, no DWARF required. ABICC parses C/C++ headers using an internal
GCC-based frontend to build an AST and computes type layouts, function signatures,
and semantic attributes directly from source.

### How it works

```
libv1.so + v1 headers ──► ABICC AST parse ──┐
                                              ├──► semantic diff ──► compliance report
libv2.so + v2 headers ──► ABICC AST parse ──┘
```

The `.so` files are used only for the exported symbol list. Type information comes
entirely from the headers.

### Requirements

| Requirement | Mandatory? | Notes |
|-------------|-----------|-------|
| Two `.so` files | ✅ yes | For exported symbol list |
| Public headers | ✅ yes | Core input for type analysis |
| `abi-compliance-checker` | ✅ yes | `sudo apt-get install abi-compliance-checker` |
| GCC (header parse) | ✅ yes | Usually already installed |
| DWARF debug info | ❌ no | Not used in this mode |
| `abi-dumper` | ❌ no | Not used in this mode |

### What it catches

Everything Mode 1 catches, plus:

- ✅ `noexcept` specifier removal/addition
- ✅ `inline` → non-inline changes (ODR hazard)
- ✅ C++ template class layout changes (from AST)
- ✅ `explicit` constructor attribute changes
- ✅ `[[nodiscard]]` attribute changes
- ✅ Default argument changes
- ✅ `const` qualifier changes on methods
- ✅ Transitive header type changes (dependency ABI leaks)
- ✅ Macro-expanded type changes (if header includes expand correctly)

### What it misses

- ❌ ELF-only symbol visibility changes (without DWARF, can't distinguish hidden vs
  default if header doesn't reflect it)
- ❌ Complex `#ifdef` / platform-guarded type differences not covered by the
  configured compiler flags
- ❌ Deep template specialization edge cases without explicit instantiation hints
- ❌ ABI differences from link-time optimization (LTO) that don't appear in headers
- N/A for inline-only (header-only) APIs — no `.so` symbol to compare against

### Limitations

1. **Header completeness** — if your headers `#include` paths aren't provided via
   `-include-path`, transitive types may not resolve.
2. **Compiler-flag sensitivity** — `#ifdef __x86_64__` etc. may produce different
   ASTs on different platforms. Run on the target platform.
3. **Macro-expanded types** — `typedef HANDLE void*`-style platform macros may
   not be fully expanded, leading to false negatives.

### Usage

```bash
# Requires abi-compliance-checker
sudo apt-get install abi-compliance-checker

# Create XML spec files
cat > v1.xml << 'SPEC'
<version>1.0</version>
<headers>
  <directory>path/to/v1/include</directory>
</headers>
<libs>
  <lib>path/to/libv1.so</lib>
</libs>
SPEC

cat > v2.xml << 'SPEC'
<version>2.0</version>
<headers>
  <directory>path/to/v2/include</directory>
</headers>
<libs>
  <lib>path/to/libv2.so</lib>
</libs>
SPEC

abi-compliance-checker -lib MyLib -old v1.xml -new v2.xml
```

---

## Mode 3: ABICC Dump-Mode (with abi-dumper)

### Overview

**ABICC dump-mode** combines `abi-dumper` (which extracts detailed type information
from DWARF debug sections) with `abi-compliance-checker`. This is the most accurate
mode: DWARF is the ground truth for compiled types, capturing what macros and
`#ifdef`s actually resolved to at compile time.

### How it works

```
libv1.so (-g) ──► abi-dumper ──► v1.dump ──┐
                                             ├──► abi-compliance-checker ──► report
libv2.so (-g) ──► abi-dumper ──► v2.dump ──┘
```

`abi-dumper` serializes DWARF type trees into `.dump` files. `abi-compliance-checker`
diffs them semantically.

### Requirements

| Requirement | Mandatory? | Notes |
|-------------|-----------|-------|
| Two `.so` files with `-g` | ✅ yes | DWARF is the core input |
| `abi-dumper` | ✅ yes | `sudo apt-get install abi-dumper` |
| `abi-compliance-checker` | ✅ yes | Same as mode 2 |
| `universal-ctags` or `exuberant-ctags` | ✅ yes | Required by abi-dumper |
| `vtable-dumper` | ✅ yes | For C++ vtable extraction |
| Public headers | ❌ optional | Improves output; not strictly required |
| **GCC** | ✅ yes | **Only GCC is supported.** Intel compilers (icpx, icc) and Clang produce DWARF that abi-dumper cannot reliably parse. |

### What it catches

Everything Mode 2 catches, plus:

- ✅ Anonymous struct/union layouts (not expressible in headers, only in DWARF)
- ✅ Complex typedef chains resolved to actual underlying types
- ✅ Template instantiation details from DWARF (actual offsets, not AST estimates)
- ✅ Bit-field layouts at bit-level precision
- ✅ `#pragma pack` and compiler-attribute-modified layouts
- ✅ Types defined in `.c`/`.cpp` implementation files but leaked into ABI
- ✅ ABI differences caused by different compiler flags (e.g., `-m32` vs `-m64`)

### What it misses

- ❌ Inline-only (header-only) APIs — no DWARF for functions never compiled into `.so`
- ❌ ELF-only symbol visibility changes (same as mode 2)
- ❌ `noexcept` specifier (not in DWARF — same as abidiff)
- ❌ Changes in stripped production `.so` (requires `-g`)

### Why dump-mode is more accurate than headers-only

Headers can contain macros, `#ifdef`s, and platform guards that make the "true"
compiled type ambiguous. DWARF records what the compiler **actually** saw:

```c
// header says:
typedef INTERNAL_INT_TYPE my_int;

// INTERNAL_INT_TYPE might be int32_t or int64_t depending on platform
// Headers-only mode may guess wrong; DWARF records the actual resolved type
```

Additionally, anonymous types invisible in headers appear in DWARF:
```c
struct Foo {
    struct { int x; int y; };  // anonymous — no name in header
    int z;
};
```

### Limitations

> ⚠️ **Critical: GCC only.** `abi-dumper` is designed for GCC-compiled libraries.
> Intel compilers (`icpx`, `icc`) and Clang produce DWARF variants that abi-dumper
> cannot reliably parse. For Intel projects where the standard toolchain is `icpx`,
> this mode is **effectively unavailable** unless a parallel GCC build is maintained.
> This is the primary reason `abi-scanner` defaults to **Mode 1 + Mode 2** for Intel
> product scanning.

1. **Requires debug builds** — production `.so` files are usually stripped. This
   mode is typically available only for CI artifacts, staging, or debug builds.
2. **Large DWARF sections** — debug `.so` files can be 10–100× larger. Analysis
   takes significantly longer.
3. **Tool dependency chain** — `abi-dumper` + `vtable-dumper` + `ctags` must all
   be compatible versions.
4. **`noexcept` blind spot** — even with full DWARF, `noexcept` is not recorded.
   Use mode 2 (headers) to cover this.

### Usage

```bash
# Install full toolchain
sudo apt-get install abi-dumper abi-compliance-checker universal-ctags vtable-dumper

# Build .so files with debug info
g++ -shared -fPIC -g -Wl,-soname,libmylib.so.1 -o libmylib_v1.so src_v1.cpp
g++ -shared -fPIC -g -Wl,-soname,libmylib.so.1 -o libmylib_v2.so src_v2.cpp

# Dump ABI from DWARF
abi-dumper libmylib_v1.so -o v1.dump -lver 1.0
abi-dumper libmylib_v2.so -o v2.dump -lver 2.0

# Compare
abi-compliance-checker -lib MyLib -old v1.dump -new v2.dump
```

---

## Combined Pipeline: abi-scanner

`abi-scanner` runs **Mode 1 + Mode 2** by default (works for production stripped `.so`
with headers), and upgrades to **Mode 1 + Mode 3** when debug `.so` files are available.

### Combined verdict logic

```
abidiff result:    PASS / WARN / FAIL
ABICC result:      PASS / WARN / FAIL
                         │
                         ▼
           if EITHER reports FAIL → combined = FAIL
           if EITHER reports WARN → combined = WARN
           if BOTH   report PASS  → combined = PASS
```

**Rationale:** The tools have complementary blind spots:

| What | abidiff sees it | ABICC sees it |
|------|:--------------:|:------------:|
| Symbol removal | ✅ | ✅ |
| ELF visibility change | ✅ | ❌ |
| noexcept removal | ❌ | ✅ (headers) |
| Inline ODR | ❌ | ✅ (headers) |
| Type layout (stripped .so) | ❌ | ✅ (headers) |
| Anon struct layout | ⚠️ DWARF | ⚠️ dump |

Using only one tool means a real break can slip through. The combined worst-of
verdict minimizes false negatives at the cost of some false positives (reviewed
manually).

### Pipeline configuration

```yaml
# abi-scanner config example
pipeline:
  modes:
    - abidiff          # always run
    - abicc_headers    # always run (requires headers)
    - abicc_dump       # run only if debug_so available

  verdict: worst-of    # FAIL if any mode FAILs

  inputs:
    v1_so: dist/v1/lib/libmylib.so
    v2_so: dist/v2/lib/libmylib.so
    v1_headers: dist/v1/include/
    v2_headers: dist/v2/include/
    # optional:
    v1_debug_so: build/v1/debug/libmylib.so
    v2_debug_so: build/v2/debug/libmylib.so
```

---

## Quick Reference

| Feature | abidiff | ABICC+headers | ABICC+dump |
|---------|:-------:|:-------------:|:----------:|
| Needs DWARF | optional | ❌ | ✅ required |
| Needs headers | ❌ | ✅ | optional |
| Needs `abi-dumper` | ❌ | ❌ | ✅ |
| Works on stripped .so | ⚠️ limited | ✅ | ❌ |
| Catches noexcept | ❌ | ✅ | ❌ |
| Catches inline ODR | ❌ | ✅ | ❌ |
| Catches type layout | ⚠️ DWARF | ✅ | ✅ |
| Catches anon structs | ⚠️ DWARF | ⚠️ limited | ✅ |
| Catches dep leak | ⚠️ DWARF | ✅ | ✅ |
| Speed | fast | medium | slow |
| Recommended for | baseline | production | CI/staging |

---

*See [examples/README.md](../examples/README.md) for the full case-by-case matrix.*
