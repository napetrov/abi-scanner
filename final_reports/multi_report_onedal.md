# ABI Compatibility Report: Intel oneDAL (`libonedal.so`)

Multi-channel ABI scan results for Intel oneDAL (latest major releases only).

## Channel: apt
**Package:** `intel-oneapi-dal`

| Version Pair | Status | Removed (Public) | Added (Public) |
|---|---|---|---|
| 2025.0.0-957 → 2025.0.1-9 | ✅ NO_CHANGE | 0 | 0 |
| 2025.0.1-9 → 2025.4.0-641 | ❌ BREAKING | 17 | 21 |
| 2025.4.0-641 → 2025.5.0-6 | ❌ BREAKING | 1161 | 714 |
| 2025.5.0-6 → 2025.6.0-114 | ⚠️ COMPATIBLE | 0 | 3 |
| 2025.6.0-114 → 2025.8.0-11 | ⚠️ COMPATIBLE | 0 | 56 |
| 2025.8.0-11 → 2025.9.0-51 | ✅ NO_CHANGE | 0 | 0 |
| 2025.9.0-51 → 2025.10.1-19 | ✅ NO_CHANGE | 0 | 0 |

### Breaking Changes Details (apt)

#### 2025.0.1-9 → 2025.4.0-641

**Removed:**
```cpp
VIRNGUNIFORMBITS64_
VIRNGUNIFORM_
XERBLA
XERBLA_
oneapi::dal::v2::array<double>::operator=(oneapi::dal::v2::array<double>&&)
oneapi::dal::v2::array<float>::operator=(oneapi::dal::v2::array<float>&&)
oneapi::dal::v2::array<int>::operator=(oneapi::dal::v2::array<int>&&)
__intel_mkl_features_init_x
cdecl_xerbla
viRngUniform
... and 7 more (see JSON file for full list)
```

**Added:**
```cpp
daal::services::interface1::SharedPtr<daal::algorithms::engines::philox4x32x10::interface1::Batch<float, (daal::algorithms::engines::philox4x32x10::Method)0> >::~SharedPtr()
daal::services::interface1::SharedPtr<daal::algorithms::engines::mcg59::interface1::Batch<float, (daal::algorithms::engines::mcg59::Method)0> >::~SharedPtr()
daal::services::interface1::SharedPtr<daal::algorithms::engines::mt19937::interface1::Batch<float, (daal::algorithms::engines::mt19937::Method)0> >::~SharedPtr()
daal::services::interface1::SharedPtr<daal::algorithms::engines::mrg32k3a::interface1::Batch<float, (daal::algorithms::engines::mrg32k3a::Method)0> >::~SharedPtr()
oneapi::dal::v2::array<int>::operator=(oneapi::dal::v2::array<int> const&)
MKL_Detect_Cpu_Global_Lock
__intel_mkl_feature_indicator_x
_vsl_WH_A
_vsl_WH_M
_vsl_mrg32k3a_skipahead_table
... and 11 more (see JSON file for full list)
```

#### 2025.4.0-641 → 2025.5.0-6

**Removed:**
```cpp
daal::algorithms::classifier::interface1::Model::setNFeatures(unsigned long)
daal::algorithms::classifier::prediction::interface2::Batch::initialize()
daal::algorithms::classifier::prediction::interface2::Batch::~Batch()
daal::algorithms::classifier::prediction::interface2::Batch::~Batch()
daal::algorithms::classifier::training::interface2::Batch::~Batch()
daal::algorithms::classifier::training::interface2::Batch::~Batch()
daal::algorithms::covariance::interface1::Batch<double, (daal::algorithms::covariance::Method)0>::allocateResult()
daal::algorithms::covariance::interface1::Batch<double, (daal::algorithms::covariance::Method)0>::~Batch()
daal::algorithms::covariance::interface1::Batch<float, (daal::algorithms::covariance::Method)0>::allocateResult()
daal::algorithms::covariance::interface1::Batch<float, (daal::algorithms::covariance::Method)0>::~Batch()
... and 1151 more (see JSON file for full list)
```

**Added:**
```cpp
_ZN6oneapi3dal15decision_forest6detail2v116train_parametersINS1_4task2v110regressionEEC1Ev, aliases _ZN6oneapi3dal15decision_forest6detail2v116train_parametersINS1_4task2v110regressionEEC2Ev
_ZN6oneapi3dal15decision_forest6detail2v116train_parametersINS1_4task2v114classificationEEC2Ev, aliases _ZN6oneapi3dal15decision_forest6detail2v116train_parametersINS1_4task2v114classificationEEC1Ev
guard variable for oneapi::dal::covariance::result_options::cor_matrix
guard variable for oneapi::dal::covariance::result_options::cov_matrix
guard variable for oneapi::dal::covariance::result_options::means
guard variable for oneapi::dal::basic_statistics::result_options::sum_squares
guard variable for oneapi::dal::basic_statistics::result_options::standard_deviation
guard variable for oneapi::dal::basic_statistics::result_options::sum_squares_centered
guard variable for oneapi::dal::basic_statistics::result_options::second_order_raw_moment
guard variable for oneapi::dal::basic_statistics::result_options::max
... and 704 more (see JSON file for full list)
```

## Channel: intel
**Package:** `dal`

