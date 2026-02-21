# Installation & Usage Guide

## System Requirements

- **OS:** Linux (Ubuntu 20.04+, RHEL 8+) or macOS
- **Disk:** 500MB for tools + 500MB per analysis run
- **RAM:** 4GB minimum
- **Network:** Access to conda.anaconda.org and apt.repos.intel.com

## Installation

### 1. Install libabigail

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install abigail-tools
abidiff --version  # Should be 2.0+
```

**RHEL/CentOS:**
```bash
sudo dnf install libabigail
```

**macOS:**
```bash
brew install libabigail
```

**From source (if package unavailable):**
```bash
git clone https://sourceware.org/git/libabigail.git
cd libabigail
autoreconf -i
./configure --prefix=/usr/local
make && sudo make install
```

### 2. Install micromamba (conda package manager)

```bash
curl -Ls https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xvj bin/micromamba
sudo mv bin/micromamba /usr/local/bin/
micromamba --version
```

### 3. Clone this repository

```bash
git clone https://github.com/napetrov/oneapi-abi-tracker.git
cd oneapi-abi-tracker
```

### 4. Set up workspace

```bash
mkdir -p workspace/{baselines,reports,public_api,metadata}/dal
export WORKSPACE=$(pwd)/workspace
export MAMBA_ROOT_PREFIX=$(pwd)/workspace/micromamba_root
```

## Basic Workflows

### Workflow 1: Analyze a Single Version

```bash
# Set up environment
export WORKSPACE=$(pwd)/workspace
export MAMBA_ROOT_PREFIX=$(pwd)/workspace/micromamba_root

# Process one version (downloads from conda-forge)
bash scripts/process_single_version.sh dal 2025.10.0

# Check output
ls -lh workspace/baselines/dal/dal_2025.10.0.abi
cat workspace/metadata/dal/2025.10.0_metadata.json
```

**What it does:**
1. Downloads `dal` package from conda-forge via micromamba
2. Extracts `libonedal.so.3` shared library
3. Generates ABI baseline using `abidw`
4. Parses headers for public API (if available)
5. Saves metadata
6. Cleans up downloaded files

**Output:**
- `workspace/baselines/dal/dal_2025.10.0.abi` (3-5MB)
- `workspace/public_api/dal/2025.10.0_public_api.json` (10-20KB, if headers available)
- `workspace/metadata/dal/2025.10.0_metadata.json` (< 1KB)

### Workflow 2: Compare Two Versions

```bash
# Ensure both versions are processed
bash scripts/process_single_version.sh dal 2025.9.0
bash scripts/process_single_version.sh dal 2025.10.0

# Compare
abidiff --suppressions config/suppressions/onedal.txt \
    workspace/baselines/dal/dal_2025.9.0.abi \
    workspace/baselines/dal/dal_2025.10.0.abi

# Check exit code
echo "Exit code: $?"
```

**Interpretation:**
- Exit 0: No changes → ✅ Patch release OK
- Exit 4: Additions only → ✅ Minor release OK, ⚠️ Patch fails
- Exit 8/12: Breaking changes → ❌ Requires major version bump

### Workflow 3: Batch Process Multiple Versions

**From conda-forge (2021-2025):**
```bash
bash scripts/process_conda_forge_versions.sh
```

**From Intel conda (2021.7-2025.2):**
```bash
bash scripts/process_intel_conda_all.sh
```

**From Intel APT (2025.4-2025.10):**
```bash
# Requires apt (Linux only)
bash scripts/process_all_apt_versions.sh
```

### Workflow 4: Full Historical Analysis

```bash
# Process all available versions first (if not done)
bash scripts/process_conda_forge_versions.sh
bash scripts/process_intel_conda_all.sh

# Run sequential comparisons
python3 scripts/compare_all_history.py
```

**Output:**
```
✅ NO_CHANGE  | 2025.9.0   → 2025.10.0  | removed=0    added=0
❌ BREAKING   | 2025.1.0   → 2025.2.0   | removed=7    added=3
...

