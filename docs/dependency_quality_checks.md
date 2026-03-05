# Dependency Quality Checker — Specification

## Overview

This document specifies a **dependency quality checker** for Intel oneAPI packages across three distribution channels: APT, Conda, and PyPI. The checker is intended to run as a CI gate or standalone audit tool, evaluating whether package dependency declarations follow the appropriate constraint policy for each channel.

It complements the ABI compatibility scanner: while the ABI scanner tells you *whether binaries are compatible*, the dependency checker tells you *whether the package manager will even select a compatible set*.

---

## Motivation and Background

An ABI-compatible library release can still cause user failures if the dependency declarations allow an incompatible combination to be installed. Analysis of Intel oneAPI packages across APT, Conda, and PyPI revealed:

- ~20% of all dependency edges are **unversioned** (no constraint at all)
- ~42% are **min-only** (`>=`) with no upper bound
- Regressions occurred in recent packages where previously present constraints were silently dropped
- Inconsistency across channels: same package has exact pins in Conda but unversioned in PyPI

The checker prevents regressions before release and drives toward a consistent, channel-appropriate policy.

---

## Checks to Implement

### CHECK-1: Unversioned dependency detection (Critical)

**What:** Flag any dependency edge with no version constraint at all.

**Target channels:** APT (`Depends`), Conda (`run`), PyPI (`requires_dist`)

