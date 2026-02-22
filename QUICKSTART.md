# ABI Scanner — Quick Start

## Phase 1: CLI Skeleton ✅

### Installation (Dev Mode)

No installation needed — run directly from repo:

```bash
cd /workspace/oneapi-abi-tracker
./abi-scanner --help
```

### Usage

#### Compare Two Versions

```bash
./abi-scanner compare conda-forge:dal=2025.9.0 conda-forge:dal=2025.10.0
```

**Output:**
```
Comparing conda-forge:dal=2025.9.0 → conda-forge:dal=2025.10.0
Status: ✅ COMPATIBLE (exit code: 0)
(Implementation in progress)
```

#### Get Help

```bash
./abi-scanner --help
./abi-scanner compare --help
./abi-scanner compatible --help
```

#### Supported Formats

```bash
# Conda channels
conda-forge:dal=2025.9.0
intel:mkl=2025.1.0

# APT packages
apt:intel-oneapi-dal=2025.9.0

# Local files (not yet implemented)
local:/path/to/libonedal.so
```

### Testing

```bash
# Run unit tests
python3 -m pytest tests/ -v

# Test package spec parser
python3 -c "
from abi_scanner.package_spec import PackageSpec
spec = PackageSpec.parse('conda-forge:dal=2025.9.0')
print(spec)
"
```

### What Works

- ✅ CLI argument parsing (argparse)
- ✅ Package spec parser with validation
- ✅ Help text and subcommands structure
- ✅ Unit tests (11/11 passing)

### What's Next

- [ ] Source adapter interface
- [ ] Conda adapter implementation
- [ ] APT adapter implementation
- [ ] Actual ABI comparison logic
- [ ] JSON output format

---

**Status:** Phase 1 in progress (50% done)  
**Last updated:** 2026-02-22
