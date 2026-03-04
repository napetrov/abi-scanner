# ABI Compatibility Report: Intel DPC++ Compiler Runtime (`libsycl.so`)

Multi-channel ABI scan results for Intel DPC++ Compiler Runtime (latest major releases only).

## Channel: apt
**Package:** `intel-oneapi-compiler-dpcpp-cpp-runtime-2025`

| Version Pair | Status | Removed (Public) | Added (Public) |
|---|---|---|---|
| 2025.0.0-1169 → 2025.0.1-1240 | ✅ NO_CHANGE | 0 | 0 |
| 2025.0.1-1240 → 2025.0.3-1401 | ✅ NO_CHANGE | 0 | 0 |
| 2025.0.3-1401 → 2025.0.4-1519 | ✅ NO_CHANGE | 0 | 0 |
| 2025.0.4-1519 → 2025.1.0-973 | ❌ BREAKING | 0 | 4 |
| 2025.1.0-973 → 2025.1.1-10 | ✅ NO_CHANGE | 0 | 0 |
| 2025.1.1-10 → 2025.2.0-766 | ❌ BREAKING | 1 | 4 |
| 2025.2.0-766 → 2025.2.1-7 | ✅ NO_CHANGE | 0 | 0 |
| 2025.2.1-7 → 2025.2.2-6 | ✅ NO_CHANGE | 0 | 0 |
| 2025.2.2-6 → 2025.3.0-639 | ⚠️ COMPATIBLE | 0 | 23 |
| 2025.3.0-639 → 2025.3.1-760 | ✅ NO_CHANGE | 0 | 0 |
| 2025.3.1-760 → 2025.3.2-832 | ✅ NO_CHANGE | 0 | 0 |

### Breaking Changes Details (apt)

#### 2025.0.4-1519 → 2025.1.0-973

**Added:**
```cpp
sycl::_V1::verifyUSMAllocatorProperties(sycl::_V1::property_list const&)
_ZN4sycl3_V13ext6oneapi12experimental21dynamic_command_groupC1ERKNS3_13command_graphILNS3_11graph_stateE0EEERKSt6vectorISt8functionIFvRNS0_7handlerEEESaISF_EE, aliases _ZN4sycl3_V13ext6oneapi12experimental21dynamic_command_groupC2ERKNS3_13command_graphILNS3_11graph_stateE0EEERKSt6vectorISt8functionIFvRNS0_7handlerEEESaISF_EE
sycl::_V1::handler::copyCodeLoc(sycl::_V1::handler const&)
sycl::_V1::handler::setKernelWorkGroupMem(unsigned long)
```

#### 2025.1.1-10 → 2025.2.0-766

**Removed:**
```cpp
sycl::_V1::queue::ext_oneapi_get_last_event() const
```

**Added:**
```cpp
sycl::_V1::interop_handle::getNativeGraph() const
sycl::_V1::interop_handle::ext_codeplay_has_graph() const
sycl::_V1::queue::ext_oneapi_get_last_event_impl() const
sycl::_V1::platform::khr_get_default_context() const
```

## Channel: intel
**Package:** `dpcpp-cpp-rt`

| Version Pair | Status | Removed (Public) | Added (Public) |
|---|---|---|---|
| 2025.0.0 → 2025.0.1 | ✅ UNKNOWN(3) | 0 | 0 |
| 2025.0.1 → 2025.0.3 | ✅ UNKNOWN(3) | 0 | 0 |
| 2025.0.3 → 2025.0.4 | ✅ UNKNOWN(3) | 0 | 0 |
| 2025.0.4 → 2025.1.0 | ✅ UNKNOWN(3) | 0 | 0 |
| 2025.1.0 → 2025.1.1 | ✅ UNKNOWN(3) | 0 | 0 |
| 2025.1.1 → 2025.2.0 | ✅ UNKNOWN(3) | 0 | 0 |
| 2025.2.0 → 2025.2.1 | ✅ UNKNOWN(3) | 0 | 0 |
| 2025.2.1 → 2025.2.2 | ✅ UNKNOWN(3) | 0 | 0 |
| 2025.2.2 → 2025.3.0 | ✅ UNKNOWN(3) | 0 | 0 |
| 2025.3.0 → 2025.3.1 | ✅ UNKNOWN(3) | 0 | 0 |
| 2025.3.1 → 2025.3.2 | ✅ UNKNOWN(3) | 0 | 0 |

*No breaking changes detected.*