**Policy:** Unversioned is only acceptable for leaf system packages with OS-managed ABI guarantees (e.g., `libc6`, `libgcc-ng` when managed by conda's `run_exports`).

**Classification:** FAIL for:
- Any Intel-family package (`intel-*`, `mkl*`, `tbb*`, `daal*`, `dnnl*`, `dal*`, `oneccl*`, `dpcpp*`)
- Any ABI-sensitive system library: `libgcc-ng`, `libstdcxx-ng`, `libstdc++6`, compiler runtimes

**Output:**
```text
[FAIL] mkl_umath -> intel-cmplr-lib-rt (unversioned)
       Channel: PyPI | Severity: Critical
       Fix: add intel-cmplr-lib-rt>=2025.3,<2026
```

---

### CHECK-2: Min-only dependency on known ABI-sensitive libraries (High)

**What:** Flag `>=`-only constraints on libraries known to have ABI incompatibility between major versions.

**ABI-sensitive library list (configurable):**
```text
intel-cmplr-lib-rt, intel-cmplr-lib-ur, intel-sycl-rt, intel-opencl-rt,
intel-openmp, tbb, mkl, daal, dnnl, oneccl, impi_rt, numpy, scipy
```

**Policy:** All dependencies on ABI-sensitive libraries should use bounded range (`>=X,<Y`) or wildcard pin (`==X.*`).

**Output:**
```text
[WARN] scikit-learn-intelex -> numpy>=1.21.6 (min-only, no upper cap)
       Channel: PyPI | Severity: High
       Risk: NumPy major version bumps may change C API
       Fix: numpy>=1.21.6,<3.0
```

---

### CHECK-3: Regression detection (Critical)

**What:** Compare dependency constraints between consecutive package versions. Flag any case where a constraint becomes *weaker* (e.g., `>=X` → unversioned, or specific pin → `*`).

**Algorithm:**
1. For each package name, collect dep specs across sorted version history.
2. For each dependency target, compare constraint at version N vs version N+1.
3. Flag if constraint specificity decreased:
   - exact → wildcard: WARN
   - wildcard → min-only: WARN
   - bounded → min-only: WARN
   - anything → unversioned: FAIL
   - dep target removed: INFO (may be intentional rename)

**This check requires access to multiple versions of the same package.**

**Output:**
```text
[FAIL] intel-oneapi-ccl-devel: dep on intel-oneapi-ccl-2021.x
       2021.15 -> >=2021.15.2-6   (was: versioned)
       2021.16 -> (unversioned)   REGRESSION DETECTED
```

---

### CHECK-4: Cross-channel consistency (Medium)

**What:** Compare constraint strictness for the same logical dependency across channels.

**Example:**
- Conda: `mkl_umath -> intel-cmplr-lib-rt` (unversioned)
- PyPI: `mkl-umath -> intel-cmplr-lib-rt` (unversioned)
- Both same: consistent but both wrong → still fails CHECK-1

**Cross-channel rule:** If a dep is exact-pinned in one channel and unversioned in another for the same package, flag the weaker channel.

**Output:**
```text
[WARN] numba-dpex -> dpcpp-cpp-rt:
       Conda: exact pin (via run_exports)
       PyPI: unversioned
       Cross-channel inconsistency detected.
```

---

### CHECK-5: Wildcard upper-bound completeness (Medium)

**What:** Flag wildcard pins (`==2022.*`) that have no accompanying lower bound. A wildcard pin without a floor could install old patch versions.

**Policy:** Wildcard pins should be accompanied by an explicit minimum:
```text
Good:  tbb>=2022.3,<2023  (or tbb==2022.*)
Bad:   tbb==2022.*        if earliest known good is 2022.3
```

**Output:**
```text
[INFO] dal -> tbb==2022.* (wildcard with no floor)
       Latest known-good: tbb 2022.3.1
       Consider: tbb>=2022.3,<2023
```

---

### CHECK-6: APT-specific: naming scheme vs. constraint gap (Medium)

**What:** For APT packages using Intel's line-versioned naming (e.g., `intel-oneapi-tbb-2022.3`), check if unversioned dependencies on the *same named package* are missing even a minor-build lower bound.

**Logic:**
- Dep target includes version in name: isolation by naming — acceptable as LOW risk.
- Dep target is generic (no version in name) + unversioned constraint: HIGH risk.
- Dep target includes version in name + was previously versioned + now unversioned: regression per CHECK-3.

---

### CHECK-7: APT-specific: `common-vars` upper-bound (Low)

**What:** Check that Intel APT packages with `Depends: intel-oneapi-common-vars (>= YYYY.x)` also include an upper-cap of the next year: `(>= YYYY.x), (<< YYYY+1)`.

**Output:**
```text
[INFO] intel-oneapi-mkl-core-2025.3 -> intel-oneapi-common-vars (>= 2025.3.0-0)
       No upper cap. Add: intel-oneapi-common-vars (<< 2026)
```

---

## Data Model

```python
@dataclass
class DepEdge:
    pkg_name: str          # source package
    pkg_version: str       # source version
    dep_target: str        # dependency name
    constraint: str        # raw constraint string (may be empty)
    channel: str           # "apt" | "conda" | "pypi"
    kind: str              # "unversioned" | "min_only" | "bounded_range"
                           # | "wildcard_pin" | "exact_pin" | "other"
    is_abi_sensitive: bool # derived from known-list

@dataclass
class CheckResult:
    check_id: str          # "CHECK-1" .. "CHECK-7"
    severity: str          # "FAIL" | "WARN" | "INFO"
    pkg_name: str
    dep_target: str
    constraint: str
    channel: str
    message: str
    suggested_fix: str | None
```

---

## Output Formats

- **Console (default):** colored FAIL/WARN/INFO lines, grouped by package
- **JSON:** machine-readable for CI integration
- **Markdown:** suitable for PR comments and audit reports

---

## Integration Points

| Channel | Data Source | Implementation path |
|---------|-------------|---------------------|
| APT | `dpkg-deb -f pkg.deb Depends` | Extend existing APT source (`sources/apt.py`) |
| Conda | `repodata.json` → `depends` key | New `sources/conda.py` extension or standalone |
| PyPI | `pypi.org/pypi/{pkg}/json` → `requires_dist` | New source; HTTP fetch |
| Regression | versioned `.deb` / repodata history | Extend `compare_all_history.py` |

---

## Configuration

Each channel's policy is configurable via YAML:

```yaml
# config/dep_check_policy.yaml

abi_sensitive_libraries:
  - intel-cmplr-lib-rt
  - intel-cmplr-lib-ur
  - intel-sycl-rt
  - intel-opencl-rt
  - intel-openmp
  - tbb
  - mkl
  - daal
  - dnnl
  - oneccl
  - impi_rt
  - numpy
  - scipy

channels:
  apt:
    unversioned_abi_sensitive: FAIL
    regression_detected: FAIL
    min_only_abi_sensitive: WARN
    common_vars_no_upper_cap: INFO

  conda:
    unversioned_abi_sensitive: FAIL
    min_only_abi_sensitive: WARN
    cross_channel_inconsistency: WARN

  pypi:
    unversioned_abi_sensitive: FAIL
    min_only_abi_sensitive: WARN
    cross_channel_inconsistency: WARN
```

---

## Scope Not Covered (Future Work)

- Conda `build`/`host`/`constrains` fields
- APT `Recommends`, `Suggests`, `Conflicts`, `Breaks`
- conda-forge repacks
- Docker image dependency chains
- Transitive dependency closure analysis
