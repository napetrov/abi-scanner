# oneDAL ABI Tracker

Automated ABI (Application Binary Interface) compatibility tracking system for Intel oneDAL library across releases.

## 🎯 Goal

Validate semantic versioning compliance for oneDAL releases by detecting ABI-breaking changes that violate SemVer:
- **Patch releases** (X.Y.Z → X.Y.Z+1) must have zero ABI changes
- **Minor releases** (X.Y.0 → X.Y+1.0) may only add compatible symbols
- **Major releases** (X.0.0 → X+1.0.0) may break ABI

**Purpose:**
- Catch breaking changes before they reach users
- Prevent accidental ABI breaks in minor/patch releases
- Maintain binary compatibility across oneDAL versions
- Provide historical ABI change analysis

## 📊 Coverage

- **35 versions analyzed** (2021-2025)
- **34 sequential comparisons** completed
- **Sources:** conda-forge, Intel conda channel, Intel APT repository

## 🚀 Quick Start

### Prerequisites

```bash
# Install libabigail (ABI analysis tools)
sudo apt install abigail-tools  # Ubuntu/Debian
# or
brew install libabigail  # macOS

# Install micromamba (conda package manager)
curl -Ls https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xvj bin/micromamba
```

### Basic Usage

**1. Analyze a single version:**
```bash
bash scripts/process_single_version.sh dal 2025.10.0
```

**2. Compare two versions:**
```bash
abidiff --suppressions config/suppressions/onedal.txt \
    baselines/dal/dal_2025.9.0.abi \
    baselines/dal/dal_2025.10.0.abi
```

**3. Full historical analysis:**
```bash
python3 scripts/compare_all_history.py
```

### Exit Codes

| Code | Meaning | SemVer Compliance |
|------|---------|-------------------|
| 0 | No ABI changes | ✅ Patch/Minor OK |
| 4 | Compatible additions only | ✅ Minor OK, ⚠️ Patch fails |
| 8 | Incompatible changes | ❌ Requires major version |
| 12 | Breaking changes (symbols removed) | ❌ Requires major version |

## 📁 Project Structure

```
oneapi-abi-tracker/
├── scripts/                          # Automation scripts
│   ├── process_single_version.sh     # Download→analyze→cleanup for one version
│   ├── compare_all_history.py        # Full sequential comparison
│   ├── parse_headers.py              # Extract public API from C++ headers
│   └── ...
├── config/
│   ├── suppressions/onedal.txt       # Filter internal symbols (MKL, TBB, etc.)
│   └── package_configs/onedal.yaml   # Package metadata (APT/conda/PyPI)
├── docs/
│   └── onedal_package_distribution.md # Package naming reference
└── README.md                          # This file
```

**Note:** ABI baselines and reports are **not** included in this repository (287MB total). They are generated locally during analysis.

## 🛠️ Development Roadmap

### Phase 1: Core Infrastructure ✅ (Complete)
- [x] Multi-source package downloading (conda-forge, Intel conda, Intel APT)
- [x] ABI baseline generation using libabigail
- [x] Sequential version comparison pipeline
- [x] Internal symbol suppression (MKL, TBB, compiler internals)
- [x] Public vs private API categorization from headers

### Phase 2: Validation & Analysis (Current)
- [ ] Full comparison report for all 35 versions
- [ ] Semantic versioning compliance validation
- [ ] Breaking change categorization (public vs private API)
- [ ] Regression detection (re-introduced removed symbols)
- [ ] JSON output format for CI/CD integration

### Phase 3: Automation
- [ ] GitHub Actions workflow for CI/CD
- [ ] Automated detection of new releases
- [ ] PR checks: fail on breaking changes in minor/patch
- [ ] Weekly monitoring cron job
- [ ] Slack/email notifications for new releases

### Phase 4: Extensions
- [ ] Extend to other oneAPI libraries:
  - oneTBB (Threading Building Blocks)
  - oneMKL (Math Kernel Library)
  - oneDNN (Deep Neural Network Library)
- [ ] Cross-library compatibility matrix
- [ ] Historical trend analysis dashboard
- [ ] API stability score per package

### Phase 5: Integration
- [ ] Integrate into oneDAL upstream CI
- [ ] Public ABI compatibility database (GitHub Pages)
- [ ] conda-forge feedstock ABI checks
- [ ] Documentation generator from ABI diffs

## 🔍 Key Findings

From completed analysis of oneDAL 2021-2025:

1. **SemVer Violation Found:** 2025.1.0 → 2025.2.0 removed move assignment operators (`array<T>::operator=(array&&)`) — should have been 2026.0.0

2. **Major Refactoring:** 2025.0 → 2025.4 removed 786 symbols (743 internal MKL/TBB, 43 public)

3. **Stable Period:** 2025.4 → 2025.10 shows no ABI changes (all exit code 0)

4. **Pattern:** Early 2021 releases had frequent breaking changes as API stabilized

## 📦 Package Naming Reference

**CRITICAL:** oneDAL has different package names across channels:

| Channel | Runtime Package | Headers Package | Devel Package |
|---------|----------------|-----------------|---------------|
| conda-forge / Intel conda | `dal` | `dal-include` | `dal-devel` |
| Intel APT | `intel-oneapi-dal-YYYY.X` | (in `-devel`) | `intel-oneapi-dal-devel-YYYY.X` |
| PyPI | `scikit-learn-intelex` (embeds oneDAL) | (embedded) | N/A |

**Always use official CLI tools:**
- `micromamba search -c conda-forge dal` (NOT curl to repodata.json)
- `apt-cache search intel-oneapi-dal` (NOT wget to pool/)
- `pip search scikit-learn-intelex`

See `docs/onedal_package_distribution.md` for complete reference.

## 🤝 Contributing

This is an experimental tool developed for Intel oneDAL team. Contributions welcome:

1. **Bug reports:** Open issue with reproduction steps
2. **Feature requests:** Describe use case and expected behavior
3. **Pull requests:** Include tests and documentation

### Testing Locally

```bash
# Process a test version
bash scripts/process_single_version.sh dal 2025.0.0

# Verify baseline created
ls workspace/baselines/dal/dal_2025.0.0.abi

# Compare with next version
bash scripts/process_single_version.sh dal 2025.0.1
abidiff --suppressions config/suppressions/onedal.txt \
    workspace/baselines/dal/dal_2025.0.0.abi \
    workspace/baselines/dal/dal_2025.0.1.abi
```

## 📄 License

MIT License (or Intel internal — TBD)

## 🔗 Related Projects

- [libabigail](https://sourceware.org/libabigail/) — ABI analysis framework
- [oneapi-src/oneDAL](https://github.com/oneapi-src/oneDAL) — oneDAL upstream
- [conda-forge/dal-feedstock](https://github.com/conda-forge/dal-feedstock) — conda-forge packaging

## 📧 Contact

- **Maintainer:** Nikolay Petrov (Intel)
- **Issues:** GitHub Issues
- **Discussions:** Intel tasks Telegram group

---

**Status:** Experimental | Active Development | Intel Internal
