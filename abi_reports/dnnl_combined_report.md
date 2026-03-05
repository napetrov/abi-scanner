# Intel oneDNN ABI Compatibility Report — Combined (abidiff + ABICC)

**Scan date:** 2026-03-05 (latest rerun)  
**Source:** Intel APT (apt.repos.intel.com/oneapi)  
**Versions scanned:** 2025.0.0 → 2025.3.0  
**Tools:** abidiff (ELF/symbol-level) + abi-compliance-checker (type/API-level)

## Combined Verdict Logic

| Condition | Combined Status |
|-----------|------------------|
| abidiff BREAKING + ABICC 100%/100% | ⚠️ ELF_INTERNAL — likely internal ELF-only symbols |
| abidiff COMPATIBLE/NO_CHANGE + ABICC binary break | 🔴 BINARY_BREAK |
| abidiff COMPATIBLE/NO_CHANGE + ABICC source break | 🟠 SOURCE_BREAK |
| abidiff BREAKING + ABICC source/binary break | 🔴 BREAKING |
| abidiff COMPATIBLE + ABICC 100%/100% | ✅ COMPATIBLE |
| abidiff NO_CHANGE + ABICC 100%/100% | ✅ NO_CHANGE |

## Summary Table

| Version Pair | Combined | abidiff | Bin% | Src% | ELF rm/add |
|---|---|---|---:|---:|---:|
| 2025.0.0-861 → 2025.0.1-6 | ✅ NO_CHANGE | NO_CHANGE | 100.0% | 100.0% | -0 +0 |
| 2025.0.1-6 → 2025.0.2-27 | ✅ NO_CHANGE | NO_CHANGE | 100.0% | 100.0% | -0 +0 |
| 2025.0.2-27 → 2025.1.0-643 | ⚠️ ELF_INTERNAL | BREAKING | 100.0% | 100.0% | -10 +15 |
| 2025.1.0-643 → 2025.1.1-5 | ✅ NO_CHANGE | NO_CHANGE | 100.0% | 100.0% | -0 +0 |
| 2025.1.1-5 → 2025.2.0-561 | ✅ COMPATIBLE | COMPATIBLE | 100.0% | 100.0% | -0 +4 |
| 2025.2.0-561 → 2025.3.0-409 | ⚠️ ELF_INTERNAL | BREAKING | 100.0% | 100.0% | -0 +19 |

## Key Findings

- 2025.0.2-27 → 2025.1.0-643: abidiff=BREAKING, ABICC=100/100 → ELF_INTERNAL
- 2025.2.0-561 → 2025.3.0-409: abidiff=BREAKING, ABICC=100/100 → ELF_INTERNAL
- Для oneDNN 2025.x публичный API остаётся стабильным; observed BREAKING от abidiff классифицированы как internal ELF deltas.