SUMMARY
==========================================================
✅ NO_CHANGE:  25
✅ COMPATIBLE: 7
❌ BREAKING:   2

Breaking changes:
  2021.1.1 → 2021.2.2 (removed=15)
  2025.1.0 → 2025.2.0 (removed=7)
```

## Advanced Usage

### Custom Suppressions

Edit `config/suppressions/onedal.txt` to filter additional symbols:

```ini
[suppress_function]
# Add your patterns
symbol_name_regexp = ^my_internal_function.*

[suppress_variable]
# Filter internal variables
symbol_name_regexp = ^_internal_.*
```

### Analyze Non-conda Packages

**From local .deb file:**
```bash
DEB_FILE=/path/to/intel-oneapi-dal-2025.10.0.deb
dpkg -x "$DEB_FILE" /tmp/extracted
SO_FILE=$(find /tmp/extracted -name "libonedal.so.3")
abidw "$SO_FILE" --out-file workspace/baselines/dal/dal_2025.10.0.abi
```

**From installed system library:**
```bash
abidw /usr/lib/x86_64-linux-gnu/libonedal.so.3 \
    --out-file workspace/baselines/dal/dal_system.abi
```

### CI/CD Integration

**GitHub Actions example:**
```yaml
name: ABI Check
on: [pull_request]

jobs:
  abi-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Install tools
        run: |
          sudo apt install -y abigail-tools
          curl -Ls https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xj
          sudo mv bin/micromamba /usr/local/bin/
      
      - name: Generate baseline
        run: |
          export MAMBA_ROOT_PREFIX=$PWD/mamba_root
          bash scripts/process_single_version.sh dal ${{ github.head_ref }}
      
      - name: Compare with main
        run: |
          abidiff --suppressions config/suppressions/onedal.txt \
            workspace/baselines/dal/dal_main.abi \
            workspace/baselines/dal/dal_${{ github.head_ref }}.abi
          EXIT=$?
          if [ $EXIT -gt 4 ]; then
            echo "ERROR: Breaking ABI changes detected!"
            exit 1
          fi
```

## Troubleshooting

### Issue: "micromamba: command not found"

**Solution:** Ensure micromamba is in PATH:
```bash
export PATH="$PATH:/usr/local/bin"
# or
alias micromamba='/path/to/micromamba'
```

### Issue: "libabigail not found"

**Solution:** Install from source or use Docker:
```bash
docker run --rm -v $(pwd):/work -w /work \
    ubuntu:22.04 bash -c "
    apt update && apt install -y abigail-tools
    abidiff --version
    "
```

### Issue: "Permission denied: /tmp/bin/micromamba"

**Solution:** `/tmp` mounted with `noexec`. Use `/workspace` instead:
```bash
mv /tmp/bin/micromamba /workspace/
chmod +x /workspace/micromamba
./workspace/micromamba --version
```

### Issue: "Package dal-2025.X.Y not found"

**Solution:** Check available versions:
```bash
export MAMBA_ROOT_PREFIX=/workspace/micromamba_root
micromamba search -c conda-forge dal
```

## Performance Tips

1. **Parallel processing:** Run multiple `process_single_version.sh` in parallel (different terminals)
2. **Reuse baselines:** Once generated, baselines can be reused for all comparisons
3. **Filter early:** Use suppressions to reduce comparison time
4. **SSD recommended:** ABI analysis is I/O intensive

## Output File Sizes

| File Type | Size | Description |
|-----------|------|-------------|
| ABI baseline (.abi) | 800KB - 5MB | XML dump of full ABI |
| Comparison report (.txt) | 10KB - 50MB | Depends on symbol count |
| Public API (.json) | 10-50KB | Namespace categorization |
| Metadata (.json) | < 1KB | Processing info |

## Next Steps

1. Read `docs/onedal_package_distribution.md` for package naming details
2. Explore `scripts/` directory for automation options
3. Check GitHub Issues for known limitations
4. Contribute improvements via Pull Requests

---

**Questions?** Open an issue or contact maintainer.
