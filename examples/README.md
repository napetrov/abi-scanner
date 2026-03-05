# ABI Scenario Catalog

An **Application Binary Interface (ABI)** defines the low-level contract between
compiled code: calling conventions, symbol names, type layouts, and vtable structure.
When a shared library changes its ABI without bumping its SONAME, pre-built consumers
crash or silently misbehave. Unlike the source-level API, ABI compatibility is
invisible to the human eye — you need tooling like `abidiff` to catch it.

## Why ABI stability matters

Downstream binaries link against a specific `.so` version at install time. If the
library ships a new build that changes a function signature, removes a symbol, or
alters a struct layout, the binary fails to load or produces wrong results — without
any source change on the consumer side. Linux distributions, language runtimes, and
embedded firmware all depend on ABI stability for safe rolling upgrades.

## abidiff exit-code reference (libabigail 2.4.0)

| Exit | Meaning |
|------|---------|
| 0 | No ABI change |
| 4 | ABI change detected (type/layout diff, addition) |
| 12 | Breaking ABI change (symbol removed) |

> In libabigail 2.4.0, only symbol **removal** triggers exit 12.  
> Type changes, vtable reorderings, and struct growth return exit 4.  
> Both should be treated as breaking by release policy.

## Case Index

| # | Case | Category | abidiff exit | Root cause |
|---|------|----------|-------------|-----------|
| [01](case01_symbol_removal/README.md) | Symbol Removal | Symbol API | 12 🔴 | Public function deleted from .so |
| [02](case02_param_type_change/README.md) | Parameter Type Change | Symbol API | 4 🟡 | Param type widened, callers pass wrong register |
| [03](case03_compat_addition/README.md) | Compatible Addition | Symbol API | 4 🟢 | New export added, existing callers unaffected |
| [04](case04_no_change/README.md) | No Change | Symbol API | 0 ✅ | Identical binary — baseline |
| [05](case05_soname/README.md) | Missing SONAME | ELF/Linker | — 🟡 | Library built without -Wl,-soname |
| [06](case06_visibility/README.md) | Visibility Leak | Visibility | — 🟡 | Internal symbols unintentionally exported |
| [07](case07_struct_layout/README.md) | Struct Layout Change | Type Layout | 4 🟡 | Field added, sizeof grows, callers undersize |
| [08](case08_enum_value_change/README.md) | Enum Value Change | Type Layout | 4 🟡 | Value inserted mid-enum, existing constants shift |
| [09](case09_cpp_vtable/README.md) | C++ Vtable Change | C++ ABI | 4 🟡 | Virtual method inserted, vtable offsets shift |
| [10](case10_return_type/README.md) | Return Type Change | Symbol API | 4 🟡 | Return type widened, callers read truncated value |
| [11](case11_global_var_type/README.md) | Global Variable Type | Type Layout | 4 🟡 | Global var type widened, symbol size changes |
| [12](case12_function_removed/README.md) | Function Disappears | Symbol API | 12 🔴 | Function moved to inline, vanishes from .so |
| [13](case13_symbol_versioning/README.md) | Symbol Versioning | ELF/Linker | — 🟡 | No version script → no `@@VER` on symbols |
| [14](case14_cpp_class_size/README.md) | C++ Class Size Change | C++ ABI | 4 🟡 | Private member grows, sizeof(class) changes |

## Quick start

```bash
# Install tools (Ubuntu/Debian)
sudo apt-get install gcc g++ binutils libabigail-tools

# Run all integration tests
cd <repo-root>
source venv/bin/activate
pytest tests/test_abi_scenarios.py -v

# Manually explore a case
cd examples/case01_symbol_removal
gcc -shared -fPIC -g v1.c -o libv1.so
gcc -shared -fPIC -g v2.c -o libv2.so
abidw --out-file v1.xml libv1.so
abidw --out-file v2.xml libv2.so
abidiff v1.xml v2.xml
```
