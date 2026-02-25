"""Package specification parser.

Parses package specs in the format: channel:package=version

Examples:
    conda-forge:dal=2025.9.0
    intel:mkl=2025.1
    apt:intel-oneapi-dal=2025.9.0
    local:/path/to/libonedal.so
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class PackageSpec:
    """Represents a package specification."""

    SUPPORTED_CHANNELS = {"conda-forge", "intel", "apt", "local"}

    channel: str
    package: str
    version: Optional[str] = None
    path: Optional[Path] = None
    
    @classmethod
    def parse(cls, spec: str, require_version: bool = True) -> "PackageSpec":
        """Parse a package spec string.
        
        Format: channel:package=version
        Special case: local:/path/to/file
        
        Args:
            spec: Package specification string
            
        Returns:
            PackageSpec object
            
        Raises:
            ValueError: If spec format is invalid
        """
        if not spec or ":" not in spec:
            raise ValueError(
                f"Invalid package spec '{spec}'. "
                f"Expected format: channel:package[=version]"
            )
        
        channel, rest = spec.split(":", 1)
        channel = channel.strip()

        if channel not in cls.SUPPORTED_CHANNELS:
            raise ValueError(
                f"Unsupported channel '{channel}'. "
                f"Supported channels: {', '.join(sorted(cls.SUPPORTED_CHANNELS))}"
            )

        # Special case: local file path
        if channel == "local":
            local_path = rest.strip()
            if not local_path:
                raise ValueError("Local spec requires a file path: local:/path/to/file.so")

            path = Path(local_path).expanduser().resolve()
            if not path.exists():
                raise ValueError(f"Local file not found: {path}")
            if not path.is_file():
                raise ValueError(f"Local path is not a file: {path}")

            return cls(
                channel="local",
                package=path.stem,  # Use filename as package name
                path=path
            )
        
        # Standard case: channel:package=version (version optional when require_version=False)
        if "=" not in rest:
            if require_version:
                raise ValueError(
                    f"Invalid package spec '{spec}'. "
                    f"Expected format: channel:package=version"
                )
            package = rest.strip()
            version = None
        else:
            package, version = rest.split("=", 1)
        package = package.strip()
        if version is not None:
            version = version.strip()
        
        if not package:
            raise ValueError(f"Empty package name in spec '{spec}'")
        if require_version and not version:
            raise ValueError(f"Empty version in spec '{spec}'")
        
        return cls(
            channel=channel,
            package=package,
            version=version
        )
    
    def __str__(self) -> str:
        """String representation of the spec."""
        if self.channel == "local":
            return f"local:{self.path}"
        return f"{self.channel}:{self.package}={self.version}"
    
    def __repr__(self) -> str:
        """Detailed representation."""
        if self.channel == "local":
            return f"PackageSpec(channel='local', path={self.path})"
        return (
            f"PackageSpec(channel='{self.channel}', "
            f"package='{self.package}', version='{self.version}')"
        )


def validate_spec(spec: str) -> bool:
    """Quick validation without full parsing.
    
    Args:
        spec: Package specification string
        
    Returns:
        True if spec looks valid
    """
    try:
        PackageSpec.parse(spec)
        return True
    except ValueError:
        return False
