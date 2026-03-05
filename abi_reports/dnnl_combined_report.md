# Intel oneDNN ABI Compatibility Report — Combined (abidiff + ABICC)

**Scan date:** 2026-03-05  
**Source:** Intel APT (apt.repos.intel.com/oneapi)  
**Versions scanned:** 2025.0.0 → 2025.3.0  
**Tools:** abidiff (ELF/symbol-level) + abi-compliance-checker (type/API-level)  

## Combined Verdict Logic

| Condition | Combined Status |
|-----------|----------------|
| abidiff BREAKING + ABICC 100%/100% | ⚠️ ELF_INTERNAL — false positive, internal symbols |
| abidiff COMPATIBLE/NO_CHANGE + ABICC binary break | 🔴 BINARY_BREAK — binary-level break (vtable/layout) |
| abidiff COMPATIBLE/NO_CHANGE + ABICC src < 100% | 🟠 SOURCE_BREAK — source-level incompatibility |
| abidiff BREAKING + ABICC src/bin < 100% | 🔴 BREAKING — confirmed by both tools |
| abidiff COMPATIBLE + ABICC 100%/100% | ✅ COMPATIBLE — additive changes only |
| abidiff NO_CHANGE + ABICC 100%/100% | ✅ NO_CHANGE — identical ABI |

## Summary Table

| Version Pair                 | Combined        | abidiff    | Bin%   | Src%   | ELF rm/add | API rm/add |
|------------------------------|-----------------|------------|--------|--------|------------|------------|
| 2025.0.0-861 -> 2025.0.1-6   | ✅ NO_CHANGE     | NO_CHANGE  | 100.0% | 100.0% | -0 +0      | -0 +0      |
| 2025.0.1-6 -> 2025.0.2-27    | ✅ NO_CHANGE     | NO_CHANGE  | 100.0% | 100.0% | -0 +0      | -0 +0      |
| 2025.0.2-27 -> 2025.1.0-643  | ⚠️ ELF_INTERNAL | BREAKING   | 100.0% | 100.0% | -10 +15    | -0 +0      |
| 2025.1.0-643 -> 2025.1.1-5   | ✅ NO_CHANGE     | NO_CHANGE  | 100.0% | 100.0% | -0 +0      | -0 +0      |
| 2025.1.1-5 -> 2025.2.0-561   | ✅ COMPATIBLE    | COMPATIBLE | 100.0% | 100.0% | -0 +4      | -0 +0      |
| 2025.2.0-561 -> 2025.3.0-409 | ⚠️ ELF_INTERNAL | BREAKING   | 100.0% | 100.0% | -0 +19     | -0 +0      |

## Key Findings

### ELF_INTERNAL cases explained

**2025.0.2-27 -> 2025.1.0-643**

- abidiff: 10 removed / 15 added ELF symbols
- ABICC binary compat: 100.0%
- ABICC source compat: 100.0%
- **Conclusion:** Symbols are ELF-visible but NOT part of the public C API.
  abidiff false positive — no public API break.

**2025.2.0-561 -> 2025.3.0-409**

- abidiff: 0 removed / 19 added ELF symbols
- ABICC binary compat: 100.0%
- ABICC source compat: 100.0%
- **Conclusion:** Symbols are ELF-visible but NOT part of the public C API.
  abidiff false positive — no public API break.

## Legend

- **⚠️ ELF_INTERNAL**: abidiff BREAKING but ABICC 100%/100% — internal/ELF-only symbols, not public API
- **🔴 BINARY_BREAK**: Binary-level break (vtable reorder, struct layout) detected by ABICC only
- **🟠 SOURCE_BREAK**: Source-level incompatibility detected by ABICC (abidiff missed it)
- **🔴 BREAKING**: Breaking change confirmed by both abidiff and ABICC
- **✅ COMPATIBLE**: Additive changes only — backward-compatible
- **✅ NO_CHANGE**: No ABI differences detected
