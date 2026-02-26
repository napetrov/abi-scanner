# ABI Scanner — Цели и Архитектура

**Дата:** 2026-02-21  
**Статус:** Experimental  
**Цель:** Универсальная утилита для сравнения ABI совместимости пакетов из разных каналов

---

## 🎯 Ключевая Цель

**Создать CLI-инструмент для сравнения бинарной совместимости (ABI) любых C/C++ библиотек, распространяемых через package managers.**

### Проблема

Разработчики и пользователи C/C++ библиотек не имеют простого способа проверить:
- Совместима ли версия из conda-forge с версией из Intel channel?
- Можно ли обновить библиотеку без перекомпиляции приложения?
- Какая версия последняя ABI-compatible с моей текущей?

### Решение

Универсальная CLI утилита:
```bash
abi-scanner compare \
  --old conda-forge:dal=2025.9.0 \
  --new intel:dal=2025.10.0 \
  --format json

# Output: compatible/breaking + detailed diff
```

**Поддержка множества источников:**
- conda/mamba channels (conda-forge, Intel, defaults)
- APT repositories (Intel oneAPI, system packages)
- PyPI wheels (с embedded .so)
- Local files (.deb, .rpm, .whl, .so)

---

## 🏗️ Архитектура

### Компоненты Системы

```
┌─────────────────────────────────────────────────────────┐
│                    CLI Interface                         │
│  abi-scanner compare/analyze/history/validate           │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────────┐
│              Package Source Adapters                     │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐   │
│  │  Conda  │  │   APT   │  │  PyPI   │  │  Local  │   │
│  │ Adapter │  │ Adapter │  │ Adapter │  │  File   │   │
│  └─────────┘  └─────────┘  └─────────┘  └─────────┘   │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────────┐
│           Package Extraction Layer                       │
│  - Download temporary copy                               │
│  - Extract .so/.dylib from package                       │
│  - Handle different formats (.deb, .tar.bz2, .whl)       │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────────┐
│              ABI Analysis Engine                         │
│  - Generate ABI baseline (libabigail/abidw)             │
│  - Compare baselines (abidiff)                           │
│  - Apply suppressions (filter internal symbols)          │
│  - Cache baselines for reuse                             │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────────┐
│            Result Formatting Layer                       │
│  - JSON output (machine-readable)                        │
│  - Human-readable summary                                │
│  - CI exit codes (0/4/8/12)                              │
│  - Markdown reports                                      │
└──────────────────────────────────────────────────────────┘
```

### Data Flow

```
User Input → Package Spec → Download → Extract → Analyze → Compare → Report
    ↓            ↓              ↓          ↓         ↓         ↓
"conda:dal   resolve to   fetch from   find .so   abidw    abidiff   JSON/text
 =2025.9"    real URL     channel      files      →.abi    →diff
```

---

## 👤 User Experience (UX)

### Use Case 1: Сравнение двух версий

**Input:**
```bash
abi-scanner compare \
  --old conda-forge:dal=2025.9.0 \
  --new conda-forge:dal=2025.10.0
```

**Output:**
```
Comparing ABI: dal 2025.9.0 → 2025.10.0
Source: conda-forge (linux-64)

Status: ✅ COMPATIBLE (exit code: 0)
  No ABI changes detected

Summary:
  Functions: 0 removed, 0 changed, 0 added
  Variables: 0 removed, 0 changed, 0 added
  
Baseline cached: ~/.abi-scanner/cache/dal_2025.9.0.abi
                 ~/.abi-scanner/cache/dal_2025.10.0.abi
```

**Alternative Output (JSON):**
```bash
abi-scanner compare ... --format json
```
```json
{
  "old": {"channel": "conda-forge", "package": "dal", "version": "2025.9.0"},
  "new": {"channel": "conda-forge", "package": "dal", "version": "2025.10.0"},
  "status": "compatible",
  "exit_code": 0,
  "changes": {
    "functions": {"removed": 0, "changed": 0, "added": 0},
    "variables": {"removed": 0, "changed": 0, "added": 0}
  }
}
```

### Use Case 2: Cross-Channel Comparison

**Вопрос:** "Intel dal совместим с conda-forge dal?"

```bash
abi-scanner compare \
  --old conda-forge:dal=2025.9.0 \
  --new intel:dal=2025.9.0
```

**Output:**
```
Comparing ABI: dal 2025.9.0 (conda-forge vs intel)

Status: ❌ BREAKING (exit code: 12)
  7 symbols removed, 3 symbols added

Removed (breaking):
  - oneapi::dal::array<int>::operator=(array&&)
  - oneapi::dal::array<float>::operator=(array&&)
  ...

Warning: These are different builds of the same version!
Recommendation: Stick to one channel for consistency.
```

### Use Case 3: Find Compatible Versions

**Вопрос:** "Какую новую версию dal я могу использовать вместо 2025.8.0?"

