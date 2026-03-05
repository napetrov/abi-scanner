"""
abi_scanner/dep_checker.py

Dependency Quality Checker for Intel oneAPI packages.
Specification: docs/dependency_quality_checks.md

Checks implemented (stubs — ready for full implementation):
  CHECK-1: Unversioned dependencies on ABI-sensitive libraries
  CHECK-2: Min-only constraints on ABI-sensitive libraries (no upper cap)
  CHECK-3: Regression detection (constraint weakened between versions)
  CHECK-4: Cross-channel consistency
  CHECK-5: Wildcard pin without floor
  CHECK-6: APT name-versioned package gap (stub)
  CHECK-7: APT common-vars upper-bound missing
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterator


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

class Channel(str, Enum):
    APT = "apt"
    CONDA = "conda"
    PYPI = "pypi"


class ConstraintKind(str, Enum):
    UNVERSIONED = "unversioned"
    MIN_ONLY = "min_only"            # >= only
    BOUNDED_RANGE = "bounded_range"  # >= and <
    WILDCARD_PIN = "wildcard_pin"    # ==X.*
    EXACT_PIN = "exact_pin"          # ==X.Y.Z or APT exact =X.Y.Z
    OTHER = "other"


class Severity(str, Enum):
    FAIL = "FAIL"
    WARN = "WARN"
    INFO = "INFO"


# Libraries where ABI compatibility across major versions cannot be assumed.
ABI_SENSITIVE_PACKAGES: frozenset[str] = frozenset({
    "intel-oneapi-tbb", "intel-oneapi-tbb-devel",
    "intel-oneapi-mkl", "intel-oneapi-mkl-core", "intel-oneapi-mkl-devel",
    "intel-oneapi-ccl", "intel-oneapi-ccl-devel",
    "intel-oneapi-dal", "intel-oneapi-dal-devel",
    "intel-oneapi-dnnl", "intel-oneapi-dnnl-devel",
    "intel-oneapi-omp", "libiomp5",
    "intel-cmplr-lib-rt", "intel-cmplr-lic-rt", "intel-cmplr-lib-ur",
    "intel-openmp", "mkl", "tbb", "impi_rt", "impi-devel",
    "intel-sycl-rt", "intel-opencl-rt",
    "numpy", "scipy", "libstdc++6", "libstdcxx-ng", "libgcc-ng",
})
ABI_SENSITIVE_PREFIXES: tuple[str, ...] = ("intel-oneapi-", "intel-cmplr-", "libmkl", "libtbb")


@dataclass
class DepEdge:
    """A single dependency edge from one package to another."""

    pkg_name: str
    pkg_version: str
    dep_target: str
    constraint: str          # raw constraint string (empty = unversioned)
    channel: Channel
    kind: ConstraintKind = field(init=False)
    is_abi_sensitive: bool = field(init=False)

    def __post_init__(self) -> None:
        self.kind = classify_constraint(self.dep_target, self.constraint, self.channel)
        self.is_abi_sensitive = is_abi_sensitive(self.dep_target)


@dataclass
class CheckResult:
    """Result of a single check on a single dependency edge."""

    check_id: str
    severity: Severity
    pkg_name: str
    dep_target: str
    constraint: str
    channel: Channel
    message: str
    suggested_fix: str | None = None


# ---------------------------------------------------------------------------
# Constraint classification helpers
# ---------------------------------------------------------------------------

def classify_constraint(dep_name: str, constraint: str, channel: Channel) -> ConstraintKind:
    """Classify a raw constraint string into a ConstraintKind."""
    if not constraint.strip():
        return ConstraintKind.UNVERSIONED

    c = constraint.strip()

    # Conda exact pin style: "2025.3.2 intel_832" (no operators, has digits, no wildcard)
    if channel == Channel.CONDA:
        parts = c.split()
        if parts and all(op not in parts[0] for op in [">", "<", "=", "!", "*"]):
            if re.search(r"\d", parts[0]):
                return ConstraintKind.EXACT_PIN

    # Wildcard: ==X.*  or  X.*
    if re.search(r"==?\s*[\d.]+\.\*", c) or re.search(r"^[\d.]+\.\*$", c):
        return ConstraintKind.WILDCARD_PIN

    # PyPI / Conda == exact (no wildcard)
    if "==" in c and "*" not in c:
        return ConstraintKind.EXACT_PIN

    # APT exact (single =, not >=)
    if re.match(r"^=\s*\S+", c) and "==" not in c and ">=" not in c:
        return ConstraintKind.EXACT_PIN

    # Bounded range: has both >= and <
    if ">=" in c and ("<" in c or "<<" in c):
        return ConstraintKind.BOUNDED_RANGE

    # Min only
    if ">=" in c or ">>" in c:
        return ConstraintKind.MIN_ONLY

    return ConstraintKind.OTHER


def is_abi_sensitive(dep_target: str) -> bool:
    """Return True if dep_target matches any known ABI-sensitive library."""
    n = dep_target.lower()
    return n in ABI_SENSITIVE_PACKAGES or any(n.startswith(p) for p in ABI_SENSITIVE_PREFIXES)


def is_intel_name_versioned(dep_target: str) -> bool:
    """Return True if dep_target uses Intel's line-versioned naming convention.

    E.g.: intel-oneapi-tbb-2022.3, intel-oneapi-ccl-2021.17 — major line is
    encoded in the package name itself, providing implicit version isolation.
    Uses character class [a-z0-9-]+ to match hyphenated component names.
    """
    return bool(
        re.search(r"intel-oneapi-[a-z0-9-]+-\d{4}(?:\.\d+)*", dep_target.lower())
    )


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def check1_unversioned(edges: list[DepEdge]) -> Iterator[CheckResult]:
    """CHECK-1: Unversioned dependency on ABI-sensitive library."""
    for e in edges:
        if e.kind == ConstraintKind.UNVERSIONED and e.is_abi_sensitive:
            # Partial exception: Intel name-versioned targets are lower severity
            if is_intel_name_versioned(e.dep_target):
                severity = Severity.WARN
                note = " (name-versioned target — lower actual risk)"
            else:
                severity = Severity.FAIL
                note = ""
            yield CheckResult(
                check_id="CHECK-1",
                severity=severity,
                pkg_name=e.pkg_name,
                dep_target=e.dep_target,
                constraint="(unversioned)",
                channel=e.channel,
                message=f"Unversioned dependency on ABI-sensitive library{note}",
                suggested_fix=f"Add constraint, e.g. {e.dep_target}>=<current>,<next_major>",
            )


def check2_min_only(edges: list[DepEdge]) -> Iterator[CheckResult]:
    """CHECK-2: Min-only constraint on ABI-sensitive library (no upper bound)."""
    for e in edges:
        if e.kind == ConstraintKind.MIN_ONLY and e.is_abi_sensitive:
            yield CheckResult(
                check_id="CHECK-2",
                severity=Severity.WARN,
                pkg_name=e.pkg_name,
                dep_target=e.dep_target,
                constraint=e.constraint,
                channel=e.channel,
                message="Min-only constraint on ABI-sensitive library; no upper bound",
                suggested_fix=f"Add upper cap, e.g. {e.dep_target}>=X,<next_major",
            )


def check3_regression(
    history: dict[str, list[DepEdge]],
) -> Iterator[CheckResult]:
    """CHECK-3: Constraint weakened between consecutive package versions.

    ``history`` maps package name to a list of ``DepEdge`` objects sorted by
    version ascending (caller's responsibility).  Channel is included in the
    grouping key to avoid mixing APT and Conda edges for the same package name.
    """
    SEVERITY_ORDER = [
        ConstraintKind.EXACT_PIN,
        ConstraintKind.BOUNDED_RANGE,
        ConstraintKind.WILDCARD_PIN,
        ConstraintKind.MIN_ONLY,
        ConstraintKind.UNVERSIONED,
        ConstraintKind.OTHER,
    ]

    def strictness(kind: ConstraintKind) -> int:
        try:
            return SEVERITY_ORDER.index(kind)
        except ValueError:
            return len(SEVERITY_ORDER)

    # Group by (pkg_name, dep_target, channel) — channel prevents cross-channel mixing.
    grouped: dict[tuple[str, str, Channel], list[DepEdge]] = defaultdict(list)
    for _pkg_name, edges in history.items():
        for e in edges:
            grouped[(e.pkg_name, e.dep_target, e.channel)].append(e)

    for (_pkg, dep, ch), edges in grouped.items():
        # Caller contract: edges already sorted by version; we respect that order.
        for prev, curr in zip(edges, edges[1:], strict=False):
            if strictness(curr.kind) > strictness(prev.kind):
                severity = (
                    Severity.FAIL
                    if curr.kind == ConstraintKind.UNVERSIONED
                    else Severity.WARN
                )
                yield CheckResult(
                    check_id="CHECK-3",
                    severity=severity,
                    pkg_name=curr.pkg_name,
                    dep_target=dep,
                    constraint=curr.constraint,
                    channel=ch,
                    message=(
                        f"Constraint regression: {prev.pkg_version} had "
                        f"{prev.kind.value!r} ({prev.constraint!r}), "
                        f"{curr.pkg_version} has {curr.kind.value!r} ({curr.constraint!r})"
                    ),
                    suggested_fix=f"Restore at least: {dep}{prev.constraint or '>=<version>'}",
                )


def check4_cross_channel(
    edges_by_channel: dict[Channel, list[DepEdge]],
) -> Iterator[CheckResult]:
    """CHECK-4: Same logical dep is stricter in one channel than another."""
    SEVERITY_ORDER = [
        ConstraintKind.EXACT_PIN,
        ConstraintKind.BOUNDED_RANGE,
        ConstraintKind.WILDCARD_PIN,
        ConstraintKind.MIN_ONLY,
        ConstraintKind.UNVERSIONED,
    ]

    def strictness(kind: ConstraintKind) -> int:
        try:
            return SEVERITY_ORDER.index(kind)
        except ValueError:
            return len(SEVERITY_ORDER)

    def norm(s: str) -> str:
        """Normalise package names for cross-channel comparison."""
        return re.sub(r"[-_]", "", s.lower().replace("intel-oneapi-", "").replace("intel.", ""))

    lookup: dict[tuple[str, str], dict[Channel, ConstraintKind]] = defaultdict(dict)
    # Store original (un-normalized) names for human-readable output
    orig_names: dict[tuple[str, str], tuple[str, str]] = {}
    for channel, edges in edges_by_channel.items():
        for e in edges:
            key = (norm(e.pkg_name), norm(e.dep_target))
            lookup[key][channel] = e.kind
            if key not in orig_names:
                orig_names[key] = (e.pkg_name, e.dep_target)

    for (_pkg, dep), by_ch in lookup.items():
        if len(by_ch) < 2:
            continue
        items = sorted(by_ch.items(), key=lambda x: strictness(x[1]))
        strictest_ch, strictest_kind = items[0]
        weakest_ch, weakest_kind = items[-1]
        if strictness(weakest_kind) > strictness(strictest_kind):
            orig_pkg, orig_dep = orig_names.get((_pkg, dep), (_pkg, dep))
            yield CheckResult(
                check_id="CHECK-4",
                severity=Severity.WARN,
                pkg_name=orig_pkg,
                dep_target=orig_dep,
                constraint=(
                    f"{strictest_ch.value}:{strictest_kind.value} vs "
                    f"{weakest_ch.value}:{weakest_kind.value}"
                ),
                channel=weakest_ch,
                message=(
                    f"Cross-channel inconsistency: {strictest_ch.value} uses "
                    f"{strictest_kind.value}, {weakest_ch.value} uses {weakest_kind.value}"
                ),
                suggested_fix=f"Align {weakest_ch.value} constraint to match {strictest_ch.value}",
            )


def check5_wildcard_no_floor(edges: list[DepEdge]) -> Iterator[CheckResult]:
    """CHECK-5: Wildcard pin without lower bound (no minimum patch guaranteed)."""
    for e in edges:
        if e.kind != ConstraintKind.WILDCARD_PIN:
            continue
        if ">=" in e.constraint or ">>" in e.constraint:
            continue
        yield CheckResult(
            check_id="CHECK-5",
            severity=Severity.INFO,
            pkg_name=e.pkg_name,
            dep_target=e.dep_target,
            constraint=e.constraint,
            channel=e.channel,
            message="Wildcard pin has no minimum floor; old patch versions may be selected",
            suggested_fix=(
                f"Add floor: {e.dep_target}>=<min_known_good> in addition to wildcard"
            ),
        )


def check6_apt_name_versioned_gap(edges: list[DepEdge]) -> Iterator[CheckResult]:
    """CHECK-6 (APT): name-versioned package with no explicit minor-build lower bound.

    Intel APT packages encode release lines in package names (e.g.
    ``intel-oneapi-tbb-2022.3``).  An unversioned constraint on such a target
    is lower risk than a truly generic unversioned dep, but still leaves the
    minor-build level unconstrained.  This check surfaces those cases so
    packagers can decide whether to add an explicit lower bound.
    """
    for e in edges:
        if e.channel != Channel.APT:
            continue
        if e.kind != ConstraintKind.UNVERSIONED:
            continue
        if not is_intel_name_versioned(e.dep_target):
            continue
        yield CheckResult(
            check_id="CHECK-6",
            severity=Severity.INFO,
            pkg_name=e.pkg_name,
            dep_target=e.dep_target,
            constraint="(unversioned, name-versioned target)",
            channel=e.channel,
            message=(
                "APT dep on name-versioned package has no explicit minor-build floor; "
                "patch-level drift is possible within the release line."
            ),
            suggested_fix=(
                f"Consider adding: {e.dep_target} (>= <min_patch_build>)"
            ),
        )


def check7_common_vars_no_upper_cap(edges: list[DepEdge]) -> Iterator[CheckResult]:
    """CHECK-7 (APT): intel-oneapi-common-vars has no upper-cap."""
    for e in edges:
        if e.channel != Channel.APT:
            continue
        if "common-vars" not in e.dep_target:
            continue
        if e.kind == ConstraintKind.MIN_ONLY:
            yield CheckResult(
                check_id="CHECK-7",
                severity=Severity.INFO,
                pkg_name=e.pkg_name,
                dep_target=e.dep_target,
                constraint=e.constraint,
                channel=e.channel,
                message=(
                    "common-vars has min-only constraint; "
                    "consider adding upper cap to prevent silent pickup of a future major release"
                ),
                suggested_fix="Add (<< NEXT_YEAR) alongside the existing lower bound",
            )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_all_checks(edges: list[DepEdge]) -> list[CheckResult]:
    """Run all single-version checks on a flat list of DepEdge."""
    results: list[CheckResult] = []
    for gen in [
        check1_unversioned(edges),
        check2_min_only(edges),
        check5_wildcard_no_floor(edges),
        check6_apt_name_versioned_gap(edges),
        check7_common_vars_no_upper_cap(edges),
    ]:
        results.extend(gen)
    return results


def format_results(results: list[CheckResult], *, color: bool = True) -> str:
    """Format check results for console output."""
    COLORS = {
        Severity.FAIL: "\033[31m",   # red
        Severity.WARN: "\033[33m",   # yellow
        Severity.INFO: "\033[36m",   # cyan
    }
    RESET = "\033[0m" if color else ""

    lines = []
    SEVERITY_RANK = {"FAIL": 0, "WARN": 1, "INFO": 2}
    for r in sorted(results, key=lambda x: (SEVERITY_RANK.get(x.severity.value, 99), x.pkg_name)):
        col = COLORS.get(r.severity, "") if color else ""
        lines.append(
            f"{col}[{r.severity.value}]{RESET} "
            f"{r.check_id} | {r.channel.value} | "
            f"{r.pkg_name} -> {r.dep_target} ({r.constraint})\n"
            f"         {r.message}"
        )
        if r.suggested_fix:
            lines.append(f"         Fix: {r.suggested_fix}")
    return "\n".join(lines)
