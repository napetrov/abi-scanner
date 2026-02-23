#!/usr/bin/env python3
"""Setup script for abi-scanner."""

import re
from pathlib import Path

from setuptools import find_packages, setup

# Read README
root = Path(__file__).parent
readme_file = root / "README.md"
long_description = readme_file.read_text() if readme_file.exists() else ""

# Single-source version from package
version_file = root / "abi_scanner" / "__init__.py"
version_match = re.search(
    r"^__version__\s*=\s*[\"']([^\"']+)[\"']",
    version_file.read_text(),
    re.MULTILINE,
)
if not version_match:
    raise RuntimeError("Unable to find __version__ in abi_scanner/__init__.py")
package_version = version_match.group(1)

setup(
    name="abi-scanner",
    version=package_version,
    description="Universal ABI compatibility checker for C/C++ libraries",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Nikolay Petrov",
    author_email="nikolay.a.petrov@intel.com",
    url="https://github.com/napetrov/abi-scanner",
    packages=find_packages(),
    python_requires=">=3.8",
    install_requires=[
        # Intentionally empty - stdlib only (argparse) for Phase 1
        # Phase 2 will add: packaging, pyyaml (for config loading)
    ],
    entry_points={
        "console_scripts": [
            "abi-scanner=abi_scanner.cli:main",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Build Tools",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    keywords="abi compatibility checker semver c++ shared-library",
)