```bash
abi-scanner compatible \
  --current conda-forge:dal=2025.8.0 \
  --newer
```

**Output:**
```
Checking compatible upgrades for dal=2025.8.0 (conda-forge)

✅ dal=2025.9.0  (compatible, +3 symbols)
✅ dal=2025.10.0 (compatible, no changes)
❌ dal=2025.11.0 (breaking, -5 symbols)

Recommendation: Safe to upgrade to 2025.10.0
```

### Use Case 4: Validate SemVer

**Вопрос:** "Соответствует ли версионирование oneDAL Semantic Versioning?"

```bash
abi-scanner validate \
  --package conda-forge:dal \
  --versions 2025.0.0:2025.10.0
```

**Output:**
```
Validating SemVer compliance for dal (2025.0.0 → 2025.10.0)

✅ 2025.0.0 → 2025.0.1  (patch, exit 0)
✅ 2025.0.1 → 2025.1.0  (minor, exit 4, additions only)
❌ 2025.1.0 → 2025.2.0  (minor, exit 12, BREAKING!)
   Violation: removed symbols in minor version

SemVer compliance: 89% (25/28 transitions valid)
Violations: 3
```

### Use Case 5: Local File Comparison

**Вопрос:** "Я собрал библиотеку локально, совместима ли она с conda версией?"

```bash
abi-scanner compare \
  --old conda-forge:dal=2025.9.0 \
  --new local:/path/to/my/libonedal.so
```

### Use Case 6: CI/CD Integration

**.github/workflows/abi-check.yml:**
```yaml
- name: Check ABI compatibility
  run: |
    abi-scanner compare \
      --old conda-forge:dal=${{ github.base_ref }} \
      --new local:./build/libonedal.so \
      --format json \
      --fail-on breaking
```

---

## 📋 Что УЖЕ Работает (Implemented)

### ✅ CLI Commands
- [x] **`abi-scanner compare`** — полный pipeline conda/apt/local
  - Intel conda, conda-forge, APT, local (.so / archives)
  - Suppression файлы, JSON output, --fail-on
- [x] **`abi-scanner list`** — перечисление доступных версий
  - Intel conda, conda-forge (micromamba search)
  - Intel APT (Packages.gz parsing)
  - --filter regex, --format json
- [x] **`abi-scanner compatible`** — поиск совместимого диапазона версий
  - base version → сравнение со всеми более новыми
  - --stop-at-first-break, --fail-on, --format json
- [ ] **`abi-scanner validate`** — planned (SemVer compliance)

### ✅ Package Sources
- [x] **Conda/mamba** — CondaSource adapter
  - conda-forge, Intel channel
  - `list_versions()`, download, extract, find .so
- [x] **Intel APT** — AptSource adapter
  - `resolve_url()` — Packages.gz URL resolution
  - `list_versions()` — Packages.gz version enumeration
  - Download .deb, extract via dpkg-deb
- [x] **Local files** — LocalSource adapter
  - .so файлы напрямую
  - Архивы (.deb, .conda, .tar.gz, .zip) → extract then find

### ✅ ABI Analysis
- [x] **Baseline generation** — abidw
- [x] **Comparison** — abidiff, exit codes (0/4/8/12)
- [x] **Symbol Filtering** — suppression конфиги
  - `config/suppressions/oneccl.txt` — oneCCL
  - `config/suppressions/compiler.txt` — DPC++ compiler (libsycl)

### ✅ Output Formats
- [x] **Text** — human-readable с verdict/статистикой
- [x] **JSON** — machine-readable для CI
- [x] **Exit codes** — 0/4/8/12 для CI/CD

### ✅ Package Configs
- [x] `config/package_configs/oneccl.yaml`
- [x] `config/package_configs/compiler.yaml`

### ✅ Scripts
- [x] `compare_all_history.py` — batch history (conda + APT channels)
  - APT channel support (--apt-pkg-pattern, --apt-base-url)
  - Lazy micromamba init, validated --filter-version regex

### ✅ Known ABI Results
- oneCCL 2021.14.0→2021.14.1: NO_CHANGE
- oneCCL 2021.14.x→2021.15.0: BREAKING (-2 +20)
- DPC++ libsycl 2025.0.x: Stable patch series
- DPC++ libsycl 2025.0→2025.1: BREAKING (-1 +78)
- DPC++ libsycl 2025.1→2025.2: BREAKING (-7 +94)
- DPC++ libsycl 2025.2→2025.3: COMPATIBLE (+164)

---

## 📋 Что НАДО Сделать (TODO)

### ✅ CLI Interface — DONE (PR #10, #11, #12)
- [x] `abi-scanner compare` — conda, apt, local
- [x] `abi-scanner list` — conda, apt
- [x] `abi-scanner compatible` — find ABI-compatible version range
- [x] Package spec parser: `channel:package=version`
- [x] Source adapters: CondaSource, AptSource, LocalSource

