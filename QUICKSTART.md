# ABI Scanner — Quick Start

## Installation

```bash
# System deps
sudo apt install abigail-tools

# micromamba (needed for conda channels)
curl -Ls https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xvj bin/micromamba
export PATH="$PATH:$(pwd)/bin"
export MAMBA_ROOT_PREFIX=$(pwd)/workspace/micromamba_root

# Clone & install
git clone https://github.com/napetrov/abi-scanner.git
cd abi-scanner
pip install -e .
```

## Command: compare

Compare ABI between two package versions.

### Intel conda channel
```bash
abi-scanner compare intel:oneccl-cpu=2021.14.0 intel:oneccl-cpu=2021.14.1 \
  --library-name libccl.so

# Output:
# Comparing intel:oneccl-cpu=2021.14.0 → intel:oneccl-cpu=2021.14.1
# Status: ✅ NO_CHANGE
```

### Intel APT channel
```bash
abi-scanner compare \
  "apt:intel-oneapi-compiler-dpcpp-cpp-runtime-2025.0=2025.0.0-1169" \
  "apt:intel-oneapi-compiler-dpcpp-cpp-runtime-2025.0=2025.0.1-1240" \
  --library-name libsycl.so

# Output:
# Comparing apt:intel-oneapi-...=2025.0.0-1169 → ...=2025.0.1-1240
# Status: ✅ NO_CHANGE
```

### With suppressions file
```bash
abi-scanner compare intel:oneccl-cpu=2021.14.0 intel:oneccl-cpu=2021.15.0 \
  --library-name libccl.so \
  --suppressions config/suppressions/oneccl.txt
```

### JSON output
```bash
abi-scanner compare intel:oneccl-cpu=2021.14.0 intel:oneccl-cpu=2021.15.0 \
  --library-name libccl.so --format json
```

### CI mode (fail on breaking)
```bash
abi-scanner compare old:pkg=1.0 new:pkg=2.0 \
  --library-name libfoo.so --fail-on breaking
echo $?  # non-zero if breaking ABI change
```

### Local .so file
```bash
abi-scanner compare intel:oneccl-cpu=2021.14.0 local:./libccl.so \
  --library-name libccl.so
```

## Command: list

List available versions for a package.

### Intel conda
```bash
abi-scanner list intel:oneccl-cpu

# With filter
abi-scanner list intel:oneccl-cpu --filter '^2021\.14'
# Output:
#   Versions for intel:oneccl-cpu (2 total):
#     2021.14.0
#     2021.14.1
```

### Intel APT
```bash
abi-scanner list apt:compiler \
  --apt-pkg-pattern '^intel-oneapi-compiler-dpcpp-cpp-runtime-2025\.\d+$' \
  --filter '^2025\.0'
# Output:
#   Versions for apt:compiler (4 total):
#     2025.0.0-1169  [pool/main/intel-oneapi-...]
#     2025.0.1-1240  [...]
```

### JSON output
```bash
abi-scanner list intel:oneccl-cpu --format json | jq '.[].version'
```

## Command: compatible

Find all versions ABI-compatible with a given baseline.

```bash
abi-scanner compatible intel:oneccl-cpu=2021.14.0 \
  --library-name libccl.so

# Output:
#   Version              Status
#   2021.14.0            (base)
#   2021.14.1            ✅ NO_CHANGE
#   2021.15.0            ❌ BREAKING  (-2 +20 ~0)
#
#   Compatible range : 2021.14.0 - 2021.14.1
#   First incompatible: 2021.15.0
```

### Stop at first break (fast CI mode)
```bash
abi-scanner compatible intel:oneccl-cpu=2021.14.0 \
  --library-name libccl.so --stop-at-first-break
```

### With version filter
```bash
abi-scanner compatible intel:oneccl-cpu=2021.14.0 \
  --library-name libccl.so --filter '^2021\.(14|15)'
```

### Exit code on incompatible
```bash
abi-scanner compatible intel:oneccl-cpu=2021.14.0 \
  --library-name libccl.so --fail-on breaking
echo $?  # 8 if any breaking version found
```

## Batch History: compare_all_history.py

For full version-history analysis:

### oneCCL via Intel conda
```bash
python3 scripts/compare_all_history.py \
  --channel intel \
  --package oneccl-cpu \
  --library-name libccl.so \
  --suppressions config/suppressions/oneccl.txt \
  --json reports/oneccl_history.json
```

### DPC++ compiler via Intel APT
```bash
python3 scripts/compare_all_history.py \
  --channel apt \
  --package intel-oneapi-compiler-dpcpp-cpp-runtime-2025 \
  --apt-pkg-pattern '^intel-oneapi-compiler-dpcpp-cpp-runtime-2025\.\d+$' \
  --library-name libsycl.so \
  --suppressions config/suppressions/compiler.txt
```

## Suppression Configs

Pre-built suppression files for Intel libraries:

| File | Library | Suppresses |
|------|---------|-----------|
| `config/suppressions/oneccl.txt` | oneCCL | `ccl::detail::*`, `ccl::internal::*`, `_GLOBAL__*` |
| `config/suppressions/compiler.txt` | DPC++ | `sycl::*::detail::*`, `sycl::*::internal::*`, `__intel_*` |
| `config/suppressions/onedal.txt` | oneDAL | `oneapi::dal::detail::*` |

---
**Last updated:** 2026-02-25 | v0.2.0-dev
