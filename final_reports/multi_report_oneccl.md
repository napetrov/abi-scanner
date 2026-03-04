# ABI Compatibility Report: Intel oneCCL (`libccl.so`)

Multi-channel ABI scan results for Intel oneCCL (latest major releases only).

## Channel: apt
**Package:** `intel-oneapi-ccl`

| Version Pair | Status | Removed (Public) | Added (Public) |
|---|---|---|---|
| 2021.16.0-302 → 2021.16.1-9 | ⚠️ COMPATIBLE | 0 | 0 |
| 2021.16.1-9 → 2021.17.0-271 | ⚠️ COMPATIBLE | 0 | 2 |
| 2021.17.0-271 → 2021.17.1-7 | ✅ NO_CHANGE | 0 | 0 |
| 2021.17.1-7 → 2021.17.2-5 | ❌ BREAKING | 0 | 2 |

### Breaking Changes Details (apt)

#### 2021.17.1-7 → 2021.17.2-5

**Added:**
```cpp
ccl::is_allgatherv_inplace(void const*, unsigned long, void const*, unsigned long const*, unsigned long, unsigned long, unsigned long)
ccl::is_allgatherv_inplace(void const*, unsigned long, void const*, unsigned long const*, unsigned long const*, unsigned long, unsigned long, unsigned long)
```

## Channel: intel
**Package:** `oneccl-cpu`

| Version Pair | Status | Removed (Public) | Added (Public) |
|---|---|---|---|
| 2021.16.0 → 2021.16.1 | ⚠️ COMPATIBLE | 0 | 0 |
| 2021.16.1 → 2021.17.0 | ⚠️ COMPATIBLE | 0 | 2 |
| 2021.17.0 → 2021.17.1 | ✅ NO_CHANGE | 0 | 0 |
| 2021.17.1 → 2021.17.2 | ❌ BREAKING | 0 | 2 |

### Breaking Changes Details (intel)

#### 2021.17.1 → 2021.17.2

**Added:**
```cpp
ccl::is_allgatherv_inplace(void const*, unsigned long, void const*, unsigned long const*, unsigned long, unsigned long, unsigned long)
ccl::is_allgatherv_inplace(void const*, unsigned long, void const*, unsigned long const*, unsigned long const*, unsigned long, unsigned long, unsigned long)
```
