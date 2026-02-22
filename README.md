# ABI Scanner

Automated ABI (Application Binary Interface) compatibility tracking for C/C++ libraries.

**⚠️ Prevents binary compatibility breaks before they reach users.**

## What is this?

ABI Scanner automatically detects when library updates break binary compatibility (ABI), helping maintainers validate Semantic Versioning compliance and prevent user-facing breakage.

**Example problem it solves:**
```
Library v2025.1.0: void process(int x);
Library v2025.2.0: void process(double x);  // ❌ ABI BREAK in minor version!

User's app compiled with v2025.1.0 crashes when linking v2025.2.0
```

ABI Scanner detects this **before release** in CI/CD.

## 📖 Documentation

- **[GOALS.md](GOALS.md)** — Project goals, tasks, roadmap, success criteria
- **[docs/INSTALLATION.md](docs/INSTALLATION.md)** — Installation & usage guide
- **[docs/onedal_package_distribution.md](docs/onedal_package_distribution.md)** — Package naming reference

## 🚀 Quick Start

```bash
# Install dependencies
sudo apt install abigail-tools
curl -Ls https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xvj bin/micromamba

# Clone repository
git clone https://github.com/napetrov/abi-scanner.git
cd abi-scanner

# Analyze a library version
export MAMBA_ROOT_PREFIX=$(pwd)/workspace/micromamba_root
bash scripts/process_single_version.sh dal 2025.10.0

# Compare two versions
abidiff --suppressions config/suppressions/onedal.txt \
    workspace/baselines/dal/dal_2025.9.0.abi \
    workspace/baselines/dal/dal_2025.10.0.abi

# Exit code:
#   0 = No changes (✅ safe for patch)
#   4 = Additions only (✅ safe for minor)
#  8/12 = Breaking changes (❌ requires major version)
```

## 📊 Current Status

**Phase 1 Complete:** Core infrastructure ✅
- [x] 35 versions of oneDAL analyzed (2021-2025)
- [x] Multi-source package support (conda-forge, Intel conda, APT)
- [x] libabigail integration with symbol filtering
- [x] Sequential comparison pipeline

**Phase 2 In Progress:** Validation & CI/CD integration
- [ ] Full comparison report
- [ ] SemVer compliance validation
- [ ] GitHub Actions workflows
- [ ] JSON output format

See [GOALS.md](GOALS.md) for complete roadmap.

## 📁 Repository Structure

```
abi-scanner/
├── GOALS.md                     # ⭐ Project goals & roadmap
├── scripts/                     # Automation scripts
│   ├── process_single_version.sh
│   ├── compare_all_history.py
│   └── ...
├── config/
│   ├── suppressions/            # Filter internal symbols
│   └── package_configs/         # Package metadata
└── docs/                        # Guides & references
```

**Note:** ABI baselines and reports are generated locally (not in repo).

## 🎯 Supported Libraries

### Currently Supported
- **Intel oneDAL** (Data Analytics Library) — 35 versions

### Planned Support
- Intel oneTBB (Threading Building Blocks)
- Intel oneMKL (Math Kernel Library)
- Intel oneDNN (Deep Neural Network Library)

### Adding New Library
See [GOALS.md](GOALS.md#phase-4-multi-library-support-may-2026) for extension plan.

## 🔍 Key Features

### Multi-Source Package Support
- **conda/mamba** — primary source (conda-forge, Intel channel)
- **APT** — Intel repositories (Ubuntu/Debian packages)
- **PyPI** — Python wheels with embedded native libraries

Uses official CLI tools (micromamba, apt) — never manual repo parsing.

### Symbol Filtering
Suppresses internal symbols to focus on public API:
- MKL internals (`mkl_*`, `vsl_*`)
- TBB internals (`tbb::detail::*`)
- Compiler-generated symbols

See `config/suppressions/` for customization.

### CI/CD Integration (Planned)
```yaml
# .github/workflows/abi-check.yml
- name: ABI Check
  run: |
    bash scripts/compare_new_version.sh
    if [ $? -gt 4 ]; then
      echo "ERROR: Breaking ABI changes in minor release!"
      exit 1
    fi
```

## 🤝 Contributing

**All changes must go through Pull Requests** (including maintainers).

Requirements:
- Fork the repository
- Create feature branch
- Add tests if applicable
- Update documentation
- Submit PR for review

See [GOALS.md#contact--governance](GOALS.md#-contact--governance) for contribution policy.

## 📄 License

MIT License (see LICENSE file)

## 📧 Contact

- **Maintainer:** Nikolay Petrov (Intel)
- **Issues:** [GitHub Issues](https://github.com/napetrov/abi-scanner/issues)
- **Discussions:** Intel tasks Telegram group

## 🔗 Related Projects

- [libabigail](https://sourceware.org/libabigail/) — ABI analysis framework
- [abi-compliance-checker](https://github.com/lvc/abi-compliance-checker) — Alternative tool
- [Intel oneAPI](https://www.intel.com/content/www/us/en/developer/tools/oneapi/overview.html) — Libraries ecosystem

---

**Status:** Active Development | Experimental  
**First Library:** Intel oneDAL (35 versions analyzed)  
**Next Target:** oneTBB support (Q2 2026)

**⭐ Star this repo** if you find it useful!
