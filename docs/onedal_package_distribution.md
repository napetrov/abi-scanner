# oneDAL Package Distribution — Complete Reference

## Package Names by Channel

### 🔴 Intel Conda Channel
**URL:** `https://software.repos.intel.com/python/conda/`

#### Runtime Package: `dal`
- **Name:** `dal` (NOT onedal, NOT daal)
- **Contains:** `.so` shared libraries (libonedal.so.3, libonedal_core.so.3, etc.)
- **Size:** ~67MB
- **Versions:** 2025.0.0, 2025.0.1, 2025.1.0, 2025.2.0, 2024.x, ...
- **Example:** `dal-2025.0.0-intel_957.tar.bz2`

#### Development Package: `dal-devel`
- **Name:** `dal-devel`
- **Contains:** `.a` static libraries (libonedal_sycl.a)
- **Size:** ~153MB
- **Does NOT contain headers** (separate package)
- **Example:** `dal-devel-2025.0.0-intel_957.tar.bz2`

#### Headers Package: `dal-include`
- **Name:** `dal-include`
- **Contains:** C++ headers (`.hpp`) — 309 files
- **Size:** ~0.4MB (tiny!)
- **Structure:** `include/oneapi/dal/*.hpp`
- **Versions:** Same as dal runtime (2025.0.0, etc.)
- **Example:** `dal-include-2025.0.0-intel_957.tar.bz2`

#### Python Binding: `daal4py`
- **Name:** `daal4py`
- **Contains:** Python package wrapping oneDAL
- **Latest version:** 2024.7.0 (no 2025.x yet in conda)
- **Depends on:** `dal` runtime package

#### Python Extension: `scikit-learn-intelex`
- **Name:** `scikit-learn-intelex`
- **Depends on:** `dal` + `daal4py`
- **Versions:** 2025.0, 2025.1, 2025.2
- **Example dependency:** `dal 2025.2.0`

---

### 🟢 conda-forge Channel
**URL:** `https://conda.anaconda.org/conda-forge/`

#### Legacy Packages (up to 2021.6)
- **`daal`** — old name, up to 2021.6.0
- **`daal-devel`** — old devel package
- **`daal4py`** — up to 2021.6.0
- **`scikit-learn-intelex`** — up to 2021.6.0

#### Modern oneDAL (2022+)
- ❌ **NOT available in conda-forge**
- oneDAL 2022+ exists only in Intel channel or APT

---

### 🔵 Intel APT Repository
**URL:** `https://apt.repos.intel.com/oneapi/pool/main/`

#### Runtime Package
- **Name:** `intel-oneapi-dal-2025.X`
- **Format:** `.deb`
- **Contains:** `.so` files only
- **Size:** ~54-55MB
- **Path:** `/opt/intel/oneapi/dal/2025.X/lib/`

#### Development Package
- **Name:** `intel-oneapi-dal-devel-2025.X`
- **Format:** `.deb`
- **Contains:** headers + static libs
- **Size:** ~168MB (large!)
- **Path:** `/opt/intel/oneapi/dal/2025.X/include/`

#### Versions Available
- 2025.0, 2025.4, 2025.5, 2025.6, 2025.8, 2025.9, 2025.10
- Missing: 2025.1, 2025.2, 2025.3, 2025.7 (not published)

---

### 🟡 PyPI
**URL:** `https://pypi.org/project/scikit-learn-intelex/`

#### Package: `scikit-learn-intelex`
- **Format:** Python wheel (.whl)
- **Contains:** Embedded `.so` files + Python bindings
- **Versions:** Full 2025.x range (2025.0.0 through 2025.10.1)
- **No headers** — runtime only

---

## Recommended Source for ABI Tracking

### ✅ Intel Conda Channel (BEST)
**Pros:**
- ✅ Split packages: `dal` (67MB) + `dal-include` (0.4MB)
- ✅ Easy to download one version at a time
- ✅ Contains both runtime and headers
- ✅ Versions: 2025.0, 2025.1, 2025.2, 2024.x
- ✅ Simple wget/curl download

**Cons:**
- ⚠️ Not all 2025.x versions (missing 2025.4-2025.10 in conda)

### ⚠️ Intel APT Repository
**Pros:**
- ✅ More 2025.x versions (up to 2025.10)

**Cons:**
- ❌ Devel packages are huge (168MB)
- ❌ Missing versions (2025.1-3, 2025.7)
- ⚠️ Requires dpkg extraction

### ❌ conda-forge
**Not suitable:** Only has legacy daal up to 2021.6

---

## For ABI Tracking Project

### Pipeline Design
```bash
# Download ONE version from Intel conda:
wget https://software.repos.intel.com/python/conda/linux-64/dal-${VERSION}-intel_${BUILD}.tar.bz2
wget https://software.repos.intel.com/python/conda/linux-64/dal-include-${VERSION}-intel_${BUILD}.tar.bz2

# Extract
tar xjf dal-*.tar.bz2 -C extracted/
tar xjf dal-include-*.tar.bz2 -C extracted/

# Create ABI baseline
abidw extracted/lib/libonedal.so.3 --out-file baselines/onedal_${VERSION}.abi

# Parse public API from headers
python parse_headers.py extracted/include/ > public_api/${VERSION}.json

# Delete packages
rm -rf extracted/ dal-*.tar.bz2
```

### Space Efficiency
- Runtime: 67MB → extract → delete
- Headers: 0.4MB → extract → delete
- **Keep only:** ABI baseline (~3MB) + public API JSON (~50KB)
- **Total per version:** ~3MB (vs 67MB packages)

---

## Summary

| Channel | Package Name | Runtime | Headers | Size | Latest 2025.x |
|---------|-------------|---------|---------|------|---------------|
| Intel Conda | `dal` | ✅ | ❌ | 67MB | 2025.2 |
| Intel Conda | `dal-include` | ❌ | ✅ | 0.4MB | 2025.2 |
| Intel APT | `intel-oneapi-dal` | ✅ | ❌ | 54MB | 2025.10 |
| Intel APT | `intel-oneapi-dal-devel` | ✅ | ✅ | 168MB | 2025.10 |
| conda-forge | `daal` | ✅ | ❌ | — | 2021.6 (legacy) |
| PyPI | `scikit-learn-intelex` | ✅ | ❌ | varies | 2025.10.1 |

**Recommendation:** Use **Intel Conda** (`dal` + `dal-include`) for versions up to 2025.2, then fall back to **Intel APT** for 2025.4+.
