"""Factory for creating source adapters from PackageSpec channel."""

from .apt import AptSource
from .conda import CondaSource
from .local import LocalSource
from ..package_spec import PackageSpec


def create_source(spec: PackageSpec):
    """Create the appropriate PackageSource implementation for a PackageSpec.

    Mapping:
    - conda-forge -> CondaSource(channel="conda-forge")
    - intel       -> CondaSource(channel="intel")
    - apt         -> AptSource()
    - local       -> LocalSource()
    """
    if spec.channel in {"conda-forge", "intel"}:
        return CondaSource(channel=spec.channel)
    if spec.channel == "apt":
        return AptSource()
    if spec.channel == "local":
        return LocalSource()

    raise ValueError(f"Unsupported source channel: {spec.channel}")
