"""Factory for creating source adapters from PackageSpec channel."""

import os
import shutil
from pathlib import Path

from .apt import AptSource
from .base import PackageSource
from .conda import CondaSource
from .local import LocalSource
from ..package_spec import PackageSpec

_MICROMAMBA_CANDIDATES = [
    "micromamba",
    str(Path.home() / "bin" / "micromamba"),
    "/usr/local/bin/micromamba",
    "/opt/conda/bin/micromamba",
]


def _find_micromamba() -> str:
    """Auto-detect micromamba binary path."""
    for candidate in _MICROMAMBA_CANDIDATES:
        resolved = shutil.which(candidate) or (candidate if Path(candidate).is_file() else None)
        if resolved and Path(resolved).is_file() and os.access(resolved, os.X_OK):
            return resolved
    return "micromamba"  # let it fail with a clear error at runtime


def create_source(spec: PackageSpec) -> PackageSource:
    """Create the appropriate PackageSource implementation for a PackageSpec.

    Mapping:
    - conda-forge -> CondaSource(channel="conda-forge")
    - intel       -> CondaSource(channel=Intel URL)
    - apt         -> AptSource()
    - local       -> LocalSource()
    """
    if spec.channel == "conda-forge":
        return CondaSource(channel="conda-forge", executable=_find_micromamba())
    if spec.channel == "intel":
        return CondaSource(
            channel="https://software.repos.intel.com/python/conda",
            executable=_find_micromamba()
        )
    if spec.channel == "apt":
        return AptSource()
    if spec.channel == "local":
        return LocalSource()

    raise ValueError(f"Unsupported source channel: {spec.channel}")