| Version Pair | Status | Removed (Public) | Added (Public) |
|---|---|---|---|
| 2025.0.0 → 2025.0.1 | ✅ NO_CHANGE | 0 | 0 |
| 2025.0.1 → 2025.1.0 | ⚠️ COMPATIBLE | 0 | 0 |
| 2025.1.0 → 2025.2.0 | ❌ BREAKING | 3 | 1 |
| 2025.2.0 → 2025.4.0 | ❌ BREAKING | 14 | 20 |
| 2025.4.0 → 2025.5.0 | ❌ BREAKING | 1161 | 714 |
| 2025.5.0 → 2025.6.0 | ⚠️ COMPATIBLE | 0 | 3 |
| 2025.6.0 → 2025.6.1 | ✅ NO_CHANGE | 0 | 0 |
| 2025.6.1 → 2025.7.0 | ⚠️ COMPATIBLE | 0 | 20 |
| 2025.7.0 → 2025.8.0 | ⚠️ COMPATIBLE | 0 | 36 |
| 2025.8.0 → 2025.9.0 | ✅ NO_CHANGE | 0 | 0 |
| 2025.9.0 → 2025.10.1 | ✅ NO_CHANGE | 0 | 0 |

### Breaking Changes Details (intel)

#### 2025.1.0 → 2025.2.0

**Removed:**
```cpp
oneapi::dal::v2::array<double>::operator=(oneapi::dal::v2::array<double>&&)
oneapi::dal::v2::array<float>::operator=(oneapi::dal::v2::array<float>&&)
oneapi::dal::v2::array<int>::operator=(oneapi::dal::v2::array<int>&&)
```

**Added:**
```cpp
oneapi::dal::v2::array<int>::operator=(oneapi::dal::v2::array<int> const&)
```

#### 2025.2.0 → 2025.4.0

**Removed:**
```cpp
VIRNGUNIFORMBITS64_
VIRNGUNIFORM_
XERBLA
XERBLA_
__intel_mkl_features_init_x
cdecl_xerbla
viRngUniform
viRngUniformBits64
viRngUniformBits64_64
viRngUniform_64
... and 4 more (see JSON file for full list)
```

**Added:**
```cpp
daal::services::interface1::SharedPtr<daal::algorithms::engines::philox4x32x10::interface1::Batch<float, (daal::algorithms::engines::philox4x32x10::Method)0> >::~SharedPtr()
daal::services::interface1::SharedPtr<daal::algorithms::engines::mcg59::interface1::Batch<float, (daal::algorithms::engines::mcg59::Method)0> >::~SharedPtr()
daal::services::interface1::SharedPtr<daal::algorithms::engines::mt19937::interface1::Batch<float, (daal::algorithms::engines::mt19937::Method)0> >::~SharedPtr()
daal::services::interface1::SharedPtr<daal::algorithms::engines::mrg32k3a::interface1::Batch<float, (daal::algorithms::engines::mrg32k3a::Method)0> >::~SharedPtr()
MKL_Detect_Cpu_Global_Lock
__intel_mkl_feature_indicator_x
_vsl_WH_A
_vsl_WH_M
_vsl_mrg32k3a_skipahead_table
_vsl_mt2203_table
... and 10 more (see JSON file for full list)
```

#### 2025.4.0 → 2025.5.0

**Removed:**
```cpp
daal::algorithms::classifier::interface1::Model::setNFeatures(unsigned long)
daal::algorithms::classifier::prediction::interface2::Batch::initialize()
daal::algorithms::classifier::prediction::interface2::Batch::~Batch()
daal::algorithms::classifier::prediction::interface2::Batch::~Batch()
daal::algorithms::classifier::training::interface2::Batch::~Batch()
daal::algorithms::classifier::training::interface2::Batch::~Batch()
daal::algorithms::covariance::interface1::Batch<double, (daal::algorithms::covariance::Method)0>::allocateResult()
daal::algorithms::covariance::interface1::Batch<double, (daal::algorithms::covariance::Method)0>::~Batch()
daal::algorithms::covariance::interface1::Batch<float, (daal::algorithms::covariance::Method)0>::allocateResult()
daal::algorithms::covariance::interface1::Batch<float, (daal::algorithms::covariance::Method)0>::~Batch()
... and 1151 more (see JSON file for full list)
```

**Added:**
```cpp
_ZN6oneapi3dal15decision_forest6detail2v116train_parametersINS1_4task2v110regressionEEC1Ev, aliases _ZN6oneapi3dal15decision_forest6detail2v116train_parametersINS1_4task2v110regressionEEC2Ev
_ZN6oneapi3dal15decision_forest6detail2v116train_parametersINS1_4task2v114classificationEEC2Ev, aliases _ZN6oneapi3dal15decision_forest6detail2v116train_parametersINS1_4task2v114classificationEEC1Ev
guard variable for oneapi::dal::covariance::result_options::cor_matrix
guard variable for oneapi::dal::covariance::result_options::cov_matrix
guard variable for oneapi::dal::covariance::result_options::means
guard variable for oneapi::dal::basic_statistics::result_options::sum_squares
guard variable for oneapi::dal::basic_statistics::result_options::standard_deviation
guard variable for oneapi::dal::basic_statistics::result_options::sum_squares_centered
guard variable for oneapi::dal::basic_statistics::result_options::second_order_raw_moment
guard variable for oneapi::dal::basic_statistics::result_options::max
... and 704 more (see JSON file for full list)
```