### ❌ Advanced Features (Priority 1)

### ❌ Advanced Features (Priority 1)
- [x] **Version discovery** — `abi-scanner list` (PR #11)
- [x] **Compatible version finder** — `abi-scanner compatible` (PR #12)
- [ ] **SemVer validation** — `abi-scanner validate` (planned PR #13)
  - Batch check all transitions for a version range
  - Report SemVer violations with evidence
- [ ] **Cross-channel comparison**
  - conda-forge:dal vs intel:dal
  - Detection of different builds

### ❌ Output & Reporting (Priority 2)
- [ ] **JSON output** — machine-readable
  - Structured format for CI
  - Detailed diff in JSON

- [ ] **Markdown reports**
  - GitHub-friendly format
  - Tables, badges, summaries

- [ ] **CI-friendly flags**
  - `--fail-on breaking` — exit 1 if breaking
  - `--allow additions` — permit exit code 4

### ❌ Performance & Caching (Priority 3)
- [ ] **Baseline cache** — ~/.abi-scanner/cache/
  - Reuse downloaded packages
  - Reuse generated .abi files
  - Cache invalidation strategy

- [ ] **Parallel processing**
  - Download multiple versions concurrently
  - Parallel baseline generation

### ❌ Error Handling (Priority 3)
- [ ] Package not found → clear error message
- [ ] Network failures → retry logic
- [ ] Unsupported package type → graceful fail

### ❌ Documentation (Priority 2)
- [ ] Man page (`man abi-scanner`)
- [ ] Tutorial: first comparison
- [ ] Cookbook: common use cases
- [ ] API reference for JSON output

---

## 🗺️ Implementation Plan

### Phase 1: CLI Unification (Week 1-2)
**Goal:** Single `abi-scanner` command for all operations

**Tasks:**
1. Create main CLI entry point (Python Click/argparse)
2. Implement package spec parser: `channel:package=version`
3. Refactor existing scripts into subcommands
4. Add --format json flag
5. Comprehensive help text

**Deliverable:** `abi-scanner compare conda-forge:dal=2025.9 conda-forge:dal=2025.10` works

### Phase 2: Channel Abstraction (Week 3)
**Goal:** Generic source adapter interface

**Tasks:**
1. Define `PackageSource` interface
2. Refactor conda logic into CondaSource adapter
3. Refactor APT logic into APTSource adapter
4. Implement LocalFileSource adapter
5. Auto-detect source from spec

**Deliverable:** Cross-channel comparison works

### Phase 3: Advanced Features (Week 4-5)
**Goal:** User-requested features

**Tasks:**
1. Implement `compatible` subcommand (version finder)
2. Implement `validate` subcommand (SemVer checker)
3. Implement `list` subcommand (version discovery)
4. JSON output format
5. --fail-on flag for CI

**Deliverable:** All use cases from UX section work

### Phase 4: Polish & Documentation (Week 6)
**Goal:** Production-ready tool

**Tasks:**
1. Error handling & retries
2. Baseline caching
3. Man page & tutorial
4. GitHub Actions example
5. Release v0.1.0

**Deliverable:** Public announcement & adoption

---

## 📊 Success Metrics

### Technical
- **CLI works:** All 6 use cases executable
- **Multi-source:** ≥3 package sources supported (conda, APT, local)
- **Performance:** <5 min to compare two versions (cold cache)
- **Cache hit rate:** >80% on repeated comparisons

### Adoption
- **External users:** ≥5 people outside Intel use the tool
- **GitHub activity:** ≥10 stars, ≥3 contributors
- **CI integrations:** ≥2 projects use in GitHub Actions

### Impact
- **Bugs caught:** ≥1 ABI break detected in PR before merge
- **SemVer violations:** Document ≥3 violations with evidence

---

## 🚧 Risks

### Risk: libabigail limitations
**Mitigation:** Test with diverse libraries, fallback to abi-compliance-checker

### Risk: Package format diversity
**Mitigation:** Start with mainstream (conda, APT), expand incrementally

### Risk: Performance (large libraries)
**Mitigation:** Implement caching early, parallel processing

### Risk: Maintenance burden
**Mitigation:** Clear abstractions, automated tests, community contributions

---

## 🧪 Testing Strategy

### Unit Tests
- Package spec parser
- Channel adapters (mock downloads)
- Output formatters

### Integration Tests
- Full comparison flow (real conda packages)
- Cross-channel comparison
- SemVer validation

### End-to-End Tests
- CI workflow simulation
- Error scenarios (network failures, bad packages)

---

## 📦 Current Status

**oneDAL Experiment:** ✅ Complete
- 35 versions analyzed (proof of concept)
- Demonstrates tool feasibility
- Identified real SemVer violation (2025.1→2025.2)

**Next:** Build generic CLI tool (Phase 1-4 above)

---

**Last Updated:** 2026-02-25  
**Next Review:** After validate command (PR #13)
