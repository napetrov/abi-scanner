"""Package source adapters for ABI Scanner.

Provides unified interface for downloading and extracting packages from different sources:
- Conda/Anaconda channels (conda-forge, intel, etc.)
- APT repositories
- Local filesystem paths
"""

from .base import PackageSource, PackageMetadata
from .conda import CondaSource
from .apt import AptSource
from .local import LocalSource
from .factory import create_source

__all__ = [
    'PackageSource',
    'PackageMetadata',
    'CondaSource',
    'AptSource',
    'LocalSource',
    'create_source',
]
